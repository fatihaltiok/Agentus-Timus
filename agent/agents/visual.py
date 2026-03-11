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
from agent.prompts import VISUAL_SYSTEM_PROMPT
from agent.shared.json_utils import extract_json_robust
from agent.shared.vision_formatter import convert_openai_to_anthropic
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

        self.current_structured_workflow_plan = build_structured_browser_workflow_plan(
            task_text,
            self._extract_browser_url(task_text),
        )
        self.current_workflow_plan = build_browser_workflow_plan(
            task_text,
            self._extract_browser_url(task_text),
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
            result = await self._call_tool("start_visual_browser", {"url": target_url})
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
                await self._call_tool(
                    "type_text",
                    {"text_to_type": step.target_text, "press_enter_after": False, "method": "write"},
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

            self.model = os.getenv("REASONING_MODEL", "nvidia/nemotron-3-nano-30b-a3b")
            self.provider = ModelProvider.OPENROUTER

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

    async def _try_structured_navigation(self, task: str) -> Optional[Dict]:
        try:
            log.info("Versuche strukturierte Navigation...")

            if self.current_structured_workflow_plan:
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

    async def run(self, task: str) -> str:
        log.info(f"VisualAgent: {task}")
        browser_plan_context = self._build_browser_plan_context(task)
        self.history = [
            {"role": "system", "content": self.system_prompt},
            {
                "role": "user",
                "content": (
                    f"AUFGABE: {task}\n\n{browser_plan_context}"
                    if browser_plan_context
                    else f"AUFGABE: {task}"
                ),
            },
        ]

        roi_set = await self._detect_dynamic_ui_and_set_roi(task)

        consecutive_loops = 0
        force_vision_mode = False
        runtime_feedback_recorded = False

        structured_result = await self._try_structured_navigation(task)
        if structured_result and structured_result.get("success"):
            log.info(f"Strukturierte Navigation erfolgreich: {structured_result['result']}")
            if roi_set:
                self._clear_roi()
            self._record_runtime_feedback(task, success=True, strategy="browser_flow", stage="structured_navigation")
            runtime_feedback_recorded = True
            return structured_result["result"]
        else:
            log.info("Fallback zu Vision-basierter Navigation")

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
                    self._record_runtime_feedback(task, success=False, stage="screenshot_capture")
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
                    self._record_runtime_feedback(task, success=True, stage="vision_final_answer")
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
                    self._record_runtime_feedback(task, success=True, strategy="browser_flow", stage="finish_task")
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
                            task,
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
            self._record_runtime_feedback(task, success=False, stage="max_iterations")
            runtime_feedback_recorded = True
        return "Max Iterationen."
