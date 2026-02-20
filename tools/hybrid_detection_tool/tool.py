# tools/hybrid_detection_tool/tool.py
"""
Hybrid Detection Tool - Kombiniert verschiedene Erkennungsmethoden.

Strategie für präzise UI-Element-Erkennung:
1. Text-basierte Elemente: OCR + Visual Grounding (sehr präzise)
2. Icon/Button-Elemente ohne Text: Object Detection (Moondream/SoM)
3. Finalisierung: Mouse Feedback Tool (Cursor-basierte Verfeinerung)

Version: 1.0
"""

import logging
import asyncio
import os
import json
import time
import httpx
from pathlib import Path
from typing import Any, List, Dict, Optional, Tuple
from dataclasses import dataclass

from tools.tool_registry_v2 import tool, ToolParameter as P, ToolCategory as C
from dotenv import load_dotenv
from utils.coordinate_converter import resolve_click_coordinates

# --- Setup ---
load_dotenv()
log = logging.getLogger("hybrid_detection")

# MCP Server URL für Tool-Aufrufe
MCP_URL = os.getenv("MCP_URL", "http://127.0.0.1:5000")
TIMEOUT = 180.0
OPENCV_TEMPLATE_THRESHOLD = float(os.getenv("OPENCV_TEMPLATE_THRESHOLD", "0.82"))
PROJECT_ROOT = Path(__file__).resolve().parents[2]
VISION_ADAPTIVE_CONFIG_PATH = Path(
    os.getenv("VISION_ADAPTIVE_CONFIG_PATH", str(PROJECT_ROOT / "data" / "vision_adaptive_config.json"))
).expanduser()


@dataclass
class DetectedElement:
    """Repräsentiert ein erkanntes UI-Element."""
    method: str  # "ocr", "som", "mouse_feedback"
    element_type: str  # "text_field", "button", "icon", etc.
    x: int
    y: int
    confidence: float
    text: str = ""
    bounds: Optional[Dict] = None
    metadata: Optional[Dict] = None


class HybridDetectionEngine:
    """
    Engine für intelligente Hybrid-Erkennung.
    Kombiniert OCR, Object Detection und Mouse Feedback.
    """

    def __init__(self):
        self.http_client = httpx.AsyncClient(timeout=TIMEOUT)

    async def _call_tool(self, method: str, params: dict = None) -> Optional[dict]:
        """Ruft ein Tool über MCP-Server auf."""
        payload = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params or {},
            "id": "hybrid-1"
        }

        try:
            response = await self.http_client.post(MCP_URL, json=payload)
            response.raise_for_status()
            result = response.json()

            if "error" in result:
                log.warning(f"Tool-Fehler ({method}): {result['error']}")
                return None

            return result.get("result")

        except Exception as e:
            log.error(f"Fehler beim Tool-Aufruf ({method}): {e}")
            return None

    def _load_active_vision_adaptive(self) -> Dict[str, Any]:
        """Lädt nur den aktiven Bereich der Adaptive-Config (nur bereits freigegebene Änderungen)."""
        path = Path(
            os.getenv("VISION_ADAPTIVE_CONFIG_PATH", str(VISION_ADAPTIVE_CONFIG_PATH))
        ).expanduser().resolve()
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            active = payload.get("active", {})
            return active if isinstance(active, dict) else {}
        except Exception:
            return {}

    def _adaptive_template_threshold(self) -> float:
        active = self._load_active_vision_adaptive()
        value = active.get("opencv_template_threshold", OPENCV_TEMPLATE_THRESHOLD)
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            parsed = OPENCV_TEMPLATE_THRESHOLD
        return max(0.5, min(0.99, parsed))

    def _adaptive_template_candidates(self) -> List[str]:
        active = self._load_active_vision_adaptive()
        values = active.get("template_candidates", [])
        if not isinstance(values, list):
            return []
        result: List[str] = []
        for value in values:
            if isinstance(value, str) and value.strip():
                result.append(value.strip())
        return result

    async def find_by_text(self, text: str) -> Optional[DetectedElement]:
        """Findet ein Element anhand seines Textes (sehr präzise)."""
        log.info(f"Text-Suche: '{text}'")

        result = await self._call_tool("find_text_coordinates", {"text_to_find": text})

        if result and result.get("found"):
            coords = resolve_click_coordinates(result, already_absolute=True)
            if not coords:
                coords = resolve_click_coordinates(result.get("coordinates", {}), already_absolute=True)
            if not coords:
                log.warning("Text-Erkennung ohne verwertbare Koordinaten")
                return None
            x, y = coords

            log.info(f"Text gefunden bei ({x}, {y})")

            return DetectedElement(
                method="ocr",
                element_type="text_element",
                x=x,
                y=y,
                confidence=result.get("confidence", 0.9),
                text=text,
                bounds=coords,
                metadata=result
            )

        log.warning(f"Text '{text}' nicht gefunden")
        return None

    async def find_by_object_detection(
        self,
        element_type: str,
        prefer_index: int = 0
    ) -> Optional[DetectedElement]:
        """Findet ein Element via Object Detection (SoM Tool)."""
        log.info(f"Object Detection: '{element_type}'")

        result = await self._call_tool("scan_ui_elements", {"element_types": [element_type]})

        if result and result.get("count", 0) > 0:
            elements = result.get("elements", [])
            if prefer_index < len(elements):
                elem = elements[prefer_index]

                log.info(f"{element_type} gefunden bei ({elem['x']}, {elem['y']})")

                return DetectedElement(
                    method="som",
                    element_type=element_type,
                    x=elem["x"],
                    y=elem["y"],
                    confidence=elem.get("confidence", 0.8),
                    bounds=elem.get("bounds"),
                    metadata={"total_found": len(elements), "index": prefer_index}
                )

        log.warning(f"{element_type} nicht gefunden")
        return None

    async def find_by_template_matching(
        self,
        template_name: Optional[str],
        threshold: Optional[float] = None,
    ) -> Optional[DetectedElement]:
        """Findet ein Element via OpenCV-Template-Matching."""
        if not template_name:
            return None
        threshold = self._adaptive_template_threshold() if threshold is None else threshold

        log.info(f"Template Matching: '{template_name}'")
        result = await self._call_tool(
            "opencv_template_match",
            {
                "template_name": template_name,
                "threshold": threshold,
                "multi_scale": True,
            },
        )
        if result and result.get("found"):
            coords = resolve_click_coordinates(result, already_absolute=True)
            if not coords:
                return None
            x, y = coords
            return DetectedElement(
                method="opencv_template",
                element_type="template_match",
                x=x,
                y=y,
                confidence=float(result.get("confidence", result.get("score", 0.0))),
                text=template_name,
                bounds=result.get("bbox"),
                metadata=result,
            )
        return None

    async def refine_with_mouse_feedback(
        self,
        x: int,
        y: int,
        target_cursor: str = "ibeam",
        radius: int = 80
    ) -> Optional[Tuple[int, int, str]]:
        """Verfeinert Koordinaten mit Mouse Feedback Tool."""
        log.info(f"Mouse Feedback Verfeinerung um ({x}, {y}), Ziel: {target_cursor}")

        result = await self._call_tool(
            "find_text_field_nearby" if target_cursor == "ibeam" else "search_for_element",
            {
                "x": x,
                "y": y,
                "radius": radius
            }
        )

        if result and result.get("found"):
            refined_x = result.get("x", x)
            refined_y = result.get("y", y)
            cursor = result.get("cursor_type", "arrow")

            log.info(f"Verfeinert: ({refined_x}, {refined_y}), Cursor: {cursor}")
            return refined_x, refined_y, cursor

        log.warning("Mouse Feedback Verfeinerung fehlgeschlagen")
        return None

    async def smart_find_element(
        self,
        text: Optional[str] = None,
        element_type: Optional[str] = None,
        refine: bool = True,
        target_cursor: Optional[str] = None,
        template_name: Optional[str] = None,
        enable_template_fallback: bool = True,
    ) -> Optional[DetectedElement]:
        """Intelligente Element-Suche mit Hybrid-Ansatz."""
        element = None

        # 1. Text-basierte Suche (wenn Text gegeben)
        if text:
            element = await self.find_by_text(text)

        # 2. Object Detection (wenn kein Text oder Text-Suche fehlgeschlagen)
        if not element and element_type:
            element = await self.find_by_object_detection(element_type)

        # 2b. OpenCV Template Fallback
        if not element and enable_template_fallback:
            candidates: List[str] = []
            for candidate in [template_name, text, element_type]:
                if isinstance(candidate, str) and candidate.strip():
                    candidates.append(candidate.strip())
            candidates.extend(self._adaptive_template_candidates())
            seen: set[str] = set()
            threshold = self._adaptive_template_threshold()
            for candidate in candidates:
                key = candidate.lower()
                if key in seen:
                    continue
                seen.add(key)
                element = await self.find_by_template_matching(candidate, threshold=threshold)
                if element:
                    break

        # 3. Mouse Feedback Verfeinerung
        if element and refine:
            if not target_cursor:
                if "text" in element.element_type.lower() or "input" in element.element_type.lower():
                    target_cursor = "ibeam"
                elif "button" in element.element_type.lower() or "link" in element.element_type.lower():
                    target_cursor = "hand"
                else:
                    target_cursor = "arrow"

            refined = await self.refine_with_mouse_feedback(
                element.x,
                element.y,
                target_cursor
            )

            if refined:
                refined_x, refined_y, cursor = refined
                old_x, old_y = element.x, element.y
                element.x = refined_x
                element.y = refined_y
                element.method = f"{element.method}+mouse_feedback"
                element.metadata = element.metadata or {}
                element.metadata.update({
                    "original_coords": (old_x, old_y),
                    "refinement_offset": (refined_x - old_x, refined_y - old_y),
                    "cursor_type": cursor
                })
                log.info(f"Verfeinert: ({old_x},{old_y}) -> ({refined_x},{refined_y})")

        return element


# Globale Engine-Instanz
hybrid_engine = HybridDetectionEngine()


# ==============================================================================
# RPC METHODEN
# ==============================================================================

@tool(
    name="hybrid_find_element",
    description="Intelligente Element-Suche mit Hybrid-Ansatz. Kombiniert OCR (für Text), Object Detection (für Icons/Buttons) und Mouse Feedback (für Feinabstimmung).",
    parameters=[
        P("text", "string", "Text des Elements (höchste Priorität)", required=False, default=None),
        P("element_type", "string", "Typ des Elements (button, text field, icon, etc.)", required=False, default=None),
        P("refine", "boolean", "Mit Mouse Feedback verfeinern?", required=False, default=True),
        P("target_cursor", "string", "Erwarteter Cursor-Typ (ibeam, hand, arrow)", required=False, default=None),
        P("template_name", "string", "Optionaler Template-Name für OpenCV-Fallback", required=False, default=None),
        P("enable_template_fallback", "boolean", "OpenCV-Fallback aktivieren?", required=False, default=True),
    ],
    capabilities=["vision", "detection"],
    category=C.VISION
)
async def hybrid_find_element(
    text: Optional[str] = None,
    element_type: Optional[str] = None,
    refine: bool = True,
    target_cursor: Optional[str] = None,
    template_name: Optional[str] = None,
    enable_template_fallback: bool = True,
) -> dict:
    """Intelligente Element-Suche mit Hybrid-Ansatz."""
    if not text and not element_type:
        raise Exception("Mindestens 'text' oder 'element_type' muss angegeben sein")

    try:
        element = await hybrid_engine.smart_find_element(
            text=text,
            element_type=element_type,
            refine=refine,
            target_cursor=target_cursor,
            template_name=template_name,
            enable_template_fallback=enable_template_fallback,
        )

        if not element:
            raise Exception(
                f"Element nicht gefunden (text='{text}', type='{element_type}')"
            )

        return {
            "found": True,
            "method": element.method,
            "element_type": element.element_type,
            "x": element.x,
            "y": element.y,
            "confidence": element.confidence,
            "text": element.text,
            "bounds": element.bounds,
            "metadata": element.metadata,
            "instruction": f"Nutze click_at(x={element.x}, y={element.y})"
        }

    except Exception as e:
        log.error(f"Hybrid-Fehler: {e}", exc_info=True)
        raise Exception(str(e))


@tool(
    name="hybrid_find_and_click",
    description="Findet ein Element mit Hybrid-Ansatz und klickt darauf.",
    parameters=[
        P("text", "string", "Text des Elements", required=False, default=None),
        P("element_type", "string", "Typ des Elements", required=False, default=None),
        P("refine", "boolean", "Mit Mouse Feedback verfeinern?", required=False, default=True),
        P("verify", "boolean", "Cursor vor dem Klick überprüfen?", required=False, default=True),
        P("template_name", "string", "Optionaler Template-Name für OpenCV-Fallback", required=False, default=None),
        P("enable_template_fallback", "boolean", "OpenCV-Fallback aktivieren?", required=False, default=True),
    ],
    capabilities=["vision", "detection"],
    category=C.VISION
)
async def hybrid_find_and_click(
    text: Optional[str] = None,
    element_type: Optional[str] = None,
    refine: bool = True,
    verify: bool = True,
    template_name: Optional[str] = None,
    enable_template_fallback: bool = True,
) -> dict:
    """Findet ein Element mit Hybrid-Ansatz und klickt darauf."""
    try:
        start_ts = time.perf_counter()
        pipeline_log: List[Dict[str, Any]] = []

        element = await hybrid_engine.smart_find_element(
            text=text,
            element_type=element_type,
            refine=refine,
            template_name=template_name,
            enable_template_fallback=enable_template_fallback,
        )

        if not element:
            raise Exception(
                f"Element nicht gefunden (text='{text}', type='{element_type}')"
            )
        pipeline_log.append(
            {
                "stage": "detect_primary",
                "method": element.method,
                "x": element.x,
                "y": element.y,
                "confidence": element.confidence,
            }
        )

        click_method = "click_with_verification" if verify else "click_at"
        click_result = await hybrid_engine._call_tool(
            click_method,
            {"x": element.x, "y": element.y}
        )

        success = click_result.get("success", False) if click_result else False
        attempts = [
            {
                "attempt": 1,
                "method": click_method,
                "x": element.x,
                "y": element.y,
                "success": bool(success),
                "result": click_result,
            }
        ]

        recovered = False
        # Recovery: Bei fehlgeschlagenem ersten Klick einen zweiten Versuch mit
        # erzwungenem Template-Fallback durchführen.
        if (
            not success
            and enable_template_fallback
            and (template_name or text or element_type)
        ):
            retry_element = await hybrid_engine.smart_find_element(
                text=text,
                element_type=element_type,
                refine=False,
                template_name=template_name,
                enable_template_fallback=True,
            )
            if retry_element:
                pipeline_log.append(
                    {
                        "stage": "detect_recovery",
                        "method": retry_element.method,
                        "x": retry_element.x,
                        "y": retry_element.y,
                        "confidence": retry_element.confidence,
                    }
                )
                retry_click_result = await hybrid_engine._call_tool(
                    click_method,
                    {"x": retry_element.x, "y": retry_element.y},
                )
                retry_success = (
                    retry_click_result.get("success", False)
                    if retry_click_result
                    else False
                )
                attempts.append(
                    {
                        "attempt": 2,
                        "method": click_method,
                        "x": retry_element.x,
                        "y": retry_element.y,
                        "success": bool(retry_success),
                        "result": retry_click_result,
                    }
                )
                if retry_success:
                    success = True
                    recovered = True
                    element = retry_element
                    click_result = retry_click_result

        if success:
            log.info(f"Erfolgreich geklickt bei ({element.x}, {element.y})")
        else:
            log.warning(f"Klick möglicherweise fehlgeschlagen")

        runtime_ms = round((time.perf_counter() - start_ts) * 1000, 2)
        pipeline_log.append(
            {
                "stage": "final",
                "success": bool(success),
                "recovered": recovered,
                "attempt_count": len(attempts),
                "runtime_ms": runtime_ms,
            }
        )

        return {
            "clicked": True,
            "success": success,
            "method": element.method,
            "x": element.x,
            "y": element.y,
            "element": {
                "type": element.element_type,
                "text": element.text,
                "confidence": element.confidence
            },
            "click_result": click_result,
            "recovered": recovered,
            "attempt_count": len(attempts),
            "attempts": attempts,
            "runtime_ms": runtime_ms,
            "pipeline_log": pipeline_log,
        }

    except Exception as e:
        log.error(f"Hybrid-Klick-Fehler: {e}", exc_info=True)
        raise Exception(str(e))


@tool(
    name="hybrid_find_text_field_and_type",
    description="Findet ein Textfeld und tippt Text hinein.",
    parameters=[
        P("text", "string", "Text zum Eintippen"),
        P("field_text", "string", "Text im/beim Textfeld (Placeholder, Label)", required=False, default=None),
        P("field_type", "string", "Element-Typ: text field, input field, chat input, search bar", required=False, default="text field"),
        P("press_enter", "boolean", "Enter-Taste nach dem Tippen drücken?", required=False, default=False),
    ],
    capabilities=["vision", "detection"],
    category=C.VISION
)
async def hybrid_find_text_field_and_type(
    text: str,
    field_text: Optional[str] = None,
    field_type: str = "text field",
    press_enter: bool = False
) -> dict:
    """Findet ein Textfeld und tippt Text hinein."""
    try:
        element = await hybrid_engine.smart_find_element(
            text=field_text,
            element_type=field_type,
            refine=True,
            target_cursor="ibeam"
        )

        if not element:
            raise Exception(
                f"Textfeld nicht gefunden (field_text='{field_text}', type='{field_type}')"
            )

        click_result = await hybrid_engine._call_tool(
            "click_with_verification",
            {"x": element.x, "y": element.y}
        )

        type_result = await hybrid_engine._call_tool(
            "type_text",
            {"text": text, "press_enter": press_enter}
        )

        success = (
            click_result and click_result.get("success", False) and
            type_result and type_result.get("success", False)
        )

        return {
            "success": success,
            "typed": text,
            "method": element.method,
            "field_location": {"x": element.x, "y": element.y},
            "pressed_enter": press_enter,
            "click_result": click_result,
            "type_result": type_result
        }

    except Exception as e:
        log.error(f"Hybrid-Type-Fehler: {e}", exc_info=True)
        raise Exception(str(e))
