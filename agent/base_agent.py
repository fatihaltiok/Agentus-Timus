"""BaseAgent Klasse mit Multi-Provider Support.

Enthaelt die Basisklasse fuer alle Timus-Agenten mit:
- Multi-Provider LLM Calls
- Loop-Detection
- Screen-Change-Gate
- ROI Management
- Strukturierte Navigation
"""

import logging
import os
import json
import asyncio
import base64
import subprocess
import platform
import time
from datetime import datetime
from typing import Dict, Any, List, Optional, Tuple

import httpx

from agent.providers import (
    ModelProvider, AgentModelConfig, get_provider_client,
)
from agent.shared.mcp_client import MCPClient
from agent.shared.screenshot import capture_screenshot_base64
from agent.shared.action_parser import parse_action
from agent.shared.vision_formatter import build_openai_vision_message

from utils.openai_compat import prepare_openai_params
from agent.dynamic_tool_mixin import DynamicToolMixin

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
    ):
        self.max_iterations = max_iterations
        self.agent_type = agent_type

        # DynamicToolMixin initialisieren
        capabilities = AGENT_CAPABILITY_MAP.get(agent_type)
        self.init_dynamic_tools(capabilities=capabilities, max_iterations=max_iterations)
        self.http_client = httpx.AsyncClient(timeout=300.0)
        self.recent_actions: List[str] = []
        self.last_skip_times: Dict[str, float] = {}

        # Multi-Provider Setup
        self.provider_client = get_provider_client()
        self.model, self.provider = AgentModelConfig.get_model_and_provider(agent_type)

        log.info(f"{self.__class__.__name__} | {self.model} | {self.provider.value}")

        self.system_prompt = (
            system_prompt_template
            .replace("{current_date}", datetime.now().strftime("%d.%m.%Y"))
            .replace("{tools_description}", tools_description_string)
        )

        # Screen-Change-Gate Support (v1.0)
        self.use_screen_change_gate = os.getenv("USE_SCREEN_CHANGE_GATE", "false").lower() == "true"
        self.cached_screen_state: Optional[Dict] = None
        self.last_screen_analysis_time: float = 0
        self._last_screen_check_time: float = 0.0

        # ROI (Region of Interest) Support (v2.0)
        self.roi_stack: List[Dict] = []
        self.current_roi: Optional[Dict] = None

        # Multimodal Vision Support
        self._vision_enabled = False
        try:
            import mss as _mss
            from PIL import Image as _PILImage
            self._vision_enabled = True
        except ImportError:
            pass

        if self.use_screen_change_gate:
            log.info(f"Screen-Change-Gate AKTIV fuer {self.__class__.__name__}")

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
                    clean[k] = v[:10] + [f"... +{len(v)-10}"]
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
        "add_interaction", "end_session", "get_memory_stats",
    }

    def should_skip_action(self, action_name: str, params: dict) -> Tuple[bool, Optional[str]]:
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
        count = self.recent_actions.count(action_key)

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

        if action_name in LOW_VALUE_ACTIONS and count >= 2:
            reason = (
                f"Low-value tool '{action_name}' already used {count+1}x. "
                f"Switch to higher-signal tools (search_web, open_url, analyze_screen_verified)."
            )
            log.warning(reason)
            self.last_skip_times[action_key] = now
            return True, reason

        if count >= 2:
            reason = (
                f"Loop detected: {action_name} wurde bereits {count+1}x aufgerufen "
                f"mit denselben Parametern. KRITISCH: Aktion wird uebersprungen. "
                f"Versuche anderen Ansatz!"
            )
            log.error(f"Kritischer Loop ({count+1}x): {action_name} - Aktion wird uebersprungen")
            self.last_skip_times[action_key] = now
            return True, reason

        elif count >= 1:
            reason = (
                f"Loop detected: {action_name} wurde bereits {count+1}x aufgerufen "
                f"mit denselben Parametern. Versuche andere Parameter oder anderen Ansatz."
            )
            log.warning(f"Loop ({count+1}x): {action_name} - Warnung an Agent")
            self.recent_actions.append(action_key)
            return False, reason

        self.recent_actions.append(action_key)
        if len(self.recent_actions) > 20:
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
    # MCP Tool Call (mit Loop-Detection)
    # ------------------------------------------------------------------

    async def _call_tool(self, method: str, params: dict) -> dict:
        method, params = self._refine_tool_call(method, params)

        should_skip, loop_reason = self.should_skip_action(method, params)

        if should_skip:
            log.error(f"Tool-Call uebersprungen: {method} (Loop)")
            return {"skipped": True, "reason": loop_reason or "Loop detected"}

        if loop_reason:
            log.warning(f"Loop-Warnung fuer {method}: {loop_reason}")

        log.info(f"{method} -> {str(params)[:100]}")

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
                return result

            if "error" in data:
                return {"error": str(data["error"])}
            return {"error": "Invalid response"}
        except Exception as e:
            return {"error": str(e)}

    # ------------------------------------------------------------------
    # Screen-Change-Gate
    # ------------------------------------------------------------------

    async def _should_analyze_screen(self, roi: Optional[Dict] = None, force: bool = False) -> bool:
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
                log.debug(f"Screen geaendert - {result.get('info', {}).get('reason', 'unknown')}")
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
                log.debug(f"ScreenState analysiert: {len(result.get('elements', []))} Elemente")
                return result
            else:
                log.warning(f"Screen-Analyse fehlgeschlagen: {result.get('error', 'unknown')}")
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
            }

        except Exception as e:
            log.error(f"Screen-Analyse fehlgeschlagen: {e}")
            return None

    async def _create_navigation_plan_with_llm(self, task: str, screen_state: Dict) -> Optional[Dict]:
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

            response = _re.sub(r'```json\s*', '', response)
            response = _re.sub(r'```\s*', '', response)

            json_match = _re.search(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', response, _re.DOTALL)
            if not json_match:
                log.warning(f"Kein JSON gefunden in Response: {response[:200]}")
                return None

            plan = json.loads(json_match.group(0))

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

            action_plan = await self._create_navigation_plan_with_llm(task, screen_state)
            if not action_plan:
                log.info("ActionPlan-Erstellung fehlgeschlagen - nutze regulaeren Flow")
                return None

            log.info(f"Fuehre ActionPlan aus: {action_plan.get('goal', 'N/A')}")
            result = await self._call_tool("execute_action_plan", {"plan_dict": action_plan})

            if result and result.get("success"):
                return {
                    "success": True,
                    "result": action_plan.get("goal", "Aufgabe erfolgreich"),
                    "state": screen_state,
                }
            else:
                log.warning(f"ActionPlan fehlgeschlagen: {result.get('error', 'Unknown')}")
                return None

        except Exception as e:
            log.error(f"Strukturierte Navigation fehlgeschlagen: {e}")
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
            log.info("Dynamische UI erkannt: Google Search - ROI auf Suchleiste gesetzt")
            return True

        elif "booking" in task_lower:
            self._set_roi(x=100, y=150, width=1000, height=400, name="booking_search_form")
            log.info("Dynamische UI erkannt: Booking.com - ROI auf Suchformular gesetzt")
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
                ModelProvider.OPENAI, ModelProvider.DEEPSEEK,
                ModelProvider.INCEPTION, ModelProvider.NVIDIA,
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
                kwargs["extra_body"] = {"chat_template_kwargs": {"enable_thinking": False}}
                kwargs["temperature"] = 0.6
                kwargs["top_p"] = 0.95
            else:
                kwargs["temperature"] = 1.0
                kwargs["top_p"] = 1.0

        kwargs = prepare_openai_params(kwargs)

        resp = await asyncio.to_thread(client.chat.completions.create, **kwargs)
        return resp.choices[0].message.content.strip()

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

    # ------------------------------------------------------------------
    # Haupt-Loop
    # ------------------------------------------------------------------

    async def run(self, task: str) -> str:
        log.info(f"{self.__class__.__name__} ({self.provider.value})")

        roi_set = await self._detect_dynamic_ui_and_set_roi(task)

        task_lower = task.lower()
        is_navigation_task = any(keyword in task_lower for keyword in [
            "browser", "website", "url", "klick", "click", "such", "search",
            "booking", "google", "amazon", "navigate", "oeffne", "gehe zu",
        ])

        if is_navigation_task:
            structured_result = await self._try_structured_navigation(task)
            if structured_result and structured_result.get("success"):
                log.info(f"Strukturierte Navigation erfolgreich: {structured_result['result']}")
                if roi_set:
                    self._clear_roi()
                return structured_result["result"]
            else:
                log.info("Strukturierte Navigation nicht moeglich - nutze regulaeren Flow")

        use_vision = is_navigation_task and self._vision_enabled
        if use_vision:
            log.info("Multimodal-Modus: Screenshots werden an LLM gesendet")
            initial_screenshot = await asyncio.to_thread(self._capture_screenshot_base64)
            initial_msg = self._build_vision_message(task, initial_screenshot)
        else:
            initial_msg = {"role": "user", "content": task}

        messages = [
            {"role": "system", "content": self.system_prompt},
            initial_msg,
        ]

        for step in range(1, self.max_iterations + 1):
            reply = await self._call_llm(messages)

            if reply.startswith("Error"):
                if roi_set:
                    self._clear_roi()
                return reply
            if "Final Answer:" in reply:
                if roi_set:
                    self._clear_roi()
                return reply.split("Final Answer:")[1].strip()

            action, err = self._parse_action(reply)
            messages.append({"role": "assistant", "content": reply})

            if not action:
                messages.append({"role": "user", "content": f"Fehler: {err}. Korrektes JSON senden."})
                continue

            obs = await self._call_tool(action.get("method", ""), action.get("params", {}))
            self._handle_file_artifacts(obs)

            obs_text = f"Observation: {json.dumps(self._sanitize_observation(obs), ensure_ascii=False)}"
            if use_vision:
                screenshot_b64 = await asyncio.to_thread(self._capture_screenshot_base64)
                messages.append(self._build_vision_message(obs_text, screenshot_b64))
            else:
                messages.append({"role": "user", "content": obs_text})

        if roi_set:
            self._clear_roi()

        return "Limit erreicht."
