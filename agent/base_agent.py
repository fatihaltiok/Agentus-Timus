"""BaseAgent Klasse mit Multi-Provider Support.

Enthaelt die Basisklasse fuer alle Timus-Agenten mit:
- Multi-Provider LLM Calls
- Loop-Detection
- Screen-Change-Gate
- ROI Management
- Strukturierte Navigation
- Post-Task Reflection (v2.0)
"""

import logging
import os
import json
import asyncio
import base64
import re
import subprocess
import platform
import time
from datetime import datetime
from typing import Dict, Any, List, Optional, Tuple, Callable

import httpx

from agent.providers import (
    ModelProvider,
    AgentModelConfig,
    get_provider_client,
)
from agent.shared.mcp_client import MCPClient
from agent.shared.screenshot import capture_screenshot_base64
from agent.shared.action_parser import parse_action
from agent.shared.vision_formatter import build_openai_vision_message
from agent.shared.json_utils import extract_json_robust

from utils.openai_compat import prepare_openai_params
from utils.policy_gate import check_tool_policy
from agent.dynamic_tool_mixin import DynamicToolMixin
from tools.tool_registry_v2 import registry_v2, ValidationError
from orchestration.lane_manager import lane_manager, Lane, LaneStatus
from utils.context_guard import ContextGuard, ContextStatus

log = logging.getLogger("TimusAgent-v4.4")

MCP_URL = "http://127.0.0.1:5000"
IMAGE_MODEL_NAME = os.getenv("IMAGE_GENERATION_MODEL", "gpt-image-1.5-2025-12-16")


AGENT_CAPABILITY_MAP = {
    "executor": None,  # Alle Tools
    "research": ["search", "document", "memory"],
    "reasoning": ["search", "document", "memory", "code"],
    "creative": ["creative", "document", "voice"],
    "meta": None,  # Alle Tools
    "visual": ["browser", "vision", "mouse", "ui"],
    "development": ["code", "file", "search"],
}


class BaseAgent(DynamicToolMixin):
    """Basisklasse fuer alle Agenten mit Multi-Provider Support und DynamicToolMixin."""

    def __init__(
        self,
        system_prompt_template: str,
        tools_description_string: str,
        max_iterations: int = 30,
        agent_type: str = "executor",
        lane_id: Optional[str] = None,
    ):
        self.max_iterations = max_iterations
        self.agent_type = agent_type
        self.lane_id = lane_id
        self._lane: Optional[Lane] = None

        # DynamicToolMixin initialisieren
        capabilities = AGENT_CAPABILITY_MAP.get(agent_type)
        self.init_dynamic_tools(
            capabilities=capabilities, max_iterations=max_iterations
        )
        self.http_client = httpx.AsyncClient(timeout=300.0)
        self.recent_actions: List[str] = []
        self.last_skip_times: Dict[str, float] = {}
        self.action_call_counts: Dict[str, int] = {}
        self._remote_tool_names: set[str] = set()
        self._remote_tools_fetched: bool = False
        self.conversation_session_id: Optional[str] = None

        # Multi-Provider Setup
        self.provider_client = get_provider_client()
        self.model, self.provider = AgentModelConfig.get_model_and_provider(agent_type)

        log.info(f"{self.__class__.__name__} | {self.model} | {self.provider.value}")

        self.system_prompt = system_prompt_template.replace(
            "{current_date}", datetime.now().strftime("%d.%m.%Y")
        ).replace("{tools_description}", tools_description_string)

        # Lane-Manager initialisieren
        lane_manager.set_registry(registry_v2)

        # Screen-Change-Gate Support (v1.0)
        self.use_screen_change_gate = (
            os.getenv("USE_SCREEN_CHANGE_GATE", "false").lower() == "true"
        )
        self.cached_screen_state: Optional[Dict] = None
        self.last_screen_analysis_time: float = 0
        self._last_screen_check_time: float = 0.0

        # ROI (Region of Interest) Support (v2.0)
        self.roi_stack: List[Dict] = []
        self.current_roi: Optional[Dict] = None

        # Context-Window-Guard (v3.0)
        self._context_guard = ContextGuard(
            max_tokens=int(os.getenv('MAX_CONTEXT_TOKENS', '128000')),
            max_output_tokens=int(os.getenv('MAX_OUTPUT_TOKENS', '8000')),
        )

        # Multimodal Vision Support
        self._vision_enabled = False
        try:
            import mss as _mss
            from PIL import Image as _PILImage

            self._vision_enabled = True
        except ImportError:
            pass

        # Post-Task Reflection Support (v2.0)
        self._reflection_enabled = os.getenv("REFLECTION_ENABLED", "true").lower() == "true"
        self._reflection_engine = None
        self._task_action_history: List[Dict[str, Any]] = []
        self._working_memory_last_meta: Dict[str, Any] = {}
        self._memory_recall_last_meta: Dict[str, Any] = {}
        self._run_started_at: float = 0.0
        self._live_status_enabled = (
            os.getenv("TIMUS_LIVE_STATUS", "true").lower() in {"1", "true", "yes", "on"}
        )
        self._step_trace_enabled = (
            os.getenv("TIMUS_STEP_TRACE", "true").lower() in {"1", "true", "yes", "on"}
        )
        self._audit_step_logger: Optional[Callable[..., None]] = None
        self._active_phase = "idle"
        self._active_tool_name: Optional[str] = None

        if self.use_screen_change_gate:
            log.info(f"Screen-Change-Gate AKTIV fuer {self.__class__.__name__}")

    def _emit_live_status(
        self,
        phase: str,
        detail: str = "",
        step: Optional[int] = None,
        total_steps: Optional[int] = None,
        tool_name: Optional[str] = None,
    ) -> None:
        """Kompakte Live-Statusanzeige fuer Terminal-User."""
        self._active_phase = phase
        if tool_name is not None:
            self._active_tool_name = tool_name
        elif not phase.startswith("tool_"):
            # Nur waehrend Tool-Phasen einen aktiven Tool-Namen anzeigen.
            self._active_tool_name = None
        if not self._live_status_enabled:
            return

        ts = datetime.now().strftime("%H:%M:%S")
        step_txt = ""
        if step is not None and total_steps is not None:
            step_txt = f" | Step {step}/{total_steps}"
        tool_txt = ""
        if self._active_tool_name:
            tool_txt = f" | Tool {self._active_tool_name}"
        detail_txt = f" | {detail}" if detail else ""
        print(
            f"   ⏱️ Status [{ts}] | Agent {self.agent_type.upper()} | {phase.upper()}{step_txt}{tool_txt}{detail_txt}"
        )

    def set_audit_step_logger(self, logger_fn: Optional[Callable[..., None]]) -> None:
        """Setzt einen optionalen JSONL-Step-Logger (z.B. AuditLogger.log_step)."""
        self._audit_step_logger = logger_fn

    def _preview_value(self, value: Any, limit: int = 500) -> str:
        """Kompakte, einzeilige Vorschau fuer Logs."""
        try:
            if isinstance(value, str):
                text = value
            else:
                text = json.dumps(value, ensure_ascii=False, default=str)
        except Exception:
            text = str(value)
        text = text.replace("\n", "\\n")
        if len(text) > limit:
            return text[:limit] + "...<truncated>"
        return text

    def _emit_step_trace(
        self,
        action: str,
        input_data: Any = None,
        output_data: Any = None,
        status: str = "ok",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Schreibt feingranulare Run-Schritte ins Audit-JSONL (wenn aktiv)."""
        if not self._step_trace_enabled or not self._audit_step_logger:
            return
        try:
            self._audit_step_logger(
                action=action,
                input_data=input_data,
                output_data=output_data,
                status=status,
                metadata=metadata,
            )
        except Exception as e:
            log.debug(f"Step-Trace Logging fehlgeschlagen: {e}")

    # ------------------------------------------------------------------
    # Screenshot + Vision (delegiert an shared utilities)
    # ------------------------------------------------------------------

    def _capture_screenshot_base64(self) -> str:
        """Macht Screenshot und gibt Base64-String zurueck."""
        if not self._vision_enabled:
            return ""
        return capture_screenshot_base64(fmt="JPEG", quality=70)

    def _build_vision_message(self, text: str, screenshot_b64: str) -> dict:
        """Baut eine multimodale User-Message mit Text + Screenshot."""
        return build_openai_vision_message(text, screenshot_b64, detail="low")

    # ------------------------------------------------------------------
    # Observation Sanitizer
    # ------------------------------------------------------------------

    def _sanitize_observation(self, obs: Any) -> Any:
        if isinstance(obs, dict):
            clean = obs.copy()
            for k, v in clean.items():
                if isinstance(v, str) and len(v) > 500:
                    clean[k] = f"<{len(v)} chars>"
                elif isinstance(v, list) and len(v) > 10:
                    clean[k] = v[:10] + [f"... +{len(v) - 10}"]
            return clean
        elif isinstance(obs, str) and len(obs) > 2000:
            return obs[:2000] + "..."
        return obs

    # ------------------------------------------------------------------
    # Loop-Detection
    # ------------------------------------------------------------------

    # System-Tools die Agenten NICHT direkt aufrufen sollen
    # (werden vom Dispatcher/System verwaltet)
    SYSTEM_ONLY_TOOLS = {
        "add_interaction",
        "end_session",
        "get_memory_stats",
    }
    NAVIGATION_TASK_PATTERNS = (
        r"\bbrowser\b",
        r"\bwebsite\b",
        r"\burl\b",
        r"\bklick(?:e|en|t)?\b",
        r"\bclick\b",
        r"\bbooking\b",
        r"\bgoogle\b",
        r"\bamazon\b",
        r"\bnavigat(?:e|ion)\b",
        r"\boeffne\b",
        r"\böffne\b",
        r"\bgehe\s+zu\b",
    )
    MEMORY_QUERY_PATTERNS = (
        r"\bwas\s+habe\s+ich\b.*\bgesuch\w*\b",
        r"\bwas\s+suche\s+ich\b",
        r"\bwas\s+haben\s+wir\b.*\bgesuch\w*\b",
        r"\bvorhin\b.*\bgesuch\w*\b",
        r"\beben\b.*\bgesuch\w*\b",
        r"\berinner\w*\s+du\s+dich\b",
        r"\bwei(?:ss|ß)t\s+du\s+das\s+nicht\s+mehr\b",
    )

    def should_skip_action(
        self, action_name: str, params: dict
    ) -> Tuple[bool, Optional[str]]:
        # System-Tools sofort blockieren
        if action_name in self.SYSTEM_ONLY_TOOLS:
            reason = (
                f"'{action_name}' ist ein System-Tool und darf nicht direkt aufgerufen werden. "
                f"Konzentriere dich auf die eigentliche Aufgabe. "
                f"Wenn du fertig bist: Final Answer: [deine Antwort]"
            )
            log.warning(f"System-Tool blockiert: {action_name}")
            return True, reason

        action_key = f"{action_name}:{json.dumps(params, sort_keys=True)}"

        # Persistenter Counter (vergisst nie)
        self.action_call_counts[action_key] = self.action_call_counts.get(action_key, 0) + 1
        count = self.action_call_counts[action_key]

        COOLDOWN_ACTIONS = {
            "get_all_screen_text": 8.0,
            "type_text": 6.0,
            "read_text_from_screen": 8.0,
        }
        LOW_VALUE_ACTIONS = {"get_all_screen_text", "read_text_from_screen"}

        now = time.time()
        if action_name in COOLDOWN_ACTIONS:
            last_skip = self.last_skip_times.get(action_key, 0)
            if now - last_skip < COOLDOWN_ACTIONS[action_name]:
                reason = (
                    f"Cooldown active for {action_name} ({COOLDOWN_ACTIONS[action_name]}s). "
                    f"Change strategy or tool before retrying."
                )
                log.warning(reason)
                return True, reason

        if action_name in LOW_VALUE_ACTIONS and count >= 3:
            reason = (
                f"Low-value tool '{action_name}' already used {count}x. "
                f"Switch to higher-signal tools (search_web, open_url, analyze_screen_verified)."
            )
            log.warning(reason)
            self.last_skip_times[action_key] = now
            return True, reason

        if count >= 3:
            reason = (
                f"Loop detected: {action_name} wurde bereits {count}x aufgerufen "
                f"mit denselben Parametern. KRITISCH: Aktion wird uebersprungen. "
                f"Versuche anderen Ansatz!"
            )
            log.error(
                f"Kritischer Loop ({count}x): {action_name} - Aktion wird uebersprungen"
            )
            self.last_skip_times[action_key] = now
            return True, reason

        elif count >= 2:
            reason = (
                f"Loop detected: {action_name} wurde bereits {count}x aufgerufen "
                f"mit denselben Parametern. Versuche andere Parameter oder anderen Ansatz."
            )
            log.warning(f"Loop ({count}x): {action_name} - Warnung an Agent")
            self.recent_actions.append(action_key)
            return False, reason

        self.recent_actions.append(action_key)
        if len(self.recent_actions) > 40:
            self.recent_actions.pop(0)

        return False, None

    # ------------------------------------------------------------------
    # Tool Refinement
    # ------------------------------------------------------------------

    def _refine_tool_call(self, method: str, params: dict) -> Tuple[str, dict]:
        if method == "Image Generation":
            params.setdefault("model", IMAGE_MODEL_NAME)
            params.setdefault("size", "1024x1024")
            params.setdefault("quality", "high")

        corrections = {
            "URL Viewer": "start_visual_browser",
            "start_app": "open_application",
            "click": "click_at",
            "deep_research": "start_deep_research",
        }
        if method in corrections:
            method = corrections[method]

        if method == "start_deep_research" and "topic" in params:
            params["query"] = params.pop("topic")

        if method == "click_at" and "x" in params:
            params["x"] = int(params["x"])
            params["y"] = int(params["y"])

        return method, params

    # ------------------------------------------------------------------
    # File Artifacts
    # ------------------------------------------------------------------

    def _handle_file_artifacts(self, observation: dict):
        if not isinstance(observation, dict):
            return
        if os.getenv("AUTO_OPEN_FILES", "true").lower() != "true":
            return

        file_path = (
            observation.get("file_path")
            or observation.get("saved_as")
            or observation.get("filepath")
        )
        if file_path and os.path.exists(file_path):
            log.info(f"Oeffne: {file_path}")
            try:
                if platform.system() == "Windows":
                    os.startfile(file_path)
                elif platform.system() == "Darwin":
                    subprocess.call(["open", file_path])
                else:
                    subprocess.call(["xdg-open", file_path])
            except Exception as e:
                log.warning(f"Oeffnen fehlgeschlagen: {e}")

    # ------------------------------------------------------------------
    # Lane Management
    # ------------------------------------------------------------------

    async def _get_lane(self) -> Lane:
        """Holt oder erstellt die Lane fuer diesen Agenten."""
        if self._lane is None:
            self._lane = await lane_manager.get_or_create_lane(
                self.lane_id or f"{self.agent_type}_{id(self)}"
            )
        return self._lane

    async def _ensure_remote_tool_names(self) -> None:
        """Holt einmalig die Tool-Namen vom Server (lazy)."""
        if self._remote_tools_fetched:
            return

        self._remote_tools_fetched = True
        try:
            resp = await self.http_client.get(
                f"{MCP_URL}/get_tool_schemas/openai",
                timeout=10.0,
            )
            if resp.status_code != 200:
                log.debug(
                    f"Remote-Registry Endpoint antwortet mit Status {resp.status_code}"
                )
                return

            schema_data = resp.json()
            if schema_data.get("status") != "success":
                return

            for tool in schema_data.get("tools", []):
                if not isinstance(tool, dict):
                    continue
                fn = tool.get("function", {})
                if not isinstance(fn, dict):
                    continue
                name = fn.get("name", "")
                if name:
                    self._remote_tool_names.add(name)

            log.info(f"Remote-Registry geladen: {len(self._remote_tool_names)} Tools")
        except Exception as e:
            log.debug(f"Remote-Registry nicht erreichbar (non-critical): {e}")

    # ------------------------------------------------------------------
    # MCP Tool Call (mit Loop-Detection und Lane-Integration)
    # ------------------------------------------------------------------

    async def _call_tool(self, method: str, params: dict) -> dict:
        method, params = self._refine_tool_call(method, params)
        self._emit_live_status(
            phase="tool_active",
            detail=str(params)[:120],
            tool_name=method,
        )

        allowed, policy_reason = check_tool_policy(method, params)
        if not allowed:
            log.error(f"Tool-Call durch Policy blockiert: {method}")
            self._emit_live_status(
                phase="tool_blocked",
                detail="Policy blockiert",
                tool_name=method,
            )
            return {"error": policy_reason, "blocked_by_policy": True}

        await self._ensure_remote_tool_names()

        try:
            registry_v2.validate_tool_call(method, **params)
        except ValidationError as e:
            log.error(f"Parameter-Validierungsfehler fuer {method}: {e}")
            self._emit_live_status(
                phase="tool_error",
                detail=f"Validierungsfehler: {e}",
                tool_name=method,
            )
            return {"error": f"Validierungsfehler: {e}", "validation_failed": True}
        except ValueError:
            if method not in self._remote_tool_names:
                log.warning(f"Tool '{method}' weder lokal noch remote bekannt")
            else:
                log.debug(f"Tool '{method}' remote bekannt - Server validiert")

        should_skip, loop_reason = self.should_skip_action(method, params)

        if should_skip:
            log.error(f"Tool-Call uebersprungen: {method} (Loop)")
            self._emit_live_status(
                phase="tool_skipped",
                detail=loop_reason or "Loop detected",
                tool_name=method,
            )
            return {"skipped": True, "reason": loop_reason or "Loop detected", "_loop_warning": loop_reason or "Loop detected"}

        if loop_reason:
            log.warning(f"Loop-Warnung fuer {method}: {loop_reason}")

        log.info(f"{method} -> {str(params)[:100]}")

        lane = await self._get_lane()
        log.debug(
            f"Lane {lane.lane_id}: Executing {method} (status={lane.status.value})"
        )

        try:
            resp = await self.http_client.post(
                MCP_URL,
                json={"jsonrpc": "2.0", "method": method, "params": params, "id": "1"},
            )
            data = resp.json()

            if "result" in data:
                result = data["result"]
                if loop_reason:
                    if isinstance(result, dict):
                        result["_loop_warning"] = loop_reason
                    else:
                        result = {"value": result, "_loop_warning": loop_reason}
                self._emit_live_status(
                    phase="tool_done",
                    detail="ok",
                    tool_name=method,
                )
                return result

            if "error" in data:
                self._emit_live_status(
                    phase="tool_error",
                    detail=str(data["error"])[:120],
                    tool_name=method,
                )
                return {"error": str(data["error"])}
            self._emit_live_status(
                phase="tool_error",
                detail="Invalid response",
                tool_name=method,
            )
            return {"error": "Invalid response"}
        except Exception as e:
            self._emit_live_status(
                phase="tool_error",
                detail=str(e)[:120],
                tool_name=method,
            )
            return {"error": str(e)}

    # ------------------------------------------------------------------
    # Screen-Change-Gate
    # ------------------------------------------------------------------

    async def _should_analyze_screen(
        self, roi: Optional[Dict] = None, force: bool = False
    ) -> bool:
        if not self.use_screen_change_gate or force:
            return True

        try:
            now = time.time()
            if now - self._last_screen_check_time > 2.0:
                self._last_screen_check_time = now
                return True

            params = {}
            if roi:
                params["roi"] = roi

            result = await self._call_tool("should_analyze_screen", params)

            if result and result.get("changed"):
                log.debug(
                    f"Screen geaendert - {result.get('info', {}).get('reason', 'unknown')}"
                )
                self._last_screen_check_time = now
                return True
            else:
                log.debug("Screen unveraendert - Cache nutzen")
                return False

        except Exception as e:
            log.warning(f"Screen-Change-Gate Fehler: {e}, analysiere sicherheitshalber")
            return True

    async def _get_screen_state(
        self,
        screen_id: str = "current",
        anchor_specs: Optional[List[Dict]] = None,
        element_specs: Optional[List[Dict]] = None,
        force_analysis: bool = False,
    ) -> Optional[Dict]:
        if not force_analysis and not await self._should_analyze_screen():
            if self.cached_screen_state:
                log.debug("Nutze gecachten ScreenState")
                return self.cached_screen_state

        try:
            self.last_screen_analysis_time = time.time()

            params = {
                "screen_id": screen_id,
                "anchor_specs": anchor_specs or [],
                "element_specs": element_specs or [],
                "extract_ocr": False,
            }

            result = await self._call_tool("analyze_screen_state", params)

            if result and not result.get("error"):
                self.cached_screen_state = result
                log.debug(
                    f"ScreenState analysiert: {len(result.get('elements', []))} Elemente"
                )
                return result
            else:
                log.warning(
                    f"Screen-Analyse fehlgeschlagen: {result.get('error', 'unknown')}"
                )
                return None

        except Exception as e:
            log.error(f"Screen-State Fehler: {e}")
            return None

    # ------------------------------------------------------------------
    # Strukturierte Navigation (v2.0)
    # ------------------------------------------------------------------

    async def _analyze_current_screen(self) -> Optional[Dict]:
        try:
            elements = []

            ocr_result = await self._call_tool("get_all_screen_text", {})
            if ocr_result and ocr_result.get("texts"):
                for i, text_item in enumerate(ocr_result["texts"][:20]):
                    if isinstance(text_item, dict):
                        elements.append(
                            {
                                "name": f"text_{i}",
                                "type": "text",
                                "text": text_item.get("text", ""),
                                "x": text_item.get("x", 0),
                                "y": text_item.get("y", 0),
                                "confidence": text_item.get("confidence", 0.0),
                            }
                        )

            if not elements:
                log.debug("Screen-Analyse: Keine Elemente gefunden")
                return None

            log.info(f"Screen-Analyse: {len(elements)} Elemente gefunden")

            return {
                "screen_id": "current_screen",
                "elements": elements,
                "anchors": [],
            }

        except Exception as e:
            log.error(f"Screen-Analyse fehlgeschlagen: {e}")
            return None

    async def _create_navigation_plan_with_llm(
        self, task: str, screen_state: Dict
    ) -> Optional[Dict]:
        import re as _re

        try:
            elements = screen_state.get("elements", [])
            if not elements:
                log.warning("Keine Elemente fuer ActionPlan verfuegbar")
                return None

            element_list = []
            for i, elem in enumerate(elements[:15]):
                text = elem.get("text", "").strip()
                if text:
                    element_list.append(
                        {
                            "name": elem.get("name", f"elem_{i}"),
                            "text": text[:50],
                            "x": elem.get("x", 0),
                            "y": elem.get("y", 0),
                            "type": elem.get("type", "unknown"),
                        }
                    )

            if not element_list:
                log.warning("Keine Elemente mit Text gefunden")
                return None

            element_summary = "\n".join(
                [
                    f'{i + 1}. {e["name"]}: "{e["text"]}" at ({e["x"]}, {e["y"]})'
                    for i, e in enumerate(element_list)
                ]
            )

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
                response = await self._call_llm([{"role": "user", "content": prompt}])
            finally:
                self.model = old_model
                self.provider = old_provider
                if old_thinking is not None:
                    os.environ["NEMOTRON_ENABLE_THINKING"] = old_thinking
                else:
                    os.environ.pop("NEMOTRON_ENABLE_THINKING", None)

            plan = extract_json_robust(response)
            if not plan:
                log.warning(f"Kein JSON gefunden in Response: {response[:200]}")
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

            log.info(
                f"ActionPlan erstellt: {compatible_plan['goal']} ({len(compatible_plan['steps'])} Steps)"
            )
            return compatible_plan

        except json.JSONDecodeError as e:
            log.error(f"JSON-Parsing fehlgeschlagen: {e}")
            return None
        except Exception as e:
            log.error(f"ActionPlan-Erstellung fehlgeschlagen: {e}")
            return None

    async def _try_structured_navigation(self, task: str) -> Optional[Dict]:
        try:
            log.info("Versuche strukturierte Navigation...")

            screen_state = await self._analyze_current_screen()
            if not screen_state or not screen_state.get("elements"):
                log.info("Keine Elemente gefunden - nutze regulaeren Flow")
                return None

            action_plan = await self._create_navigation_plan_with_llm(
                task, screen_state
            )
            if not action_plan:
                log.info("ActionPlan-Erstellung fehlgeschlagen - nutze regulaeren Flow")
                return None

            log.info(f"Fuehre ActionPlan aus: {action_plan.get('goal', 'N/A')}")
            result = await self._call_tool(
                "execute_action_plan", {"plan_dict": action_plan}
            )

            if result and result.get("success"):
                return {
                    "success": True,
                    "result": action_plan.get("goal", "Aufgabe erfolgreich"),
                    "state": screen_state,
                }
            else:
                error_msg = "Unknown"
                if isinstance(result, dict):
                    error_msg = (
                        result.get("error")
                        or result.get("error_message")
                        or result.get("message")
                        or "Unknown"
                    )
                log.warning(
                    f"ActionPlan fehlgeschlagen: {error_msg}"
                )
                return None

        except Exception as e:
            log.error(f"Strukturierte Navigation fehlgeschlagen: {e}")
            return None

    def _is_navigation_task(self, task_lower: str) -> bool:
        """Heuristik: Nur echte Navigation/UI-Aufgaben triggern den Screen-Flow."""
        return any(
            re.search(pattern, task_lower) is not None
            for pattern in self.NAVIGATION_TASK_PATTERNS
        )

    def _is_memory_recall_query(self, task_lower: str) -> bool:
        """Erkennt direkte Rückfragen nach bereits besprochenem Inhalt."""
        return any(
            re.search(pattern, task_lower) is not None
            for pattern in self.MEMORY_QUERY_PATTERNS
        )

    async def _try_memory_recall(self, task: str) -> Optional[str]:
        """Fast-Path für Erinnerungsfragen über das Memory-Tool."""
        try:
            self._memory_recall_last_meta = {}
            recall_params: Dict[str, Any] = {"query": task, "n_results": 5}
            if self.conversation_session_id:
                recall_params["session_id"] = self.conversation_session_id
            recall_result = await self._call_tool("recall", recall_params)

            # Rückwärtskompatibel mit älteren Server-Schemas ohne session_id.
            if (
                isinstance(recall_result, dict)
                and recall_result.get("validation_failed")
                and "session_id" in recall_params
            ):
                recall_result = await self._call_tool(
                    "recall",
                    {"query": task, "n_results": 5},
                )
            if not isinstance(recall_result, dict):
                return None

            if recall_result.get("status") != "success":
                return None
            meta = recall_result.get("meta")
            if isinstance(meta, dict):
                self._memory_recall_last_meta = meta

            memories = recall_result.get("memories", [])
            if not memories:
                return "Ich finde dazu gerade keine passende Erinnerung im Gedächtnis."

            lines = []
            for item in memories[:3]:
                text = str(item.get("text", "")).strip()
                if not text:
                    continue
                score = item.get("relevance_score")
                if isinstance(score, (int, float)):
                    lines.append(f"- {text} (Relevanz {score:.2f})")
                else:
                    lines.append(f"- {text}")

            if not lines:
                return "Ich habe Erinnerungen gefunden, aber ohne verwertbaren Text."

            return "Das habe ich im Gedächtnis gefunden:\n" + "\n".join(lines)
        except Exception as e:
            log.debug(f"Memory-Recall Fast-Path fehlgeschlagen: {e}")
            return None

    # ------------------------------------------------------------------
    # ROI (Region of Interest) Management (v2.0)
    # ------------------------------------------------------------------

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
            log.info(
                "Dynamische UI erkannt: Google Search - ROI auf Suchleiste gesetzt"
            )
            return True

        elif "booking" in task_lower:
            self._set_roi(
                x=100, y=150, width=1000, height=400, name="booking_search_form"
            )
            log.info(
                "Dynamische UI erkannt: Booking.com - ROI auf Suchformular gesetzt"
            )
            return True

        elif "amazon" in task_lower:
            self._set_roi(x=200, y=50, width=900, height=200, name="amazon_search_bar")
            log.info("Dynamische UI erkannt: Amazon - ROI auf Suchleiste gesetzt")
            return True

        return False

    # ------------------------------------------------------------------
    # LLM Calls
    # ------------------------------------------------------------------

    async def _call_llm(self, messages: List[Dict]) -> str:
        try:
            if self.provider in [
                ModelProvider.OPENAI,
                ModelProvider.DEEPSEEK,
                ModelProvider.INCEPTION,
                ModelProvider.NVIDIA,
                ModelProvider.OPENROUTER,
            ]:
                return await self._call_openai_compatible(messages)
            elif self.provider == ModelProvider.ANTHROPIC:
                return await self._call_anthropic(messages)
            else:
                return f"Error: Provider {self.provider} nicht unterstuetzt"
        except Exception as e:
            log.error(f"LLM Fehler: {e}")
            return f"Error: {e}"

    async def _call_openai_compatible(self, messages: List[Dict]) -> str:
        client = self.provider_client.get_client(self.provider)

        kwargs = {
            "model": self.model,
            "messages": messages,
            "temperature": 0.3,
            "max_tokens": 2000,
        }

        if self.provider == ModelProvider.INCEPTION:
            if os.getenv("MERCURY_DIFFUSING", "false").lower() == "true":
                kwargs["extra_body"] = {"diffusing": True}

        if "nemotron" in self.model.lower():
            enable = os.getenv("NEMOTRON_ENABLE_THINKING", "true").lower() == "true"
            if not enable:
                kwargs["extra_body"] = {
                    "chat_template_kwargs": {"enable_thinking": False}
                }
                kwargs["temperature"] = 0.6
                kwargs["top_p"] = 0.95
            else:
                kwargs["temperature"] = 1.0
                kwargs["top_p"] = 1.0

        kwargs = prepare_openai_params(kwargs)

        resp = await asyncio.to_thread(client.chat.completions.create, **kwargs)
        if not resp.choices or not hasattr(resp.choices[0], "message"):
            return ""
        content = resp.choices[0].message.content
        if isinstance(content, str):
            return content.strip()
        if isinstance(content, list):
            parts: List[str] = []
            for item in content:
                if isinstance(item, dict) and isinstance(item.get("text"), str):
                    parts.append(item["text"])
                elif hasattr(item, "text") and isinstance(getattr(item, "text"), str):
                    parts.append(getattr(item, "text"))
            return "".join(parts).strip()
        return str(content or "").strip()

    async def _call_anthropic(self, messages: List[Dict]) -> str:
        client = self.provider_client.get_client(ModelProvider.ANTHROPIC)

        system_content = ""
        chat_messages = []
        for msg in messages:
            if msg["role"] == "system":
                system_content = msg["content"]
            else:
                chat_messages.append(msg)

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

    # ------------------------------------------------------------------
    # Action Parser (delegiert an shared)
    # ------------------------------------------------------------------

    def _parse_action(self, text: str) -> Tuple[Optional[dict], Optional[str]]:
        return parse_action(text)

    def _format_generate_text_output(self, text: str) -> str:
        """Bereitet generate_text-Ergebnisse nutzerfreundlich auf (falls JSON-Liste)."""
        raw = (text or "").strip()
        if not raw:
            return raw

        cleaned = raw.replace("```json", "").replace("```", "").strip()
        parsed: Any = None
        try:
            parsed = json.loads(cleaned)
        except Exception:
            parsed = None

        cafes: Optional[List[Dict[str, Any]]] = None
        if isinstance(parsed, list):
            cafes = [x for x in parsed if isinstance(x, dict)]
        elif isinstance(parsed, dict):
            value = parsed.get("cafes")
            if isinstance(value, list):
                cafes = [x for x in value if isinstance(x, dict)]

        if not cafes:
            return raw

        lines: List[str] = []
        for idx, cafe in enumerate(cafes[:15], start=1):
            name = str(cafe.get("name", "")).strip()
            desc = str(
                cafe.get("short_description")
                or cafe.get("description")
                or cafe.get("atmosphere")
                or ""
            ).strip()
            if not name:
                continue
            if desc:
                lines.append(f"{idx}. {name} - {desc}")
            else:
                lines.append(f"{idx}. {name}")

        if lines:
            return "Hier ist deine Liste:\n" + "\n".join(lines)
        return raw

    def _is_list_request(self, task_lower: str) -> bool:
        """Erkennt, ob der Nutzer explizit eine Liste möchte."""
        patterns = (
            r"\berstelle\s+eine?\s+liste\b",
            r"\bmach\s+eine?\s+liste\b",
            r"\bliste\b",
            r"\blist\b",
            r"\bauflisten\b",
        )
        return any(re.search(p, task_lower) for p in patterns)

    async def _finalize_list_output(self, task: str, result: str) -> str:
        """
        Formatiert Listenanfragen in ein konsistentes Ausgabeformat und speichert sie als Datei.
        """
        task_lower = (task or "").lower()
        if not self._is_list_request(task_lower):
            return result

        final_text = (result or "").strip()
        if not final_text:
            return result

        # JSON-Output von generate_text in nummerierte Liste umwandeln.
        if final_text.startswith("[") or final_text.startswith("{") or "```json" in final_text:
            final_text = self._format_generate_text_output(final_text)

        # Falls noch keine klare Listenform vorhanden ist, einfache Zeilen als nummerierte Liste ausgeben.
        if not re.search(r"(?m)^\s*\d+\.\s+", final_text):
            raw_lines = [ln.strip(" -\t") for ln in final_text.splitlines() if ln.strip()]
            if raw_lines:
                final_text = "Hier ist deine Liste:\n" + "\n".join(
                    f"{i}. {line}" for i, line in enumerate(raw_lines, start=1)
                )

        # Ergebnis zusätzlich persistieren.
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        slug = re.sub(r"[^a-z0-9]+", "_", task_lower)[:50].strip("_") or "liste"
        file_path = f"results/{ts}_{slug}.md"
        file_content = f"# Ergebnisliste\n\n{final_text}\n"

        save_obs = await self._call_tool(
            "write_file",
            {"path": file_path, "content": file_content},
        )
        saved_ok = isinstance(save_obs, dict) and save_obs.get("status") == "success"
        self._emit_step_trace(
            action="list_output_persisted",
            output_data={
                "path": file_path,
                "saved": saved_ok,
                "tool_observation_preview": self._preview_value(save_obs, 500),
            },
            status="ok" if saved_ok else "warning",
        )
        if saved_ok:
            return f"{final_text}\n\nGespeichert unter: `{file_path}`"
        return final_text

    # ------------------------------------------------------------------
    # Working-Memory Prompt-Injektion
    # ------------------------------------------------------------------

    async def _build_working_memory_context(self, task: str) -> str:
        enabled = os.getenv("WORKING_MEMORY_INJECTION_ENABLED", "true").lower()
        if enabled not in {"1", "true", "yes", "on"}:
            self._working_memory_last_meta = {
                "enabled": False,
                "reason": "disabled_by_env",
                "context_chars": 0,
            }
            return ""

        try:
            max_chars = int(os.getenv("WORKING_MEMORY_CHAR_BUDGET", "3200"))
            max_related = int(os.getenv("WORKING_MEMORY_MAX_RELATED", "4"))
            max_recent_events = int(os.getenv("WORKING_MEMORY_MAX_RECENT_EVENTS", "6"))
        except ValueError:
            max_chars, max_related, max_recent_events = 3200, 4, 6

        try:
            from memory.memory_system import memory_manager

            context = await asyncio.to_thread(
                memory_manager.build_working_memory_context,
                task,
                max_chars,
                max_related,
                max_recent_events,
                self.conversation_session_id,
            )
            wm_stats: Dict[str, Any] = {}
            if hasattr(memory_manager, "get_last_working_memory_stats"):
                wm_stats = memory_manager.get_last_working_memory_stats()
            memory_snapshot: Dict[str, Any] = {}
            if hasattr(memory_manager, "get_runtime_memory_snapshot"):
                try:
                    snapshot = memory_manager.get_runtime_memory_snapshot(
                        session_id=self.conversation_session_id
                    )
                    if isinstance(snapshot, dict):
                        memory_snapshot = snapshot
                except Exception:
                    memory_snapshot = {}
            self._working_memory_last_meta = {
                "enabled": True,
                "context_chars": len(context or ""),
                "settings": {
                    "max_chars": max_chars,
                    "max_related": max_related,
                    "max_recent_events": max_recent_events,
                },
                "memory_stats": wm_stats,
                "memory_snapshot": memory_snapshot,
            }
            if context:
                log.info(f"Working-Memory-Kontext injiziert ({len(context)} chars)")
            return context or ""
        except Exception as e:
            log.debug(f"Working-Memory-Kontext nicht verfügbar (non-critical): {e}")
            self._working_memory_last_meta = {
                "enabled": True,
                "error": str(e),
                "context_chars": 0,
            }
            return ""

    def _inject_working_memory_into_task(self, task: str, working_memory_context: str) -> str:
        if not working_memory_context:
            return task
        return (
            f"{working_memory_context}\n\n"
            f"AKTUELLE_NUTZERANFRAGE:\n{task}\n\n"
            "Bearbeite jetzt ausschließlich die aktuelle Nutzeranfrage."
        )

    def get_runtime_telemetry(self) -> Dict[str, Any]:
        run_duration = None
        if self._run_started_at > 0:
            run_duration = round(max(0.0, time.time() - self._run_started_at), 3)
        return {
            "agent_type": self.agent_type,
            "model": self.model,
            "provider": self.provider.value,
            "run_duration_sec": run_duration,
            "action_count": len(self._task_action_history),
            "active_phase": self._active_phase,
            "active_tool": self._active_tool_name,
            "conversation_session_id": self.conversation_session_id or "",
            "memory_recall": self._memory_recall_last_meta,
            "working_memory": self._working_memory_last_meta,
        }

    # ------------------------------------------------------------------
    # Haupt-Loop
    # ------------------------------------------------------------------

    async def run(self, task: str) -> str:
        log.info(f"{self.__class__.__name__} ({self.provider.value})")
        # Run-scope Reset: verhindert, dass alte Loop-Counter ueber mehrere Tasks leaken.
        self.recent_actions = []
        self.last_skip_times = {}
        self.action_call_counts = {}
        self._task_action_history = []
        self._run_started_at = time.time()
        self._active_tool_name = None
        self._memory_recall_last_meta = {}
        self._emit_live_status(
            phase="start",
            detail=f"model={self.model} provider={self.provider.value}",
        )
        self._emit_step_trace(
            action="agent_run_start",
            input_data={
                "task_preview": self._preview_value(task, 400),
                "task_chars": len(task or ""),
            },
            status="started",
            metadata={
                "agent_type": self.agent_type,
                "model": self.model,
                "provider": self.provider.value,
                "max_iterations": self.max_iterations,
                "session_id": self.conversation_session_id or "",
            },
        )

        roi_set = await self._detect_dynamic_ui_and_set_roi(task)

        task_lower = task.lower()
        is_memory_query = self._is_memory_recall_query(task_lower)

        if is_memory_query:
            memory_answer = await self._try_memory_recall(task)
            if memory_answer:
                if roi_set:
                    self._clear_roi()
                self._task_action_history = [
                    {
                        "method": "recall",
                        "params": {"query": task, "n_results": 5},
                        "result": memory_answer[:200],
                    }
                ]
                self._emit_live_status(phase="memory_recall", detail="Fast-Path genutzt")
                self._emit_step_trace(
                    action="memory_fastpath_hit",
                    output_data={
                        "answer_preview": self._preview_value(memory_answer, 600),
                        "answer_chars": len(memory_answer),
                    },
                )
                await self._run_reflection(task, memory_answer, success=True)
                return memory_answer

        is_navigation_task = self._is_navigation_task(task_lower)

        if is_navigation_task:
            structured_result = await self._try_structured_navigation(task)
            if structured_result and structured_result.get("success"):
                log.info(
                    f"Strukturierte Navigation erfolgreich: {structured_result['result']}"
                )
                self._emit_live_status(
                    phase="structured_nav",
                    detail="ActionPlan erfolgreich",
                )
                self._emit_step_trace(
                    action="structured_navigation_success",
                    output_data={
                        "result_preview": self._preview_value(
                            structured_result.get("result", ""), 500
                        )
                    },
                )
                if roi_set:
                    self._clear_roi()
                # Track structured nav action for reflection
                self._task_action_history.append({
                    "method": "structured_navigation",
                    "params": {"task": task},
                    "result": structured_result.get("result", "")
                })
                await self._run_reflection(task, structured_result.get("result", ""))
                return structured_result["result"]
            else:
                log.info(
                    "Strukturierte Navigation nicht moeglich - nutze regulaeren Flow"
                )
                self._emit_step_trace(
                    action="structured_navigation_fallback",
                    status="warning",
                )

        # Clear action history for new task
        self._task_action_history = []
        working_memory_context = await self._build_working_memory_context(task)
        task_with_context = self._inject_working_memory_into_task(
            task, working_memory_context
        )
        self._emit_step_trace(
            action="working_memory_injected",
            output_data={
                "context_chars": len(working_memory_context or ""),
                "context_preview": self._preview_value(working_memory_context, 700),
            },
            metadata={"vision_enabled": self._vision_enabled},
        )

        use_vision = is_navigation_task and self._vision_enabled
        if use_vision:
            log.info("Multimodal-Modus: Screenshots werden an LLM gesendet")
            initial_screenshot = await asyncio.to_thread(
                self._capture_screenshot_base64
            )
            initial_msg = self._build_vision_message(task_with_context, initial_screenshot)
        else:
            initial_msg = {"role": "user", "content": task_with_context}

        messages = [
            {"role": "system", "content": self.system_prompt},
            initial_msg,
        ]
        last_generate_text_output: str = ""
        empty_reply_streak = 0

        for step in range(1, self.max_iterations + 1):
            self._emit_live_status(
                phase="thinking",
                step=step,
                total_steps=self.max_iterations,
            )
            last_msg = messages[-1] if messages else {}
            last_content = last_msg.get("content", "") if isinstance(last_msg, dict) else ""
            self._emit_step_trace(
                action="llm_request",
                input_data={
                    "step": step,
                    "messages_count": len(messages),
                    "last_role": (
                        last_msg.get("role", "")
                        if isinstance(last_msg, dict)
                        else ""
                    ),
                    "last_message_preview": self._preview_value(last_content, 400),
                },
            )
            reply = await self._call_llm(messages)
            if not (reply or "").strip():
                empty_reply_streak += 1
                self._emit_step_trace(
                    action="empty_llm_reply",
                    output_data={"step": step, "streak": empty_reply_streak},
                    status="warning",
                )
            else:
                empty_reply_streak = 0
            self._emit_step_trace(
                action="llm_reply",
                output_data={
                    "step": step,
                    "reply_chars": len(reply or ""),
                    "reply_preview": self._preview_value(reply, 900),
                    "contains_final_answer": "Final Answer:" in (reply or ""),
                },
            )
            if (
                empty_reply_streak >= 2
                and last_generate_text_output
            ):
                final_result = self._format_generate_text_output(last_generate_text_output)
                final_result = await self._finalize_list_output(task, final_result)
                self._emit_live_status(
                    phase="final",
                    detail="Fallback: generate_text übernommen",
                    step=step,
                    total_steps=self.max_iterations,
                )
                self._emit_step_trace(
                    action="fallback_final_from_generate_text",
                    output_data={
                        "step": step,
                        "final_chars": len(final_result),
                        "final_preview": self._preview_value(final_result, 900),
                    },
                    status="completed",
                )
                if roi_set:
                    self._clear_roi()
                await self._run_reflection(task, final_result, success=True)
                return final_result

            if reply.startswith("Error"):
                self._emit_live_status(
                    phase="error",
                    detail=reply[:120],
                    step=step,
                    total_steps=self.max_iterations,
                )
                if roi_set:
                    self._clear_roi()
                self._emit_step_trace(
                    action="llm_error",
                    output_data={
                        "step": step,
                        "error_preview": self._preview_value(reply, 800),
                    },
                    status="error",
                )
                await self._run_reflection(task, reply, success=False)
                return reply
            if "Final Answer:" in reply:
                final_result = reply.split("Final Answer:")[1].strip()
                final_result = await self._finalize_list_output(task, final_result)
                self._emit_live_status(
                    phase="final",
                    detail=f"{len(final_result)} chars",
                    step=step,
                    total_steps=self.max_iterations,
                )
                if roi_set:
                    self._clear_roi()
                self._emit_step_trace(
                    action="final_answer_detected",
                    output_data={
                        "step": step,
                        "final_preview": self._preview_value(final_result, 800),
                        "final_chars": len(final_result),
                    },
                    status="completed",
                )
                await self._run_reflection(task, final_result, success=True)
                return final_result

            action, err = self._parse_action(reply)
            messages.append({"role": "assistant", "content": reply})

            if not action:
                self._emit_live_status(
                    phase="parse_error",
                    detail=(err or "Kein JSON")[:120],
                    step=step,
                    total_steps=self.max_iterations,
                )
                messages.append(
                    {
                        "role": "user",
                        "content": (
                            f"Fehler: {err}. "
                            "Antworte jetzt ENTWEDER mit "
                            "Action: {\"method\":\"tool_name\",\"params\":{...}} "
                            "ODER mit Final Answer: ... "
                            "Nutze NICHT das System-Tool add_interaction."
                        ),
                    }
                )
                self._emit_step_trace(
                    action="parse_error",
                    output_data={
                        "step": step,
                        "error": err or "Kein JSON",
                        "reply_preview": self._preview_value(reply, 900),
                    },
                    status="warning",
                )
                continue

            method = action.get("method", "")
            params = action.get("params", {})
            self._emit_step_trace(
                action="action_parsed",
                input_data={
                    "step": step,
                    "method": method,
                    "params_preview": self._preview_value(params, 800),
                },
            )

            obs = await self._call_tool(method, params)
            self._emit_step_trace(
                action="tool_observation",
                input_data={"step": step, "method": method},
                output_data={
                    "observation_type": type(obs).__name__,
                    "observation_preview": self._preview_value(
                        self._sanitize_observation(obs), 950
                    ),
                },
            )
            if (
                method == "generate_text"
                and isinstance(obs, dict)
                and obs.get("status") == "success"
                and isinstance(obs.get("text"), str)
                and obs.get("text", "").strip()
            ):
                last_generate_text_output = obs["text"].strip()
            
            # Track action for reflection
            self._task_action_history.append({
                "method": method,
                "params": params,
                "result": str(obs)[:200] if obs else None
            })
            
            self._handle_file_artifacts(obs)

            obs_text = f"Observation: {json.dumps(self._sanitize_observation(obs), ensure_ascii=False)}"
            if use_vision:
                screenshot_b64 = await asyncio.to_thread(
                    self._capture_screenshot_base64
                )
                messages.append(self._build_vision_message(obs_text, screenshot_b64))
            else:
                messages.append({"role": "user", "content": obs_text})

        if roi_set:
            self._clear_roi()
        self._emit_live_status(phase="limit", detail="max iterations erreicht")
        self._emit_step_trace(
            action="iteration_limit_reached",
            output_data={"max_iterations": self.max_iterations},
            status="error",
        )
        
        await self._run_reflection(task, "Limit erreicht", success=False)
        return "Limit erreicht."

    async def _run_reflection(
        self, 
        task: str, 
        result: str, 
        success: bool = True
    ) -> None:
        """
        Fuehrt Post-Task Reflexion aus und speichert Learnings.
        
        Wird automatisch nach Task-Abschluss aufgerufen.
        """
        if not self._reflection_enabled:
            return
        
        try:
            # Lazy import to avoid circular dependency
            from memory.reflection_engine import get_reflection_engine
            
            engine = get_reflection_engine()
            
            # Set memory manager if available
            if engine.memory is None:
                try:
                    from memory.memory_system import memory_manager
                    engine.set_memory_manager(memory_manager)
                except ImportError:
                    pass
            
            # Set LLM client if available
            if engine.llm is None and hasattr(self, 'provider_client'):
                try:
                    engine.set_llm_client(
                        self.provider_client.get_client(ModelProvider.OPENAI)
                    )
                except Exception:
                    # Fallback: ReflectionEngine kann MultiProviderClient selbst auflösen
                    engine.set_llm_client(self.provider_client)
            
            # Run reflection
            reflection = await engine.reflect_on_task(
                task={"description": task, "type": self.agent_type},
                actions=self._task_action_history,
                result={"success": success, "output": result}
            )
            
            if reflection:
                log.debug(
                    f"🪞 Reflexion: {len(reflection.what_worked)} positiv, "
                    f"{len(reflection.what_failed)} negativ"
                )
                
        except Exception as e:
            log.debug(f"Reflexion fehlgeschlagen (non-critical): {e}")
