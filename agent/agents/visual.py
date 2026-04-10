"""VisualAgent - Visual Agent mit Screenshot-Analyse."""

import os
import io
import json
import re
import asyncio
import base64
import time
import logging
from typing import Any, Dict, List, Optional

import httpx

from agent.base_agent import BaseAgent, MCP_URL
from agent.providers import ModelProvider
from agent.providers import resolve_model_provider_env
from agent.prompts import VISUAL_SYSTEM_PROMPT
from agent.shared.delegation_handoff import DelegationHandoff, parse_delegation_handoff
from agent.shared.json_utils import extract_json_robust
from agent.shared.vision_formatter import convert_openai_to_anthropic
from orchestration.approval_auth_contract import (
    build_awaiting_user_workflow_payload,
    build_challenge_required_workflow_payload,
    build_user_mediated_login_workflow_payload,
    derive_user_action_blocker_reason,
    normalize_phase_d_workflow_payload,
)
from orchestration.auth_session_state import is_auth_session_reusable, normalize_auth_session_entry
from orchestration.specialist_context import (
    assess_specialist_context_alignment,
    extract_specialist_context_from_handoff_data,
    format_specialist_signal_response,
    render_specialist_context_block,
)
from orchestration.autonomy_observation import record_autonomy_observation
from orchestration.browser_workflow_plan import (
    BrowserStateEvidence,
    BrowserWorkflowPlan,
    BrowserWorkflowStep,
    build_browser_workflow_plan,
    build_structured_browser_workflow_plan,
)

log = logging.getLogger("TimusAgent-v4.4")


class VisualAgent(BaseAgent):
    """Visual Agent mit Screenshot-Analyse."""

    _SCAN_LOOP_RECOVERY_TEXT = (
        "LOOP-WARNUNG bei scan_ui_elements: aendere den Ansatz. "
        "Nutze andere element_types, setze use_zoom=false oder wechsle auf "
        "Text/OCR-basierte Suche statt denselben Scan zu wiederholen."
    )

    def __init__(self, tools_description_string: str):
        super().__init__(VISUAL_SYSTEM_PROMPT, tools_description_string, 30, "visual")

        self._mss_module = None
        self._pil_image = None
        try:
            import mss
            from PIL import Image
            self._mss_module = mss
            self._pil_image = Image
        except ImportError:
            pass

        self.history: list = []
        self.last_clicked_element_type = None

        self.roi_stack: List[Dict] = []
        self.current_roi: Optional[Dict] = None
        self.current_workflow_plan: List[str] = []
        self.current_structured_workflow_plan: Optional[BrowserWorkflowPlan] = None
        self.current_browser_url: str = ""
        self.current_browser_type: str = "firefox"
        self.current_credential_broker: str = ""
        self.current_broker_profile: str = ""
        self.current_broker_domain: str = ""

    def _notify_delegation_progress(self, stage: str, **payload: Any) -> None:
        callback = getattr(self, "_delegation_progress_callback", None)
        if not callable(callback):
            return
        try:
            callback(stage=stage, payload=payload)
            return
        except TypeError:
            pass
        try:
            callback(stage, payload)
            return
        except TypeError:
            pass
        try:
            callback(stage)
        except Exception:
            return

    def _emit_user_action_blocker(self, payload: Any, *, stage: str = "user_action_required") -> None:
        if not isinstance(payload, dict):
            return
        normalized_payload = normalize_phase_d_workflow_payload(payload)
        if not normalized_payload:
            return
        self._notify_delegation_progress(
            stage,
            kind="blocker",
            blocker_reason=derive_user_action_blocker_reason(normalized_payload),
            message=str(normalized_payload.get("error") or normalized_payload.get("message") or "").strip(),
            user_action_required=str(normalized_payload.get("user_action_required") or "").strip(),
            platform=str(normalized_payload.get("platform") or "").strip(),
            service=str(normalized_payload.get("service") or "").strip(),
            url=str(normalized_payload.get("url") or "").strip(),
            tool_status=str(normalized_payload.get("status") or "").strip(),
            workflow_id=str(normalized_payload.get("workflow_id") or "").strip(),
            workflow_kind=str(normalized_payload.get("workflow_kind") or "").strip(),
            workflow_reason=str(normalized_payload.get("reason") or "").strip(),
            approval_scope=str(normalized_payload.get("approval_scope") or "").strip(),
            resume_hint=str(normalized_payload.get("resume_hint") or "").strip(),
            challenge_type=str(normalized_payload.get("challenge_type") or "").strip(),
            auth_required=bool(normalized_payload.get("auth_required")),
            approval_required=bool(normalized_payload.get("approval_required")),
            awaiting_user=bool(normalized_payload.get("awaiting_user")),
            challenge_required=bool(normalized_payload.get("challenge_required")),
            status=str(normalized_payload.get("status") or "").strip(),
        )

    @staticmethod
    def _build_phase_d_workflow_result(
        payload: Any,
        *,
        result_text: str = "",
        **extra: Any,
    ) -> dict[str, Any]:
        normalized_payload = normalize_phase_d_workflow_payload(payload)
        if not normalized_payload:
            return {}
        effective_result = str(
            result_text
            or normalized_payload.get("message")
            or normalized_payload.get("error")
            or normalized_payload.get("status")
            or ""
        ).strip()
        response = {
            **normalized_payload,
            "success": False,
            "result": effective_result,
            "metadata": {
                "phase_d_workflow": normalized_payload,
            },
        }
        for key, value in extra.items():
            if value is not None:
                response[key] = value
        return response

    def _emit_auth_session_ready(
        self,
        *,
        service: str,
        url: str,
        workflow_id: str,
        status: str = "authenticated",
        reason: str = "login_confirmed",
        evidence: str = "",
        browser_type: str = "",
        credential_broker: str = "",
        broker_profile: str = "",
        domain: str = "",
    ) -> None:
        if not service and not url:
            return
        self._notify_delegation_progress(
            "auth_session_ready",
            kind="auth_session",
            auth_session_status=str(status or "authenticated").strip().lower(),
            auth_session_service=str(service or "").strip().lower(),
            auth_session_url=str(url or "").strip(),
            auth_session_scope="session",
            auth_session_workflow_id=str(workflow_id or "").strip(),
            auth_session_reason=str(reason or "login_confirmed").strip().lower(),
            auth_session_reuse_ready=True,
            auth_session_evidence=str(evidence or "").strip(),
            auth_session_browser_type=str(browser_type or "").strip().lower(),
            auth_session_credential_broker=str(credential_broker or "").strip().lower(),
            auth_session_broker_profile=str(broker_profile or "").strip(),
            auth_session_domain=str(domain or "").strip().lower(),
        )

    def _get_screenshot_as_base64(self) -> str:
        if not self._mss_module or not self._pil_image:
            return ""
        try:
            with self._mss_module.mss() as sct:
                mon = int(os.getenv("ACTIVE_MONITOR", "1"))
                monitor = sct.monitors[mon] if mon < len(sct.monitors) else sct.monitors[1]
                raw = sct.grab(monitor)
                img = self._pil_image.frombytes("RGB", raw.size, raw.bgra, "raw", "BGRX")
            img.thumbnail((1280, 720))
            buf = io.BytesIO()
            img.save(buf, "PNG")
            return base64.b64encode(buf.getvalue()).decode()
        except Exception:
            return ""

    async def _capture_before(self):
        try:
            await self.http_client.post(
                MCP_URL,
                json={"jsonrpc": "2.0", "method": "capture_screen_before_action", "params": {}, "id": "1"},
            )
        except Exception:
            pass

    async def _verify_action(self, method: str) -> bool:
        if method not in ["click_at", "type_text", "start_visual_browser", "open_application"]:
            return True
        try:
            resp = await self.http_client.post(
                MCP_URL,
                json={"jsonrpc": "2.0", "method": "verify_action_result", "params": {"timeout": 5.0}, "id": "1"},
            )
            return resp.json().get("result", {}).get("success", False)
        except Exception:
            return False

    # ------------------------------------------------------------------
    # 3c: Robusteres Retry-Verhalten (Phase 3)
    # ------------------------------------------------------------------

    MAX_VISUAL_RETRIES = int(os.getenv("VISUAL_MAX_RETRIES", "3"))  # Lean: visual_retry_terminates

    async def _click_with_retry(self, x: int, y: int, label: str = "") -> bool:
        """
        Klickt mit bis zu MAX_VISUAL_RETRIES Versuchen.
        Lean Th.48: retry ≤ MAX_VISUAL_RETRIES → retry < MAX_VISUAL_RETRIES + 1

        Strategie:
          Versuch 1: Direktklick
          Versuch 2: Warten (500ms) + Screenshot + Koordinaten neu berechnen
          Versuch 3+: Alternative Klick-Methode (Koordinaten-Fallback)
        """
        for attempt in range(self.MAX_VISUAL_RETRIES):
            try:
                if attempt == 1:
                    # Kurz warten, dann Screenshot neu auswerten
                    await asyncio.sleep(0.5)
                    await self._wait_for_stable_screenshot(timeout_ms=2000)

                resp = await self.http_client.post(
                    MCP_URL,
                    json={"jsonrpc": "2.0", "method": "click_at",
                          "params": {"x": x, "y": y}, "id": "1"},
                )
                result = resp.json().get("result", {})
                if result.get("success", False):
                    log.info("_click_with_retry: Erfolg bei Versuch %d (%s)", attempt + 1, label)
                    return True

                log.warning("_click_with_retry: Versuch %d fehlgeschlagen (%s)", attempt + 1, label)
            except Exception as exc:
                log.warning("_click_with_retry: Exception Versuch %d: %s", attempt + 1, exc)

        log.error("_click_with_retry: Alle %d Versuche fehlgeschlagen (%s)", self.MAX_VISUAL_RETRIES, label)
        return False

    async def _wait_for_stable_screenshot(self, timeout_ms: int = 2000) -> bool:
        """
        Wartet bis der Bildschirm stabil ist (≥ 95% identische Pixel).
        Gibt True zurück wenn Stabilität erreicht, False bei Timeout.
        """
        try:
            resp = await self.http_client.post(
                MCP_URL,
                json={"jsonrpc": "2.0", "method": "wait_until_stable",
                      "params": {"timeout": timeout_ms / 1000.0}, "id": "1"},
            )
            return resp.json().get("result", {}).get("success", False)
        except Exception:
            return False

    def _get_stability_timeout(self, method: str) -> float:
        if method == "start_visual_browser":
            return 1.0
        if method == "type_text":
            return 1.2
        if method in {"click_at", "open_application"}:
            return 1.5
        return 0.0

    async def _wait_stable(self, method: str = ""):
        timeout = self._get_stability_timeout(method)
        if timeout <= 0:
            return
        try:
            await self.http_client.post(
                MCP_URL,
                json={"jsonrpc": "2.0", "method": "wait_until_stable", "params": {"timeout": timeout}, "id": "1"},
            )
        except Exception:
            pass

    def _build_loop_recovery_hint(self, method: str) -> str:
        workflow_hint = ""
        if self.current_workflow_plan:
            workflow_hint = (
                " Nutze den vorhandenen Browser-Ablaufplan und gehe zum naechsten "
                "verifizierbaren Schritt zurueck statt denselben UI-Scan zu wiederholen."
            )
        if method == "scan_ui_elements":
            strategy = self._preferred_recovery_strategy()
            if strategy == "ocr_text":
                return (
                    f"{self._SCAN_LOOP_RECOVERY_TEXT} "
                    "Bevorzuge jetzt OCR/Text-Suche und vermeide denselben Bounding-Box-Scan."
                    f"{workflow_hint}"
                )
            if strategy == "datepicker":
                return (
                    f"{self._SCAN_LOOP_RECOVERY_TEXT} "
                    "Bei Kalendern: fokussiere den Datepicker und suche gezielt nach Datums-Text."
                    f"{workflow_hint}"
                )
            return f"{self._SCAN_LOOP_RECOVERY_TEXT}{workflow_hint}"
        return f"LOOP-WARNUNG fuer {method}: veraendere Parameter oder nutze einen anderen Tool-Pfad.{workflow_hint}"

    def _preferred_recovery_strategy(self) -> str:
        """Waehlt eine leichte visuelle Recovery-Praeferenz aus Feedback-Scores."""
        try:
            from orchestration.feedback_engine import get_feedback_engine

            engine = get_feedback_engine()
            candidates = {
                "ocr_text": engine.get_effective_target_score("visual_strategy", "ocr_text", default=1.0),
                "click_targeting": engine.get_effective_target_score("visual_strategy", "click_targeting", default=1.0),
                "datepicker": engine.get_effective_target_score("visual_strategy", "datepicker", default=1.0),
                "browser_flow": engine.get_effective_target_score("visual_strategy", "browser_flow", default=1.0),
            }
            return max(candidates.items(), key=lambda item: item[1])[0]
        except Exception:
            return "ocr_text"

    def _infer_visual_feedback_targets(self, task: str, *, strategy: str = "") -> List[Dict[str, str]]:
        task_lower = str(task or "").lower()
        inferred_strategy = str(strategy or "").strip().lower() or self._preferred_recovery_strategy()
        targets: List[Dict[str, str]] = [{"namespace": "visual_strategy", "key": inferred_strategy}]
        if any(token in task_lower for token in ("browser", "website", "webseite", "booking", ".com", ".de")):
            targets.append({"namespace": "visual_strategy", "key": "browser_flow"})
        if any(token in task_lower for token in ("datum", "date", "datepicker", "kalender", "check-in", "check-out")):
            targets.append({"namespace": "visual_strategy", "key": "datepicker"})

        unique: dict[tuple[str, str], Dict[str, str]] = {}
        for item in targets:
            unique[(item["namespace"], item["key"])] = item
        return list(unique.values())

    def _record_runtime_feedback(self, task: str, *, success: Optional[bool], strategy: str = "", stage: str = "") -> None:
        try:
            from orchestration.feedback_engine import get_feedback_engine

            get_feedback_engine().record_runtime_outcome(
                action_id=f"visual-{stage or 'run'}-{int(time.time() * 1000)}",
                success=success,
                context={
                    "agent": "visual",
                    "stage": str(stage or "run")[:80],
                    "visual_strategy": str(strategy or self._preferred_recovery_strategy())[:80],
                    "task_excerpt": str(task or "")[:160],
                },
                feedback_targets=self._infer_visual_feedback_targets(task, strategy=strategy),
            )
        except Exception as e:
            log.debug("Visual Runtime-Feedback fehlgeschlagen: %s", e)

    def _extract_browser_url(self, task: str) -> str:
        text = str(task or "").strip()
        if not text:
            return ""
        direct = re.search(r"https?://[^\s]+", text)
        if direct:
            return direct.group(0)
        domain = re.search(r"([a-zA-Z0-9.-]+\.(?:de|com|org|net|io|ai))", text)
        if domain:
            return f"https://{domain.group(1)}"
        return ""

    def _preferred_text_entry_method(self, text: str) -> str:
        candidate = str(text or "").strip()
        if not candidate:
            return "auto"
        if candidate.startswith(("http://", "https://", "www.")):
            return "clipboard"
        if re.search(r"[:/?=&%#@+~^\\|]", candidate):
            return "clipboard"
        return "auto"

    def _build_browser_plan_context(self, task: str) -> str:
        task_text = str(task or "").strip()
        if not task_text:
            self.current_workflow_plan = []
            self.current_structured_workflow_plan = None
            return ""
        task_lower = task_text.lower()
        if not any(token in task_lower for token in ("browser", "website", "webseite", "booking", ".com", ".de", "formular", "login", "anmelden")):
            self.current_workflow_plan = []
            self.current_structured_workflow_plan = None
            return ""

        browser_url = self._extract_browser_url(task_text) or self.current_browser_url

        self.current_structured_workflow_plan = build_structured_browser_workflow_plan(
            task_text,
            browser_url,
        )
        self.current_workflow_plan = build_browser_workflow_plan(
            task_text,
            browser_url,
        )
        plan_lines = []
        for index, step in enumerate(self.current_structured_workflow_plan.steps[:8], start=1):
            evidence = ", ".join(
                f"{item.evidence_type}={item.value}" for item in step.success_signal[:2]
            )
            plan_lines.append(
                f"{index}. action={step.action} target={step.target_type}:{step.target_text} "
                f"expected_state={step.expected_state} timeout={step.timeout:.1f}s "
                f"fallback={step.fallback_strategy}"
                + (f" signal=[{evidence}]" if evidence else "")
            )
        return (
            "STRIKTER BROWSER-ABLAUFPLAN:\n"
            f"flow_type={self.current_structured_workflow_plan.flow_type} "
            f"initial_state={self.current_structured_workflow_plan.initial_state}\n"
            + "\n".join(plan_lines)
            + "\nArbeite strikt schrittweise. Wechsle Zustand nur bei harter Evidenz. "
              "Nutze Fallbacks nur als echten Strategiewechsel, nicht als denselben Retry."
        )

    def _prepare_visual_task(self, task: str) -> tuple[str, str]:
        handoff = parse_delegation_handoff(task)
        if not handoff:
            return str(task or "").strip(), ""

        effective_task = handoff.goal or str(task or "").strip()
        if handoff.handoff_data.get("source_url"):
            self.current_browser_url = str(handoff.handoff_data["source_url"]).strip()
        elif handoff.handoff_data.get("results_url"):
            self.current_browser_url = str(handoff.handoff_data["results_url"]).strip()

        lines = ["STRUKTURIERTER VISUAL-HANDOFF:"]
        if handoff.expected_output:
            lines.append(f"expected_output={handoff.expected_output}")
        if handoff.success_signal:
            lines.append(f"success_signal={handoff.success_signal}")
        if handoff.constraints:
            lines.append("constraints=" + " | ".join(handoff.constraints))

        specialist_context_payload = extract_specialist_context_from_handoff_data(handoff.handoff_data)
        specialist_context = render_specialist_context_block(
            specialist_context_payload,
            header="SPEZIALISTENKONTEXT:",
            alignment=assess_specialist_context_alignment(
                current_task=handoff.handoff_data.get("original_user_task")
                or handoff.handoff_data.get("target_hint")
                or handoff.goal,
                payload=specialist_context_payload,
            ),
        )
        if specialist_context:
            lines.append(specialist_context)

        for key in (
            "recipe_id",
            "stage_id",
            "expected_state",
            "target_hint",
            "source_url",
            "results_url",
            "previous_stage_result",
            "captured_context",
            "browser_plan",
            "previous_blackboard_key",
        ):
            value = handoff.handoff_data.get(key)
            if value:
                lines.append(f"{key}={value}")

        return effective_task, "\n".join(lines)

    @staticmethod
    def _extract_followup_field(raw_task: str, field_name: str) -> str:
        match = re.search(
            rf"^\s*{re.escape(field_name)}:\s*(.+)$",
            str(raw_task or ""),
            flags=re.IGNORECASE | re.MULTILINE,
        )
        return str(match.group(1) if match else "").strip()

    @staticmethod
    def _extract_followup_current_query(raw_task: str) -> str:
        match = re.search(
            r"#\s*CURRENT USER QUERY\s*(.+)$",
            str(raw_task or ""),
            flags=re.IGNORECASE | re.DOTALL,
        )
        return str(match.group(1) if match else "").strip()

    def _extract_pending_login_resume_context(self, raw_task: str) -> dict[str, str]:
        source = str(raw_task or "")
        if "# FOLLOW-UP CONTEXT" not in source:
            return {}
        status = self._extract_followup_field(source, "pending_workflow_status").lower()
        reason = self._extract_followup_field(source, "pending_workflow_reason").lower()
        reply_kind = self._extract_followup_field(source, "pending_workflow_reply_kind").lower()
        source_agent = self._extract_followup_field(source, "pending_workflow_source_agent").lower()
        is_login_resume = status == "awaiting_user" and reason in {"", "user_mediated_login", "user_action_required"}
        is_challenge_resume = status == "challenge_required"
        if (not is_login_resume and not is_challenge_resume) or not reply_kind:
            return {}
        return {
            "workflow_id": self._extract_followup_field(source, "pending_workflow_workflow_id")
            or self._extract_followup_field(source, "pending_workflow_id"),
            "status": status,
            "reason": reason,
            "service": self._extract_followup_field(source, "pending_workflow_service").lower(),
            "url": self._extract_followup_field(source, "pending_workflow_url"),
            "reply_kind": reply_kind,
            "challenge_type": self._extract_followup_field(source, "pending_workflow_challenge_type").lower(),
            "resume_hint": self._extract_followup_field(source, "pending_workflow_resume_hint"),
            "source_agent": source_agent,
            "preferred_browser": (
                self._extract_followup_field(source, "pending_workflow_preferred_browser")
                or self._extract_followup_field(source, "pending_workflow_browser_type")
            ).lower(),
            "credential_broker": self._extract_followup_field(source, "pending_workflow_credential_broker").lower(),
            "broker_profile": self._extract_followup_field(source, "pending_workflow_broker_profile"),
            "domain": self._extract_followup_field(source, "pending_workflow_domain").lower(),
            "current_query": self._extract_followup_current_query(source),
        }

    def _extract_auth_session_context(
        self,
        raw_task: str,
        handoff: Optional[DelegationHandoff] = None,
    ) -> dict[str, str]:
        payload: dict[str, Any] = {}
        handoff_data = handoff.handoff_data if handoff else {}
        for key in (
            "auth_session_service",
            "auth_session_status",
            "auth_session_scope",
            "auth_session_url",
            "auth_session_confirmed_at",
            "auth_session_expires_at",
            "auth_session_browser_type",
            "auth_session_credential_broker",
            "auth_session_broker_profile",
            "auth_session_domain",
        ):
            value = str(handoff_data.get(key) or "").strip()
            if value:
                payload[key.replace("auth_session_", "")] = value

        if not payload and "# FOLLOW-UP CONTEXT" in str(raw_task or ""):
            for key in (
                "service",
                "status",
                "scope",
                "url",
                "confirmed_at",
                "expires_at",
                "browser_type",
                "credential_broker",
                "broker_profile",
                "domain",
            ):
                value = self._extract_followup_field(raw_task, f"auth_session_{key}")
                if value:
                    payload[key] = value

        normalized = normalize_auth_session_entry(payload) if payload else None
        return normalized.to_dict() if normalized else {}

    @staticmethod
    def _infer_domain_from_url(url: str) -> str:
        raw = str(url or "").strip().lower()
        if not raw:
            return ""
        host = raw.replace("https://", "").replace("http://", "").split("/")[0]
        if host.startswith("www."):
            host = host[4:]
        return host

    def _resolve_login_lane(
        self,
        *,
        handoff: Optional[DelegationHandoff],
        auth_session: Optional[dict[str, str]],
        url: str,
    ) -> dict[str, str]:
        handoff_data = handoff.handoff_data if handoff else {}
        browser_type = (
            str(handoff_data.get("browser_type") or "").strip().lower()
            or str((auth_session or {}).get("browser_type") or "").strip().lower()
            or "firefox"
        )
        credential_broker = (
            str(handoff_data.get("credential_broker") or "").strip().lower()
            or str((auth_session or {}).get("credential_broker") or "").strip().lower()
        )
        broker_profile = (
            str(handoff_data.get("broker_profile") or "").strip()
            or str((auth_session or {}).get("broker_profile") or "").strip()
        )
        domain = (
            str(handoff_data.get("domain") or "").strip().lower()
            or str((auth_session or {}).get("domain") or "").strip().lower()
            or self._infer_domain_from_url(url)
        )
        if credential_broker == "chrome_password_manager" and browser_type == "firefox":
            browser_type = "chrome"
        if credential_broker == "chrome_password_manager" and not broker_profile:
            broker_profile = "Default"
        return {
            "browser_type": browser_type,
            "credential_broker": credential_broker,
            "broker_profile": broker_profile,
            "domain": domain,
        }

    def _set_login_lane(self, lane: dict[str, str]) -> None:
        self.current_browser_type = str(lane.get("browser_type") or "firefox").strip().lower() or "firefox"
        self.current_credential_broker = str(lane.get("credential_broker") or "").strip().lower()
        self.current_broker_profile = str(lane.get("broker_profile") or "").strip()
        self.current_broker_domain = str(lane.get("domain") or "").strip().lower()

    def _resolve_login_target(self, handoff: Optional[DelegationHandoff], effective_task: str) -> tuple[str, str]:
        source_url = (
            str((handoff.handoff_data.get("source_url") or "") if handoff else "").strip()
            or self.current_browser_url
            or self._extract_browser_url(effective_task)
        )
        service = (
            str((handoff.handoff_data.get("service") or handoff.handoff_data.get("service_name") or "") if handoff else "").strip().lower()
            or self._infer_service_from_browser_url(source_url)
        )
        return source_url, service

    async def _try_reuse_authenticated_session(
        self,
        auth_session: dict[str, str],
        *,
        handoff: Optional[DelegationHandoff],
        effective_task: str,
    ) -> Optional[Dict[str, Any]]:
        source_url, target_service = self._resolve_login_target(handoff, effective_task)
        reusable_service = str(auth_session.get("service") or "").strip().lower() or target_service
        if not reusable_service:
            return None
        if not is_auth_session_reusable(auth_session, service=reusable_service):
            return None

        reuse_url = str(auth_session.get("url") or "").strip() or source_url
        if not reuse_url:
            return None

        self.current_browser_url = reuse_url
        browser_type = str(auth_session.get("browser_type") or self.current_browser_type or "firefox").strip().lower() or "firefox"
        broker_profile = str(auth_session.get("broker_profile") or "").strip()
        start_payload: Dict[str, Any] = {"url": reuse_url, "browser_type": browser_type}
        if browser_type == "chrome" and broker_profile:
            start_payload["profile_name"] = broker_profile
        result = await self._call_tool("start_visual_browser", start_payload)
        if isinstance(result, dict) and result.get("success") is False:
            return None

        verification = await self._detect_authenticated_session_state(reusable_service)
        if not verification.get("success"):
            return None

        positives = ", ".join(str(item) for item in verification.get("positive_hits") or [])
        self._emit_auth_session_ready(
            service=reusable_service,
            url=reuse_url,
            workflow_id=str(auth_session.get("workflow_id") or ""),
            status="session_reused",
            reason="session_reused",
            evidence=positives,
            browser_type=browser_type,
            credential_broker=str(auth_session.get("credential_broker") or "").strip().lower(),
            broker_profile=broker_profile,
            domain=str(auth_session.get("domain") or self._infer_domain_from_url(reuse_url)).strip().lower(),
        )
        suffix = f" Sichtbare Signale: {positives}." if positives else ""
        return {
            "success": True,
            "result": (
                f"Bestehende Session bei {reusable_service} wiederverwendet. "
                f"Ein neuer Login-Schritt wurde uebersprungen.{suffix}"
            ).strip(),
            "current_state": "authenticated",
            "metadata": {
                "auth_session": {
                    **auth_session,
                    "status": "session_reused",
                    "service": reusable_service,
                    "url": reuse_url,
                }
            },
        }

    async def _normalize_login_flow_success_result(
        self,
        result: Dict[str, Any],
        *,
        handoff: Optional[DelegationHandoff],
        effective_task: str,
    ) -> Dict[str, Any]:
        if not isinstance(result, dict) or not result.get("success"):
            return result
        if not self.current_structured_workflow_plan:
            return result
        if str(self.current_structured_workflow_plan.flow_type or "").strip().lower() != "login_flow":
            return result

        raw_metadata = result.get("metadata") if isinstance(result.get("metadata"), dict) else {}
        auth_metadata = raw_metadata.get("auth_session") if isinstance(raw_metadata.get("auth_session"), dict) else {}
        if auth_metadata:
            return result
        if str(result.get("current_state") or "").strip().lower() == "authenticated":
            return result

        source_url, service = self._resolve_login_target(handoff, effective_task)
        verification = await self._detect_authenticated_session_state(service)
        if verification.get("success"):
            return result

        payload = build_user_mediated_login_workflow_payload(
            service=service,
            url=source_url,
            domain=self.current_broker_domain or self._infer_domain_from_url(source_url),
            preferred_browser=self.current_browser_type,
            credential_broker=self.current_credential_broker,
            broker_profile=self.current_broker_profile,
            message=(
                "Die Login-Maske ist sichtbar und bereit zur nutzergesteuerten Anmeldung. "
                "Timus stoppt hier bewusst vor Benutzername, Passwort und 2FA."
            ),
            user_action_required=(
                (
                    f"Bitte nutze den Chrome-Passwortmanager oder gib Benutzername, Passwort und ggf. 2FA selbst bei {service or 'dem Dienst'} ein."
                    if self.current_credential_broker == "chrome_password_manager"
                    else f"Bitte gib Benutzername, Passwort und ggf. 2FA selbst bei {service or 'dem Dienst'} ein."
                )
            ),
            resume_hint=(
                "Sage danach 'weiter', 'ich bin eingeloggt' oder beschreibe die sichtbare Challenge, "
                "damit Timus kontrolliert fortsetzen kann."
            ),
        )
        self._emit_user_action_blocker(payload, stage="await_login_completion")
        phase_d_result = self._build_phase_d_workflow_result(
            payload,
            result_text=str(payload.get("message") or "").strip(),
        )
        for key in ("completed_steps", "current_state", "plan_id", "state"):
            if key in result:
                phase_d_result[key] = result[key]
        if raw_metadata:
            merged_metadata = dict(raw_metadata)
            merged_metadata.update(phase_d_result.get("metadata") or {})
            phase_d_result["metadata"] = merged_metadata
        return phase_d_result

    @staticmethod
    def _infer_challenge_type_from_query(query: str) -> str:
        lowered = str(query or "").strip().lower()
        if "cloudflare" in lowered or "turnstile" in lowered:
            return "cloudflare_challenge"
        if "hcaptcha" in lowered:
            return "hcaptcha"
        if "recaptcha" in lowered:
            return "recaptcha"
        if "captcha" in lowered:
            return "captcha"
        if "2fa" in lowered or "authenticator" in lowered or "sms" in lowered or "code" in lowered:
            return "2fa"
        if "access denied" in lowered:
            return "access_denied"
        return "security_challenge"

    @staticmethod
    def _authenticated_markers_for_service(service: str) -> tuple[tuple[str, ...], tuple[str, ...]]:
        common_positive = ("dashboard", "profil", "profile", "account", "settings", "abmelden", "sign out")
        common_negative = ("login", "sign in", "anmelden", "passwort", "password", "username")
        normalized = str(service or "").strip().lower()
        if normalized == "github":
            return (
                ("repositories", "pull requests", "issues", "codespaces", "github", *common_positive),
                common_negative,
            )
        if normalized == "x":
            return (
                ("home", "notifications", "messages", "post", "what's happening", *common_positive),
                common_negative,
            )
        if normalized == "linkedin":
            return (
                ("feed", "network", "messaging", "jobs", "linkedin", *common_positive),
                common_negative,
            )
        if normalized == "outlook":
            return (
                ("inbox", "new mail", "outlook", "sent items", *common_positive),
                common_negative,
            )
        return (common_positive, common_negative)

    @staticmethod
    def _infer_visible_browser_from_text_blob(text_blob: str) -> str:
        lowered = str(text_blob or "").strip().lower()
        if not lowered:
            return ""
        if "mozilla firefox" in lowered or "firefox" in lowered:
            return "firefox"
        if "google chrome" in lowered or "chrome" in lowered or "chromium" in lowered:
            return "chrome"
        return ""

    async def _detect_authenticated_session_state(self, service: str) -> dict[str, Any]:
        screen_state = await self._analyze_current_screen()
        elements = list(screen_state.get("elements") or []) if isinstance(screen_state, dict) else []
        text_blob = " | ".join(
            str(item.get("text") or "").strip().lower()
            for item in elements
            if isinstance(item, dict) and str(item.get("text") or "").strip()
        )
        positive_markers, negative_markers = self._authenticated_markers_for_service(service)
        positive_hits = [marker for marker in positive_markers if marker in text_blob]
        negative_hits = [marker for marker in negative_markers if marker in text_blob]
        return {
            "success": bool(positive_hits),
            "positive_hits": positive_hits,
            "negative_hits": negative_hits,
            "text_preview": text_blob[:280],
            "visible_browser": self._infer_visible_browser_from_text_blob(text_blob),
        }

    def _build_goal_satisfied_login_result(
        self,
        *,
        service: str,
        url: str,
        workflow_id: str,
        lane: dict[str, str],
        verification: dict[str, Any],
        execution_log: List[Dict[str, Any]],
        current_state: str,
        plan_id: str,
    ) -> Dict[str, Any]:
        positives = ", ".join(str(item) for item in verification.get("positive_hits") or [])
        visible_browser = str(verification.get("visible_browser") or "").strip().lower()
        session_browser = visible_browser or str(lane.get("browser_type") or self.current_browser_type or "").strip().lower()
        session_broker = ""
        session_profile = ""
        if session_browser == "chrome" and str(lane.get("credential_broker") or "").strip().lower() == "chrome_password_manager":
            session_broker = "chrome_password_manager"
            session_profile = str(lane.get("broker_profile") or "").strip()

        self._emit_auth_session_ready(
            service=service,
            url=url,
            workflow_id=workflow_id,
            status="authenticated",
            reason="goal_already_satisfied",
            evidence=positives,
            browser_type=session_browser,
            credential_broker=session_broker,
            broker_profile=session_profile,
            domain=str(lane.get("domain") or self._infer_domain_from_url(url)).strip().lower(),
        )

        browser_note = ""
        requested_browser = str(lane.get("browser_type") or "").strip().lower()
        if visible_browser and requested_browser and visible_browser != requested_browser:
            browser_note = (
                f" Sichtbar ist der eingeloggte Zustand aktuell in {visible_browser}, "
                f"nicht im angeforderten {requested_browser}."
            )
        evidence_note = f" Sichtbare Signale: {positives}." if positives else ""

        return {
            "success": True,
            "result": (
                f"Der Login bei {service or 'dem Dienst'} ist funktional bereits erfüllt. "
                f"Ich sehe bereits einen eingeloggten Zustand und ueberspringe den Login-Schritt."
                f"{evidence_note}{browser_note}"
            ).strip(),
            "current_state": "authenticated",
            "completed_steps": execution_log,
            "plan_id": plan_id,
            "metadata": {
                "auth_session": {
                    "service": service,
                    "status": "authenticated",
                    "scope": "session",
                    "url": url,
                    "workflow_id": workflow_id,
                    "browser_type": session_browser,
                    "credential_broker": session_broker,
                    "broker_profile": session_profile,
                    "domain": str(lane.get("domain") or self._infer_domain_from_url(url)).strip().lower(),
                }
            },
        }

    async def _resume_user_mediated_login(self, context: dict[str, str]) -> str:
        service = str(context.get("service") or "").strip().lower()
        url = str(context.get("url") or "").strip()
        reply_kind = str(context.get("reply_kind") or "").strip().lower()
        workflow_id = str(context.get("workflow_id") or "").strip()
        workflow_status = str(context.get("status") or "").strip().lower()
        current_query = str(context.get("current_query") or "").strip()
        challenge_type = (
            str(context.get("challenge_type") or "").strip().lower()
            or self._infer_challenge_type_from_query(current_query)
        )

        if reply_kind == "challenge_present":
            payload = build_challenge_required_workflow_payload(
                service=service,
                workflow_id=workflow_id,
                challenge_type=challenge_type,
                url=url,
                domain=str(context.get("domain") or "").strip().lower(),
                preferred_browser=str(context.get("preferred_browser") or "").strip().lower(),
                credential_broker=str(context.get("credential_broker") or "").strip().lower(),
                broker_profile=str(context.get("broker_profile") or "").strip(),
                message="Ich sehe den Login noch nicht als abgeschlossen; die Sicherheitspruefung ist weiterhin aktiv.",
            )
            self._emit_user_action_blocker(payload, stage="await_login_challenge_resolution")
            return self._build_phase_d_workflow_result(
                payload,
                result_text=f"{payload['message']}\n\n{payload['user_action_required']}".strip(),
            )

        if reply_kind == "resume_blocked":
            if workflow_status == "challenge_required":
                payload = build_challenge_required_workflow_payload(
                    service=service,
                    workflow_id=workflow_id,
                    challenge_type=challenge_type,
                    url=url,
                    domain=str(context.get("domain") or "").strip().lower(),
                    preferred_browser=str(context.get("preferred_browser") or "").strip().lower(),
                    credential_broker=str(context.get("credential_broker") or "").strip().lower(),
                    broker_profile=str(context.get("broker_profile") or "").strip(),
                    message="Die Sicherheitspruefung scheint noch nicht geloest zu sein.",
                )
                self._emit_user_action_blocker(payload, stage="await_login_challenge_resolution")
                return self._build_phase_d_workflow_result(
                    payload,
                    result_text=f"{payload['message']}\n\n{payload['user_action_required']}".strip(),
                )
            payload = build_awaiting_user_workflow_payload(
                service=service,
                workflow_id=workflow_id,
                url=url,
                reason="user_mediated_login",
                step="login_form_ready",
                domain=str(context.get("domain") or "").strip().lower(),
                preferred_browser=str(context.get("preferred_browser") or "").strip().lower(),
                credential_broker=str(context.get("credential_broker") or "").strip().lower(),
                broker_profile=str(context.get("broker_profile") or "").strip(),
                message="Der Login wirkt noch nicht abgeschlossen.",
                resume_hint="Sage 'ich bin eingeloggt' oder beschreibe die sichtbare Blockade genauer.",
                user_action_required="Bitte schliesse den Login selbst im Browser ab oder gib die sichtbare Blockade an.",
            )
            self._emit_user_action_blocker(payload, stage="await_login_completion")
            return self._build_phase_d_workflow_result(
                payload,
                result_text=f"{payload['message']}\n\n{payload['user_action_required']}".strip(),
            )

        verification = await self._detect_authenticated_session_state(service)
        if verification.get("success"):
            positives = ", ".join(str(item) for item in verification.get("positive_hits") or [])
            self._emit_auth_session_ready(
                service=service,
                url=url,
                workflow_id=workflow_id,
                evidence=positives,
                browser_type=str(context.get("preferred_browser") or "").strip().lower(),
                credential_broker=str(context.get("credential_broker") or "").strip().lower(),
                broker_profile=str(context.get("broker_profile") or "").strip(),
                domain=str(context.get("domain") or "").strip().lower(),
            )
            suffix = f" Sichtbare Signale: {positives}." if positives else ""
            return (
                f"Der Login bei {service or 'dem Dienst'} wirkt bestaetigt. "
                f"Der user-mediated Login-Workflow ist damit abgeschlossen.{suffix}"
            ).strip()

        if workflow_status == "challenge_required" or reply_kind == "challenge_resolved":
            payload = build_challenge_required_workflow_payload(
                service=service,
                workflow_id=workflow_id,
                challenge_type=challenge_type,
                url=url,
                domain=str(context.get("domain") or "").strip().lower(),
                preferred_browser=str(context.get("preferred_browser") or "").strip().lower(),
                credential_broker=str(context.get("credential_broker") or "").strip().lower(),
                broker_profile=str(context.get("broker_profile") or "").strip(),
                message="Ich kann nach der Sicherheitspruefung noch keinen bestaetigten eingeloggten Zustand erkennen.",
            )
            self._emit_user_action_blocker(payload, stage="await_login_challenge_resolution")
            return self._build_phase_d_workflow_result(
                payload,
                result_text=f"{payload['message']}\n\n{payload['user_action_required']}".strip(),
            )

        payload = build_awaiting_user_workflow_payload(
            service=service,
            workflow_id=workflow_id,
            url=url,
            reason="user_mediated_login",
            step="login_form_ready",
            domain=str(context.get("domain") or "").strip().lower(),
            preferred_browser=str(context.get("preferred_browser") or "").strip().lower(),
            credential_broker=str(context.get("credential_broker") or "").strip().lower(),
            broker_profile=str(context.get("broker_profile") or "").strip(),
            message="Ich kann den erfolgreichen Login noch nicht sicher bestaetigen.",
            resume_hint=(
                "Wenn du eingeloggt bist, sag 'ich bin eingeloggt' oder beschreibe kurz, was du jetzt im Browser siehst."
            ),
            user_action_required=(
                "Bitte schliesse den Login selbst im Browser ab. Falls eine Challenge sichtbar ist, nenne sie kurz."
            ),
        )
        self._emit_user_action_blocker(payload, stage="await_login_completion")
        return self._build_phase_d_workflow_result(
            payload,
            result_text=f"{payload['message']}\n\n{payload['user_action_required']}".strip(),
        )

    async def _call_llm(self, messages: List[Dict]) -> str:
        if self.provider == ModelProvider.ANTHROPIC:
            return await self._call_anthropic_vision(messages)
        return await super()._call_llm(messages)

    async def _call_anthropic_vision(self, messages: List[Dict]) -> str:
        client = self.provider_client.get_client(ModelProvider.ANTHROPIC)

        system_content, chat_messages = convert_openai_to_anthropic(messages)

        if client:
            resp = await asyncio.to_thread(
                client.messages.create,
                model=self.model,
                max_tokens=2000,
                system=system_content,
                messages=chat_messages,
            )
            return resp.content[0].text.strip()
        else:
            api_key = self.provider_client.get_api_key(ModelProvider.ANTHROPIC)
            async with httpx.AsyncClient(timeout=120.0) as http:
                resp = await http.post(
                    "https://api.anthropic.com/v1/messages",
                    headers={
                        "x-api-key": api_key,
                        "anthropic-version": "2023-06-01",
                        "content-type": "application/json",
                    },
                    json={
                        "model": self.model,
                        "max_tokens": 2000,
                        "system": system_content,
                        "messages": chat_messages,
                    },
                )
                return resp.json()["content"][0]["text"].strip()

    # ROI overrides (VisualAgent hat eigene ROI-Instanzen)
    def _set_roi(self, x: int, y: int, width: int, height: int, name: str = "custom"):
        roi = {"x": x, "y": y, "width": width, "height": height, "name": name}
        self.current_roi = roi
        log.info(f"ROI gesetzt: {name} ({x},{y} {width}x{height})")

    def _clear_roi(self):
        self.current_roi = None
        log.info("ROI geloescht")

    def _push_roi(self, x: int, y: int, width: int, height: int, name: str = "custom"):
        if self.current_roi:
            self.roi_stack.append(self.current_roi)
        self._set_roi(x, y, width, height, name)

    def _pop_roi(self):
        if self.roi_stack:
            self.current_roi = self.roi_stack.pop()
            log.info(f"ROI wiederhergestellt: {self.current_roi['name']}")
        else:
            self._clear_roi()

    async def _detect_dynamic_ui_and_set_roi(self, task: str) -> bool:
        task_lower = task.lower()

        if "google" in task_lower and ("such" in task_lower or "search" in task_lower):
            self._set_roi(x=200, y=100, width=800, height=150, name="google_searchbar")
            log.info("Dynamische UI erkannt: Google Search - ROI auf Suchleiste gesetzt")
            return True

        elif "booking" in task_lower:
            self._set_roi(x=100, y=150, width=1000, height=400, name="booking_search_form")
            log.info(
                "Dynamische UI erkannt: Booking.com - ROI auf Suchformular gesetzt (feedback_strategy=%s)",
                self._preferred_recovery_strategy(),
            )
            return True

        return False

    async def _analyze_current_screen(self) -> Optional[Dict]:
        try:
            elements = []

            ocr_result = await self._call_tool("get_all_screen_text", {})
            if ocr_result and ocr_result.get("texts"):
                for i, text_item in enumerate(ocr_result["texts"][:20]):
                    if isinstance(text_item, dict):
                        elements.append({
                            "name": f"text_{i}",
                            "type": "text",
                            "text": text_item.get("text", ""),
                            "x": text_item.get("x", 0),
                            "y": text_item.get("y", 0),
                            "confidence": text_item.get("confidence", 0.0),
                        })

            if not elements:
                log.debug("Screen-Analyse: Keine Elemente gefunden")
                return None

            log.info(f"Screen-Analyse: {len(elements)} Elemente gefunden")

            return {
                "screen_id": "current_screen",
                "elements": elements,
                "anchors": [],
                "current_url": self.current_browser_url,
            }

        except Exception as e:
            log.error(f"Screen-Analyse fehlgeschlagen: {e}")
            return None

    def _normalize_match_text(self, value: str) -> str:
        return re.sub(r"\s+", " ", str(value or "").strip().lower())

    def _observation_contains_text(self, observation: Dict[str, Any], needle: str) -> bool:
        target = self._normalize_match_text(needle)
        if not target:
            return False
        for element in observation.get("elements", []) or []:
            hay = self._normalize_match_text(element.get("text", ""))
            if target in hay:
                return True
        return False

    def _observation_matches_evidence(self, observation: Dict[str, Any], evidence: BrowserStateEvidence) -> bool:
        value = str(evidence.value or "").strip()
        if not value:
            return False
        if evidence.evidence_type == "url_contains":
            current_url = str(observation.get("current_url", "") or "")
            return value.lower() in current_url.lower()
        if evidence.evidence_type == "visible_text":
            return self._observation_contains_text(observation, value)
        if evidence.evidence_type == "dom_selector":
            selector = value.lower()
            if selector in {"input", "textarea", "password"}:
                return any(
                    token in self._normalize_match_text(element.get("text", ""))
                    for element in observation.get("elements", []) or []
                    for token in ("suche", "search", "email", "e-mail", "name", "nachricht", "passwort", "password")
                )
            if selector in {"results", "autocomplete"}:
                return any(
                    token in self._normalize_match_text(element.get("text", ""))
                    for element in observation.get("elements", []) or []
                    for token in ("ergebnisse", "results", "hotels", "unterkünfte", "unterkuenfte")
                )
            return self._observation_contains_text(observation, value)
        if evidence.evidence_type == "visual_marker":
            marker = value.lower()
            if marker == "calendar":
                return any(
                    token in self._normalize_match_text(element.get("text", ""))
                    for element in observation.get("elements", []) or []
                    for token in ("mär", "maerz", "march", "apr", "mai", "jun", "jul", "aug", "sep", "okt", "nov", "dez")
                )
            if marker == "password-filled":
                return True
            return self._observation_contains_text(observation, value)
        return False

    async def _verify_structured_step(self, step: BrowserWorkflowStep) -> Dict[str, Any]:
        observation = await self._analyze_current_screen() or {"elements": [], "current_url": self.current_browser_url}
        matched = [
            f"{evidence.evidence_type}={evidence.value}"
            for evidence in step.success_signal
            if self._observation_matches_evidence(observation, evidence)
        ]
        return {
            "success": bool(matched),
            "matched_signals": matched,
            "observation": observation,
        }

    async def _locate_target_coordinates(self, target_text: str, strategy: str) -> Optional[Dict[str, Any]]:
        safe_target = str(target_text or "").strip()
        if not safe_target:
            return None
        if strategy == "vision_scan":
            await self._call_tool(
                "scan_ui_elements",
                {"element_types": ["button", "input", "text"], "use_zoom": False},
            )
        elif strategy == "roi_shift":
            await self._detect_dynamic_ui_and_set_roi(safe_target)
        fuzzy_threshold = 85 if strategy == "dom_lookup" else 65
        try:
            result = await self._call_tool(
                "find_text_coordinates",
                {"text_to_find": safe_target, "fuzzy_threshold": fuzzy_threshold},
            )
            if isinstance(result, dict) and result.get("found"):
                return result
        except Exception as e:
            log.debug("Target-Lokalisierung fehlgeschlagen (%s): %s", strategy, e)
        return None

    def _build_fallback_chain(self, step: BrowserWorkflowStep) -> List[str]:
        chain = [step.fallback_strategy]
        for strategy in ("dom_lookup", "ocr_lookup", "vision_scan", "roi_shift"):
            if strategy not in chain:
                chain.append(strategy)
        if "state_backtrack" not in chain:
            chain.append("state_backtrack")
        if "abort_with_handoff" not in chain:
            chain.append("abort_with_handoff")
        return chain

    async def _execute_structured_step(self, step: BrowserWorkflowStep) -> Dict[str, Any]:
        if step.action == "navigate":
            target_url = step.target_text
            if target_url and not target_url.startswith("http"):
                target_url = f"https://{target_url}"
            self.current_browser_url = target_url
            result = await self._call_tool(
                "start_visual_browser",
                {
                    "url": target_url,
                    "browser_type": self.current_browser_type or "firefox",
                    **(
                        {"profile_name": self.current_broker_profile}
                        if (self.current_browser_type or "firefox") == "chrome" and self.current_broker_profile
                        else {}
                    ),
                },
            )
            verify = await self._verify_structured_step(step)
            return {
                "success": bool(result and result.get("success", True)) and verify["success"],
                "strategy": "direct_navigate",
                "verification_result": verify,
            }

        if step.action == "verify_state":
            verify = await self._verify_structured_step(step)
            return {
                "success": verify["success"],
                "strategy": "verify_state",
                "verification_result": verify,
            }

        fallback_chain = self._build_fallback_chain(step)
        for strategy in fallback_chain:
            if strategy == "state_backtrack":
                verify = await self._verify_structured_step(step)
                if verify["success"]:
                    return {
                        "success": True,
                        "strategy": strategy,
                        "verification_result": verify,
                    }
                continue
            if strategy == "abort_with_handoff":
                return {
                    "success": False,
                    "strategy": strategy,
                    "verification_result": {"success": False, "matched_signals": []},
                }

            located = await self._locate_target_coordinates(step.target_text, strategy)
            if not located:
                continue

            x = int(located.get("x", 0))
            y = int(located.get("y", 0))
            if step.action in {"dismiss_cookie", "select_option", "open_panel", "click_target", "submit", "focus_input"}:
                await self._call_tool("click_at", {"x": x, "y": y})
                if step.action == "submit":
                    await self._wait_stable("click_at")
            elif step.action == "type_text":
                await self._call_tool("click_at", {"x": x, "y": y})
                method = self._preferred_text_entry_method(step.target_text)
                await self._call_tool(
                    "type_text",
                    {"text_to_type": step.target_text, "press_enter_after": False, "method": method},
                )

            verify = await self._verify_structured_step(step)
            if verify["success"]:
                return {
                    "success": True,
                    "strategy": strategy,
                    "verification_result": verify,
                }
        return {
            "success": False,
            "strategy": fallback_chain[-1],
            "verification_result": {"success": False, "matched_signals": []},
        }

    async def _execute_structured_workflow_plan(self, plan: BrowserWorkflowPlan) -> Dict[str, Any]:
        execution_log: List[Dict[str, Any]] = []
        current_state = plan.initial_state
        plan_id = f"{plan.flow_type}-{int(time.time() * 1000)}"

        for index, step in enumerate(plan.steps, start=1):
            result = await self._execute_structured_step(step)
            verification = result.get("verification_result", {}) or {}
            success = bool(result.get("success"))
            if success:
                current_state = step.expected_state
            log.info(
                "StructuredBrowserStep plan_id=%s step=%d action=%s expected_state=%s strategy=%s success=%s matched=%s",
                plan_id,
                index,
                step.action,
                step.expected_state,
                result.get("strategy", ""),
                success,
                verification.get("matched_signals", []),
            )
            execution_log.append(
                {
                    "plan_id": plan_id,
                    "step_number": index,
                    "current_state": current_state,
                    "action": step.action,
                    "strategy": result.get("strategy", ""),
                    "fallback_reason": "" if success else "step_failed",
                    "verification_result": verification,
                }
            )
            if not success:
                return {
                    "success": False,
                    "error": f"Structured step failed: {step.action}",
                    "completed_steps": execution_log,
                    "current_state": current_state,
                    "plan_id": plan_id,
                }

        return {
            "success": True,
            "result": f"{plan.flow_type} erfolgreich ausgeführt",
            "completed_steps": execution_log,
            "current_state": current_state,
            "plan_id": plan_id,
        }

    def _infer_service_from_browser_url(self, url: str) -> str:
        host = str(url or "").strip().lower()
        if not host:
            return ""
        host = host.replace("https://", "").replace("http://", "").split("/")[0]
        if host.startswith("www."):
            host = host[4:]
        if host.startswith("x.com") or host.startswith("twitter.com"):
            return "x"
        if host.endswith("github.com"):
            return "github"
        if host.endswith("linkedin.com"):
            return "linkedin"
        if host.endswith("outlook.com") or host.endswith("live.com"):
            return "outlook"
        if host.endswith("booking.com"):
            return "booking"
        if "." in host:
            return host.split(".")[0]
        return host

    async def _execute_user_mediated_login_plan(
        self,
        plan: BrowserWorkflowPlan,
        *,
        handoff: Optional[DelegationHandoff],
        effective_task: str,
    ) -> Dict[str, Any]:
        execution_log: List[Dict[str, Any]] = []
        current_state = plan.initial_state
        plan_id = f"{plan.flow_type}-{int(time.time() * 1000)}"
        prefix_steps: List[BrowserWorkflowStep] = []
        source_url, service = self._resolve_login_target(handoff, effective_task)
        lane = self._resolve_login_lane(handoff=handoff, auth_session=None, url=source_url)

        for step in plan.steps:
            prefix_steps.append(step)
            if step.expected_state == "login_modal":
                break

        for index, step in enumerate(prefix_steps, start=1):
            result = await self._execute_structured_step(step)
            verification = result.get("verification_result", {}) or {}
            success = bool(result.get("success"))
            if success:
                current_state = step.expected_state
            execution_log.append(
                {
                    "plan_id": plan_id,
                    "step_number": index,
                    "current_state": current_state,
                    "action": step.action,
                    "strategy": result.get("strategy", ""),
                    "fallback_reason": "" if success else "step_failed",
                    "verification_result": verification,
                }
            )
            if not success:
                verification = await self._detect_authenticated_session_state(service)
                if verification.get("success"):
                    return self._build_goal_satisfied_login_result(
                        service=service,
                        url=source_url,
                        workflow_id="",
                        lane=lane,
                        verification=verification,
                        execution_log=execution_log,
                        current_state=current_state,
                        plan_id=plan_id,
                    )
                return {
                    "success": False,
                    "error": f"Structured step failed: {step.action}",
                    "completed_steps": execution_log,
                    "current_state": current_state,
                    "plan_id": plan_id,
                }

        verification = await self._detect_authenticated_session_state(service)
        if verification.get("success") and current_state != "login_modal":
            return self._build_goal_satisfied_login_result(
                service=service,
                url=source_url,
                workflow_id="",
                lane=lane,
                verification=verification,
                execution_log=execution_log,
                current_state=current_state,
                plan_id=plan_id,
            )

        workflow_payload = build_user_mediated_login_workflow_payload(
            service=service,
            url=source_url,
            domain=lane["domain"],
            preferred_browser=lane["browser_type"],
            credential_broker=lane["credential_broker"],
            broker_profile=lane["broker_profile"],
            message=(
                "Die Login-Maske ist bereit. Bitte fuehre den Login jetzt selbst im Browser aus; "
                "Timus stoppt hier bewusst vor Benutzername, Passwort und 2FA."
            ),
            user_action_required=(
                (
                    f"Bitte nutze den Chrome-Passwortmanager oder gib Benutzername, Passwort und ggf. 2FA selbst bei {service or 'dem Dienst'} ein."
                    if lane["credential_broker"] == "chrome_password_manager"
                    else f"Bitte gib Benutzername, Passwort und ggf. 2FA selbst bei {service or 'dem Dienst'} ein."
                )
            ),
            resume_hint=(
                "Sage danach 'weiter', 'ich bin eingeloggt' oder beschreibe die sichtbare Challenge, "
                "damit Timus kontrolliert fortsetzen kann."
            ),
        )
        self._emit_user_action_blocker(workflow_payload, stage="await_login_completion")
        return {
            **workflow_payload,
            "status": "awaiting_user",
            "success": False,
            "result": str(workflow_payload.get("message") or "").strip(),
            "completed_steps": execution_log,
            "current_state": current_state,
            "plan_id": plan_id,
            "metadata": {
                "phase_d_workflow": workflow_payload,
            },
        }

    async def _create_navigation_plan_with_llm(self, task: str, screen_state: Dict) -> Optional[Dict]:
        try:
            elements = screen_state.get("elements", [])
            if not elements:
                log.warning("Keine Elemente fuer ActionPlan verfuegbar")
                return None

            element_list = []
            for i, elem in enumerate(elements[:15]):
                text = elem.get("text", "").strip()
                if text:
                    element_list.append({
                        "name": elem.get("name", f"elem_{i}"),
                        "text": text[:50],
                        "x": elem.get("x", 0),
                        "y": elem.get("y", 0),
                        "type": elem.get("type", "unknown"),
                    })

            if not element_list:
                log.warning("Keine Elemente mit Text gefunden")
                return None

            element_summary = "\n".join([
                f"{i+1}. {e['name']}: \"{e['text']}\" at ({e['x']}, {e['y']})"
                for i, e in enumerate(element_list)
            ])

            prompt = f"""Erstelle einen ACTION-PLAN fuer diese Aufgabe:

AUFGABE: {task}

VERFUEGBARE ELEMENTE:
{element_summary}

BEISPIEL ACTION-PLAN:
{{
  "task_id": "search_task",
  "description": "Google suchen nach Python",
  "steps": [
    {{"op": "type", "target": "elem_2", "value": "Python", "retries": 2}},
    {{"op": "click", "target": "elem_5", "retries": 2}}
  ]
}}

Antworte NUR mit JSON (keine Markdown, keine Erklaerung):"""

            old_model = self.model
            old_provider = self.provider

            self.model, self.provider = resolve_model_provider_env(
                model_env="REASONING_MODEL",
                provider_env="REASONING_MODEL_PROVIDER",
                fallback_model="qwen/qwq-32b",
                fallback_provider=ModelProvider.OPENROUTER,
            )

            old_thinking = os.environ.get("NEMOTRON_ENABLE_THINKING")
            os.environ["NEMOTRON_ENABLE_THINKING"] = "true"

            try:
                response = await self._call_llm([
                    {"role": "user", "content": prompt}
                ])
            finally:
                self.model = old_model
                self.provider = old_provider
                if old_thinking is not None:
                    os.environ["NEMOTRON_ENABLE_THINKING"] = old_thinking
                else:
                    os.environ.pop("NEMOTRON_ENABLE_THINKING", None)

            plan = extract_json_robust(response)
            if not isinstance(plan, dict):
                log.warning(f"Kein valides JSON gefunden in Response: {response[:200]}")
                return None

            if not plan.get("steps") or not isinstance(plan["steps"], list):
                log.warning("ActionPlan hat keine Steps")
                return None

            compatible_plan = {
                "goal": plan.get("description", task),
                "screen_id": screen_state.get("screen_id", "current_screen"),
                "steps": [],
            }

            for step in plan["steps"]:
                compatible_step = {
                    "op": step.get("op", "click"),
                    "target": step.get("target", ""),
                    "params": {},
                    "verify_before": [],
                    "verify_after": [],
                    "retries": step.get("retries", 2),
                }
                if "value" in step:
                    compatible_step["params"]["text"] = step["value"]
                compatible_plan["steps"].append(compatible_step)

            log.info(f"ActionPlan erstellt: {compatible_plan['goal']} ({len(compatible_plan['steps'])} Steps)")
            return compatible_plan

        except Exception as e:
            log.error(f"ActionPlan-Erstellung fehlgeschlagen: {e}")
            return None

    async def _try_structured_navigation(
        self,
        task: str,
        *,
        handoff: Optional[DelegationHandoff] = None,
        auth_session: Optional[dict[str, str]] = None,
    ) -> Optional[Dict]:
        try:
            log.info("Versuche strukturierte Navigation...")

            if self.current_structured_workflow_plan:
                if self.current_structured_workflow_plan.flow_type == "login_flow":
                    reused_result = await self._try_reuse_authenticated_session(
                        auth_session or {},
                        handoff=handoff,
                        effective_task=task,
                    )
                    if reused_result:
                        return reused_result
                    return await self._execute_user_mediated_login_plan(
                        self.current_structured_workflow_plan,
                        handoff=handoff,
                        effective_task=task,
                    )
                structured_result = await self._execute_structured_workflow_plan(
                    self.current_structured_workflow_plan
                )
                if structured_result.get("success"):
                    return structured_result

            screen_state = await self._analyze_current_screen()
            if not screen_state or not screen_state.get("elements"):
                log.info("Keine Elemente gefunden, Fallback zu Vision")
                return None

            action_plan = await self._create_navigation_plan_with_llm(task, screen_state)
            if not action_plan:
                log.info("ActionPlan-Erstellung fehlgeschlagen, Fallback zu Vision")
                return None

            log.info(f"Fuehre ActionPlan aus: {action_plan.get('description', 'N/A')}")
            result = await self._call_tool("execute_action_plan", {"plan_dict": action_plan})

            if result and result.get("success"):
                return {
                    "success": True,
                    "result": action_plan.get("description", "Aufgabe erfolgreich"),
                    "state": screen_state,
                }
            else:
                log.warning(f"ActionPlan fehlgeschlagen: {result.get('error', 'Unknown')}")
                return None

        except Exception as e:
            log.error(f"Strukturierte Navigation fehlgeschlagen: {e}")
            return None

    async def run(self, task: str) -> Any:
        pending_login_resume = self._extract_pending_login_resume_context(task)
        if pending_login_resume and pending_login_resume.get("source_agent") in {"", "visual", "visual_login", "visual_nemotron"}:
            return await self._resume_user_mediated_login(pending_login_resume)
        handoff = parse_delegation_handoff(task)
        auth_session_context = self._extract_auth_session_context(task, handoff=handoff)
        effective_task, handoff_context = self._prepare_visual_task(task)
        specialist_context_payload = (
            extract_specialist_context_from_handoff_data(handoff.handoff_data) if handoff else {}
        )
        alignment = assess_specialist_context_alignment(
            current_task=(
                (handoff.handoff_data.get("original_user_task") or "") if handoff else ""
            )
            or ((handoff.handoff_data.get("target_hint") or "") if handoff else "")
            or effective_task,
            payload=specialist_context_payload,
        )
        response_mode = str(specialist_context_payload.get("response_mode") or "").strip().lower()
        if handoff and response_mode == "summarize_state" and self._handoff_requires_visual_action(handoff, effective_task):
            return format_specialist_signal_response(
                "needs_meta_reframe",
                reason="state_mode_conflicts_with_visual_action",
                message=(
                    "Der aktuelle Visual-Handoff verlangt eine echte UI- oder Browser-Aktion, "
                    "waehrend Meta gerade im Zusammenfassungsmodus ist. "
                    "Meta sollte erst zwischen Statuszusammenfassung und Visual-Ausfuehrung entscheiden."
                ),
            )
        if handoff and alignment.get("alignment_state") == "needs_meta_reframe":
            return format_specialist_signal_response(
                "needs_meta_reframe",
                reason=str(alignment.get("reason") or ""),
                message=(
                    "Der aktuelle Visual-Handoff ist nicht stabil genug am laufenden Themenanker verankert. "
                    "Meta sollte die UI-Aufgabe erst genauer neu rahmen."
                ),
            )
        log.info(f"VisualAgent: {effective_task}")
        self.current_browser_type = "firefox"
        self.current_credential_broker = ""
        self.current_broker_profile = ""
        self.current_broker_domain = ""
        selected_strategy = self._choose_visual_strategy_mode(handoff, specialist_context_payload, effective_task)
        if handoff:
            record_autonomy_observation(
                "specialist_strategy_selected",
                {
                    "agent": "visual",
                    "strategy_mode": selected_strategy,
                    "response_mode": response_mode,
                    "session_id": str(handoff.handoff_data.get("session_id") or ""),
                },
            )
        browser_plan_context = self._build_browser_plan_context(effective_task)
        user_sections = [f"AUFGABE: {effective_task}"]
        if handoff_context:
            user_sections.append(handoff_context)
        if browser_plan_context:
            user_sections.append(browser_plan_context)
        self.history = [
            {"role": "system", "content": self.system_prompt},
            {
                "role": "user",
                "content": "\n\n".join(user_sections),
            },
        ]

        roi_set = await self._detect_dynamic_ui_and_set_roi(effective_task)

        consecutive_loops = 0
        force_vision_mode = False
        runtime_feedback_recorded = False

        if selected_strategy == "structured_navigation":
            source_url, _service = self._resolve_login_target(handoff, effective_task)
            self._set_login_lane(
                self._resolve_login_lane(
                    handoff=handoff,
                    auth_session=auth_session_context,
                    url=source_url,
                )
            )
            structured_result = await self._try_structured_navigation(
                effective_task,
                handoff=handoff,
                auth_session=auth_session_context,
            )
            if structured_result:
                structured_result = await self._normalize_login_flow_success_result(
                    structured_result,
                    handoff=handoff,
                    effective_task=effective_task,
                )
                if structured_result.get("success"):
                    log.info(f"Strukturierte Navigation erfolgreich: {structured_result['result']}")
                    if roi_set:
                        self._clear_roi()
                    self._record_runtime_feedback(effective_task, success=True, strategy="browser_flow", stage="structured_navigation")
                    runtime_feedback_recorded = True
                    return structured_result["result"]
                pending_status = str(structured_result.get("status") or "").strip().lower()
                if pending_status in {"approval_required", "auth_required", "awaiting_user", "challenge_required"}:
                    if roi_set:
                        self._clear_roi()
                    self._record_runtime_feedback(
                        effective_task,
                        success=False,
                        strategy="browser_flow",
                        stage=f"structured_navigation_{pending_status}",
                    )
                    runtime_feedback_recorded = True
                    return structured_result
            log.info("Fallback zu Vision-basierter Navigation")
        else:
            log.info("D0.9 Strategy: Vision-first statt strukturierter Navigation")

        for iteration in range(self.max_iterations):
            if consecutive_loops >= 2:
                log.warning(f"Loop-Recovery: {consecutive_loops} consecutive Loops - forciere Vision-Mode")
                force_vision_mode = True
                consecutive_loops = 0

            if iteration > 0 and self.use_screen_change_gate and not force_vision_mode:
                should_analyze = await self._should_analyze_screen(roi=self.current_roi)
                if not should_analyze:
                    log.debug(f"Iteration {iteration+1}: Screen unveraendert, ueberspringe Screenshot")
                    await asyncio.sleep(0.2)
                    continue

            if force_vision_mode:
                log.info("Force-Vision-Mode: Screenshot erzwingen trotz Screen-Change-Gate")
                force_vision_mode = False

            screenshot = await asyncio.to_thread(self._get_screenshot_as_base64)
            if not screenshot:
                if not runtime_feedback_recorded:
                    self._record_runtime_feedback(effective_task, success=False, stage="screenshot_capture")
                    runtime_feedback_recorded = True
                return "Screenshot-Fehler"

            self.last_screen_analysis_time = time.time()

            messages = self.history + [{
                "role": "user",
                "content": [
                    {"type": "text", "text": "Aktueller Screenshot. Naechster Schritt?"},
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{screenshot}"}},
                ],
            }]

            reply = await self._call_llm(messages)

            if "Final Answer:" in reply:
                if roi_set:
                    self._clear_roi()
                if not runtime_feedback_recorded:
                    self._record_runtime_feedback(effective_task, success=True, stage="vision_final_answer")
                    runtime_feedback_recorded = True
                return reply.split("Final Answer:")[1].strip()

            action, err = self._parse_action(reply)
            if not action:
                self.history.append({"role": "user", "content": f"Fehler: {err}"})
                continue

            method = action.get("method", "")
            params = action.get("params", {})

            if method == "finish_task":
                if roi_set:
                    self._clear_roi()
                if not runtime_feedback_recorded:
                    self._record_runtime_feedback(effective_task, success=True, strategy="browser_flow", stage="finish_task")
                    runtime_feedback_recorded = True
                return params.get("message", "Fertig")

            if method in ["click_at", "type_text", "start_visual_browser", "open_application"]:
                await self._capture_before()

            obs = await self._call_tool(method, params)

            if isinstance(obs, dict) and "_loop_warning" in obs:
                consecutive_loops += 1
                log.warning(f"Loop-Warnung erhalten ({consecutive_loops}x): {obs['_loop_warning']}")
                obs["_info"] = self._build_loop_recovery_hint(method)
                if method == "scan_ui_elements":
                    force_vision_mode = True
                    if consecutive_loops >= 2 and not runtime_feedback_recorded:
                        self._record_runtime_feedback(
                            effective_task,
                            success=False,
                            strategy=self._preferred_recovery_strategy(),
                            stage="scan_ui_loop",
                        )
                        runtime_feedback_recorded = True
            else:
                consecutive_loops = 0

            if method in ["click_at", "type_text", "start_visual_browser", "open_application"]:
                if not await self._verify_action(method):
                    self.history.append({"role": "assistant", "content": reply})
                    self.history.append({"role": "user", "content": "Nicht verifiziert. Anderen Ansatz versuchen."})
                    continue
                await self._wait_stable(method)

            self._handle_file_artifacts(obs)
            self.history.append({"role": "assistant", "content": reply})
            self.history.append({"role": "user", "content": f"Observation: {json.dumps(self._sanitize_observation(obs), ensure_ascii=False)}"})
            await asyncio.sleep(0.5)

        if roi_set:
            self._clear_roi()

        if not runtime_feedback_recorded:
            self._record_runtime_feedback(effective_task, success=False, stage="max_iterations")
            runtime_feedback_recorded = True
        return "Max Iterationen."

    def _handoff_requires_visual_action(self, handoff: DelegationHandoff, effective_task: str) -> bool:
        if handoff.handoff_data.get("source_url") or handoff.handoff_data.get("results_url"):
            return True
        if handoff.handoff_data.get("browser_plan") or handoff.handoff_data.get("expected_state"):
            return True
        target_hint = str(handoff.handoff_data.get("target_hint") or "").strip().lower()
        if target_hint:
            return True
        task_lower = str(effective_task or "").strip().lower()
        return any(
            token in task_lower
            for token in (
                "browser",
                "website",
                "webseite",
                "formular",
                "login",
                "anmelden",
                "oeffne",
                "öffne",
                "klicke",
                "click",
                ".com",
                ".de",
            )
        )

    def _choose_visual_strategy_mode(
        self,
        handoff: Optional[DelegationHandoff],
        specialist_context_payload: dict,
        effective_task: str,
    ) -> str:
        preference_text = " | ".join(str(item or "").strip().lower() for item in specialist_context_payload.get("user_preferences") or [])
        guidance_text = " | ".join(
            str(item or "").strip().lower()
            for item in (
                specialist_context_payload.get("next_expected_step"),
                specialist_context_payload.get("open_loop"),
                specialist_context_payload.get("active_goal"),
            )
            if str(item or "").strip()
        )
        if any(token in preference_text or token in guidance_text for token in ("ocr", "text", "text zuerst", "screen text", "lesen", "lies", "lese")):
            return "vision_first"
        if handoff and self._handoff_requires_visual_action(handoff, effective_task):
            return "structured_navigation"
        return "vision_first"
