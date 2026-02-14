"""VisualAgent - Visual Agent mit Screenshot-Analyse."""

import os
import io
import json
import asyncio
import base64
import time
import logging
from typing import Dict, List, Optional

import httpx

from agent.base_agent import BaseAgent, MCP_URL
from agent.providers import ModelProvider
from agent.prompts import VISUAL_SYSTEM_PROMPT
from agent.shared.vision_formatter import convert_openai_to_anthropic

log = logging.getLogger("TimusAgent-v4.4")


class VisualAgent(BaseAgent):
    """Visual Agent mit Screenshot-Analyse."""

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

    async def _wait_stable(self):
        try:
            await self.http_client.post(
                MCP_URL,
                json={"jsonrpc": "2.0", "method": "wait_until_stable", "params": {"timeout": 3.0}, "id": "1"},
            )
        except Exception:
            pass

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
            log.info("Dynamische UI erkannt: Booking.com - ROI auf Suchformular gesetzt")
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
        self.history = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": f"AUFGABE: {task}"},
        ]

        roi_set = await self._detect_dynamic_ui_and_set_roi(task)

        consecutive_loops = 0
        force_vision_mode = False

        structured_result = await self._try_structured_navigation(task)
        if structured_result and structured_result.get("success"):
            log.info(f"Strukturierte Navigation erfolgreich: {structured_result['result']}")
            if roi_set:
                self._clear_roi()
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
                return params.get("message", "Fertig")

            if method in ["click_at", "type_text", "start_visual_browser", "open_application"]:
                await self._capture_before()

            obs = await self._call_tool(method, params)

            if isinstance(obs, dict) and "_loop_warning" in obs:
                consecutive_loops += 1
                log.warning(f"Loop-Warnung erhalten ({consecutive_loops}x): {obs['_loop_warning']}")
                obs["_info"] = f"LOOP-WARNUNG: {obs['_loop_warning']} Versuche anderen Ansatz!"
            else:
                consecutive_loops = 0

            if method in ["click_at", "type_text", "start_visual_browser", "open_application"]:
                if not await self._verify_action(method):
                    self.history.append({"role": "assistant", "content": reply})
                    self.history.append({"role": "user", "content": "Nicht verifiziert. Anderen Ansatz versuchen."})
                    continue
                await self._wait_stable()

            self._handle_file_artifacts(obs)
            self.history.append({"role": "assistant", "content": reply})
            self.history.append({"role": "user", "content": f"Observation: {json.dumps(self._sanitize_observation(obs), ensure_ascii=False)}"})
            await asyncio.sleep(0.5)

        if roi_set:
            self._clear_roi()

        return "Max Iterationen."
