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
import httpx
from typing import List, Dict, Optional, Union, Tuple
from dataclasses import dataclass
from jsonrpcserver import method, Success, Error

from tools.universal_tool_caller import register_tool
from dotenv import load_dotenv

# --- Setup ---
load_dotenv()
log = logging.getLogger("hybrid_detection")

# MCP Server URL für Tool-Aufrufe
MCP_URL = os.getenv("MCP_URL", "http://127.0.0.1:5000")
TIMEOUT = 180.0


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

    async def find_by_text(self, text: str) -> Optional[DetectedElement]:
        """
        Findet ein Element anhand seines Textes (sehr präzise).
        Nutzt OCR + Visual Grounding.
        """
        log.info(f"🔍 Text-Suche: '{text}'")

        # Visual Grounding Tool nutzen
        result = await self._call_tool("find_text_coordinates", {"text_to_find": text})

        if result and result.get("found"):
            coords = result.get("coordinates", {})
            x = coords.get("center_x", coords.get("x", 0))
            y = coords.get("center_y", coords.get("y", 0))

            log.info(f"✅ Text gefunden bei ({x}, {y})")

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

        log.warning(f"⚠️ Text '{text}' nicht gefunden")
        return None

    async def find_by_object_detection(
        self,
        element_type: str,
        prefer_index: int = 0
    ) -> Optional[DetectedElement]:
        """
        Findet ein Element via Object Detection (SoM Tool).
        Gut für Icons, Buttons ohne Text.
        """
        log.info(f"🔍 Object Detection: '{element_type}'")

        # SoM Tool nutzen
        result = await self._call_tool("scan_ui_elements", {"element_types": [element_type]})

        if result and result.get("count", 0) > 0:
            elements = result.get("elements", [])
            if prefer_index < len(elements):
                elem = elements[prefer_index]

                log.info(f"✅ {element_type} gefunden bei ({elem['x']}, {elem['y']})")

                return DetectedElement(
                    method="som",
                    element_type=element_type,
                    x=elem["x"],
                    y=elem["y"],
                    confidence=elem.get("confidence", 0.8),
                    bounds=elem.get("bounds"),
                    metadata={"total_found": len(elements), "index": prefer_index}
                )

        log.warning(f"⚠️ {element_type} nicht gefunden")
        return None

    async def refine_with_mouse_feedback(
        self,
        x: int,
        y: int,
        target_cursor: str = "ibeam",
        radius: int = 80
    ) -> Optional[Tuple[int, int, str]]:
        """
        Verfeinert Koordinaten mit Mouse Feedback Tool.
        Sucht in der Umgebung nach dem richtigen Cursor-Typ.

        Returns:
            (refined_x, refined_y, cursor_type) oder None
        """
        log.info(f"🔍 Mouse Feedback Verfeinerung um ({x}, {y}), Ziel: {target_cursor}")

        # Mouse Feedback Tool nutzen
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

            log.info(f"✅ Verfeinert: ({refined_x}, {refined_y}), Cursor: {cursor}")
            return refined_x, refined_y, cursor

        log.warning("⚠️ Mouse Feedback Verfeinerung fehlgeschlagen")
        return None

    async def smart_find_element(
        self,
        text: Optional[str] = None,
        element_type: Optional[str] = None,
        refine: bool = True,
        target_cursor: Optional[str] = None
    ) -> Optional[DetectedElement]:
        """
        Intelligente Element-Suche mit Hybrid-Ansatz.

        Strategie:
        1. Wenn Text gegeben: OCR-basierte Suche (sehr präzise)
        2. Wenn element_type: Object Detection (SoM)
        3. Optional: Mouse Feedback Verfeinerung

        Args:
            text: Text des Elements (höchste Priorität)
            element_type: Typ des Elements ("button", "text field", etc.)
            refine: Mit Mouse Feedback verfeinern?
            target_cursor: Erwarteter Cursor-Typ für Verfeinerung

        Returns:
            DetectedElement oder None
        """
        element = None

        # 1. Text-basierte Suche (wenn Text gegeben)
        if text:
            element = await self.find_by_text(text)

        # 2. Object Detection (wenn kein Text oder Text-Suche fehlgeschlagen)
        if not element and element_type:
            element = await self.find_by_object_detection(element_type)

        # 3. Mouse Feedback Verfeinerung
        if element and refine:
            # Standard-Cursor für Element-Typ ableiten
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
                # Element-Koordinaten aktualisieren
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
                log.info(f"✅ Verfeinert: ({old_x},{old_y}) → ({refined_x},{refined_y})")

        return element


# Globale Engine-Instanz
hybrid_engine = HybridDetectionEngine()


# ==============================================================================
# RPC METHODEN
# ==============================================================================

@method
async def hybrid_find_element(
    text: Optional[str] = None,
    element_type: Optional[str] = None,
    refine: bool = True,
    target_cursor: Optional[str] = None
) -> Union[Success, Error]:
    """
    Intelligente Element-Suche mit Hybrid-Ansatz.

    Kombiniert OCR (für Text), Object Detection (für Icons/Buttons)
    und Mouse Feedback (für Feinabstimmung).

    Args:
        text: Text des Elements (höchste Priorität, z.B. "Anmelden", "Suchen")
        element_type: Typ des Elements ("button", "text field", "icon", etc.)
        refine: Mit Mouse Feedback verfeinern? (default: True)
        target_cursor: Erwarteter Cursor-Typ ("ibeam", "hand", "arrow")

    Returns:
        Success mit Element-Daten oder Error

    Beispiele:
        hybrid_find_element(text="Anmelden")  # Sucht Button/Link mit Text "Anmelden"
        hybrid_find_element(element_type="text field", refine=True)  # Findet Textfeld
        hybrid_find_element(text="Suchen", element_type="search bar", refine=True)
    """
    if not text and not element_type:
        return Error(
            code=-32602,
            message="Mindestens 'text' oder 'element_type' muss angegeben sein"
        )

    try:
        element = await hybrid_engine.smart_find_element(
            text=text,
            element_type=element_type,
            refine=refine,
            target_cursor=target_cursor
        )

        if not element:
            return Error(
                code=-32001,
                message=f"Element nicht gefunden (text='{text}', type='{element_type}')"
            )

        return Success({
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
        })

    except Exception as e:
        log.error(f"Hybrid-Fehler: {e}", exc_info=True)
        return Error(code=-32000, message=str(e))


@method
async def hybrid_find_and_click(
    text: Optional[str] = None,
    element_type: Optional[str] = None,
    refine: bool = True,
    verify: bool = True
) -> Union[Success, Error]:
    """
    Findet ein Element mit Hybrid-Ansatz und klickt darauf.

    Args:
        text: Text des Elements
        element_type: Typ des Elements
        refine: Mit Mouse Feedback verfeinern?
        verify: Cursor vor dem Klick überprüfen?

    Returns:
        Success mit Klick-Ergebnis oder Error
    """
    try:
        # 1. Element finden
        element = await hybrid_engine.smart_find_element(
            text=text,
            element_type=element_type,
            refine=refine
        )

        if not element:
            return Error(
                code=-32001,
                message=f"Element nicht gefunden (text='{text}', type='{element_type}')"
            )

        # 2. Klicken
        click_method = "click_with_verification" if verify else "click_at"
        click_result = await hybrid_engine._call_tool(
            click_method,
            {"x": element.x, "y": element.y}
        )

        success = click_result.get("success", False) if click_result else False

        if success:
            log.info(f"✅ Erfolgreich geklickt bei ({element.x}, {element.y})")
        else:
            log.warning(f"⚠️ Klick möglicherweise fehlgeschlagen")

        return Success({
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
            "click_result": click_result
        })

    except Exception as e:
        log.error(f"Hybrid-Klick-Fehler: {e}", exc_info=True)
        return Error(code=-32000, message=str(e))


@method
async def hybrid_find_text_field_and_type(
    text: str,
    field_text: Optional[str] = None,
    field_type: str = "text field",
    press_enter: bool = False
) -> Union[Success, Error]:
    """
    Findet ein Textfeld und tippt Text hinein.

    Args:
        text: Text zum Eintippen
        field_text: Text im/beim Textfeld (z.B. Placeholder, Label)
        field_type: Element-Typ ("text field", "input field", "chat input", "search bar")
        press_enter: Enter-Taste nach dem Tippen drücken?

    Returns:
        Success mit Ergebnis oder Error

    Beispiel:
        hybrid_find_text_field_and_type(
            text="Hallo Welt",
            field_text="Nachricht eingeben",
            press_enter=True
        )
    """
    try:
        # 1. Textfeld finden
        element = await hybrid_engine.smart_find_element(
            text=field_text,
            element_type=field_type,
            refine=True,
            target_cursor="ibeam"
        )

        if not element:
            return Error(
                code=-32001,
                message=f"Textfeld nicht gefunden (field_text='{field_text}', type='{field_type}')"
            )

        # 2. Klicken (mit Verifikation dass Cursor = ibeam)
        click_result = await hybrid_engine._call_tool(
            "click_with_verification",
            {"x": element.x, "y": element.y}
        )

        # 3. Text tippen
        type_result = await hybrid_engine._call_tool(
            "type_text",
            {"text": text, "press_enter": press_enter}
        )

        success = (
            click_result and click_result.get("success", False) and
            type_result and type_result.get("success", False)
        )

        return Success({
            "success": success,
            "typed": text,
            "method": element.method,
            "field_location": {"x": element.x, "y": element.y},
            "pressed_enter": press_enter,
            "click_result": click_result,
            "type_result": type_result
        })

    except Exception as e:
        log.error(f"Hybrid-Type-Fehler: {e}", exc_info=True)
        return Error(code=-32000, message=str(e))


# ==============================================================================
# REGISTRIERUNG
# ==============================================================================

register_tool("hybrid_find_element", hybrid_find_element)
register_tool("hybrid_find_and_click", hybrid_find_and_click)
register_tool("hybrid_find_text_field_and_type", hybrid_find_text_field_and_type)

log.info("✅ Hybrid Detection Tool v1.0 registriert")
log.info("   Kombiniert: OCR + Object Detection + Mouse Feedback")
log.info("   Tools: hybrid_find_element, hybrid_find_and_click, hybrid_find_text_field_and_type")
