# tools/som_tool/tool.py
"""
Set-of-Mark (SoM) Tool für Timus Visual Agent.

Erkennt UI-Elemente auf dem Bildschirm, nummeriert sie und gibt
präzise Klick-Koordinaten zurück.

Features:
- Nutzt Qwen-VL (Qwen2-VL-7B-Instruct) für UI-Element-Erkennung
- Ein einziger VLM-Call für alle Element-Typen (statt N API-Calls)
- Nummeriert Elemente [1], [2], [3]...
- Berechnet Klick-Koordinaten (Mitte des Elements)
- Multi-Monitor Support mit Offset-Tracking

Version: 2.0 (Qwen-VL)
"""

import logging
import asyncio
import json
import re
import os
import mss
from PIL import Image, ImageDraw, ImageFont
from typing import List, Dict, Optional, Tuple, Any
from dataclasses import dataclass, field

from tools.tool_registry_v2 import tool, ToolParameter as P, ToolCategory as C
from tools.engines.qwen_vl_engine import qwen_vl_engine_instance
from dotenv import load_dotenv
from utils.coordinate_converter import (
    denormalize_point,
    normalize_point,
    sanitize_scale,
    to_click_point,
)

# --- Setup ---
load_dotenv()
log = logging.getLogger("som_tool")

# Konfiguration
ACTIVE_MONITOR = int(os.getenv("ACTIVE_MONITOR", "1"))
ZOOM_PASS_THRESHOLD = int(os.getenv("SOM_ZOOM_PASS_THRESHOLD", "5"))

# Erweiterte UI-Element-Typen
UI_ELEMENT_TYPES = [
    # Standard UI
    "button",
    "text field",
    "input field",
    "search bar",
    "icon",
    "link",
    "menu",
    "checkbox",
    "dropdown",
    # Chat-Interface spezifisch
    "chat input",
    "message box",
    "textbox",
    "textarea",
    "send button",
    "submit button",
]

# Qwen-VL Prompt für UI-Element-Erkennung (kein Action-Planning!)
SOM_DETECTION_PROMPT = """Du bist ein UI-Element-Detektor. Deine EINZIGE Aufgabe: Alle sichtbaren UI-Elemente im Screenshot auflisten.

AUFLOESUNG: {width}x{height} Pixel

Gib ALLE klickbaren/interaktiven Elemente als JSON-Array zurück.
Jedes Element hat: type, x, y (Center-Koordinaten in Pixeln), text (sichtbarer Text).

Erlaubte Typen: {element_types}

FORMAT (NUR JSON, KEINE Erklärungen):
[
  {{"type": "button", "x": {example_x}, "y": {example_y}, "text": "Search"}},
  {{"type": "text field", "x": {example_x}, "y": {example_y}, "text": ""}}
]

REGELN:
1. Koordinaten sind Pixel (0-{max_x} fuer x, 0-{max_y} fuer y)
2. x,y = CENTER des Elements
3. Liste ALLE sichtbaren interaktiven Elemente auf
4. NUR die erlaubten Typen verwenden
5. KEIN Action-Planning - NUR Element-Auflistung!
6. Maximal 20 Elemente"""


@dataclass
class UIElement:
    """Repräsentiert ein erkanntes UI-Element."""
    id: int
    element_type: str
    x_min: float  # Normalisiert 0-1
    y_min: float
    x_max: float
    y_max: float
    pixel_x: int  # Absolute Pixel (relativ zum Monitor)
    pixel_y: int
    pixel_width: int
    pixel_height: int
    center_x: int  # Klick-Koordinate (absolut für PyAutoGUI)
    center_y: int
    confidence: float = 1.0
    text: str = ""  # Falls Text erkannt wurde


class SetOfMarkEngine:
    """
    Engine für Set-of-Mark UI-Erkennung.

    Scannt den Bildschirm, erkennt UI-Elemente via Qwen-VL,
    nummeriert sie und berechnet Klick-Koordinaten.
    """

    def __init__(self):
        self.elements: List[UIElement] = []
        self.screenshot: Optional[Image.Image] = None
        self.screen_width: int = 0
        self.screen_height: int = 0
        self.monitor_offset_x: int = 0
        self.monitor_offset_y: int = 0
        self._last_scan_types: List[str] = []

    def _capture_screenshot(self) -> Image.Image:
        """Macht einen Screenshot des aktiven Monitors."""
        with mss.mss() as sct:
            # Monitor auswählen
            if ACTIVE_MONITOR < len(sct.monitors):
                monitor = sct.monitors[ACTIVE_MONITOR]
            else:
                monitor = sct.monitors[1] if len(sct.monitors) > 1 else sct.monitors[0]

            # Dimensionen und Offset speichern
            self.screen_width = monitor["width"]
            self.screen_height = monitor["height"]
            self.monitor_offset_x = monitor["left"]
            self.monitor_offset_y = monitor["top"]

            # Screenshot erstellen
            sct_img = sct.grab(monitor)
            img = Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")

            log.debug(
                f"Screenshot: {self.screen_width}x{self.screen_height} "
                f"von Monitor {ACTIVE_MONITOR} (Offset: {self.monitor_offset_x}, {self.monitor_offset_y})"
            )
            return img

    def _detect_all_elements(
        self,
        img: Image.Image,
        element_types: List[str],
        source: str = "base",
    ) -> List[Dict]:
        """
        Erkennt alle UI-Elemente mit einem einzigen Qwen-VL Call.
        """
        types_str = ", ".join(element_types)
        prompt = SOM_DETECTION_PROMPT.format(
            width=img.width,
            height=img.height,
            max_x=max(img.width - 1, 0),
            max_y=max(img.height - 1, 0),
            example_x=max(img.width // 2, 0),
            example_y=max(img.height // 2, 0),
            element_types=types_str,
        )

        log.info(f"Qwen-VL SoM-Erkennung [{source}]: {types_str}")

        result = qwen_vl_engine_instance.analyze_screenshot(
            image=img,
            task=f"Finde alle UI-Elemente: {types_str}",
            system_prompt=prompt,
            max_tokens=1024
        )

        if not result.get("success"):
            log.error(f"Qwen-VL Fehler: {result.get('error', 'unbekannt')}")
            return []

        raw_response = result.get("raw_response", "")
        log.debug(f"Qwen-VL Raw: {raw_response[:300]}")

        return self._parse_qwen_elements(
            raw_response,
            reference_width=img.width,
            reference_height=img.height,
            source=source,
        )

    def _parse_qwen_elements(
        self,
        raw_response: str,
        reference_width: int,
        reference_height: int,
        source: str = "base",
    ) -> List[Dict]:
        """
        Parst die Qwen-VL JSON-Antwort und konvertiert Pixel-Koordinaten
        zu normalisierten 0-1 Werten.
        """
        elements = []

        # JSON aus Response extrahieren
        json_match = re.search(r'```json\s*(\[.*?\])\s*```', raw_response, re.DOTALL)
        if not json_match:
            json_match = re.search(r'(\[.*?\])', raw_response, re.DOTALL)

        if not json_match:
            log.warning("Keine JSON-Elemente in Qwen-VL Antwort gefunden")
            return []

        try:
            data = json.loads(json_match.group(1))
            if not isinstance(data, list):
                data = [data]
        except json.JSONDecodeError as e:
            log.warning(f"JSON Parse Error: {e}")
            return []

        for item in data:
            if not isinstance(item, dict):
                continue

            elem_type = item.get("type", "unknown")
            px = item.get("x")
            py = item.get("y")
            text = item.get("text", "")

            if px is None or py is None:
                continue

            # Pixel -> Normalisiert (0-1), bezogen auf die echte Referenzauflösung
            norm_cx, norm_cy = normalize_point(
                pixel_x=float(px),
                pixel_y=float(py),
                reference_width=reference_width,
                reference_height=reference_height,
            )

            # Bounding Box um Center (5% Umkreis)
            box_size = 0.05
            elements.append({
                "x_min": max(0.0, norm_cx - box_size),
                "y_min": max(0.0, norm_cy - box_size),
                "x_max": min(1.0, norm_cx + box_size),
                "y_max": min(1.0, norm_cy + box_size),
                "center_x": norm_cx,
                "center_y": norm_cy,
                "element_type": elem_type,
                "text": text,
                "_method": "qwen_vl",
                "_source": source,
            })

        log.info(f"{len(elements)} Elemente aus Qwen-VL geparst")
        return elements

    def _run_zoom_pass(self, element_types: List[str]) -> List[Dict]:
        """
        Optionaler Zoom-Pass: zentraler Crop wird vergroessert analysiert
        und auf den Fullscreen-Normraum zurueckprojiziert.
        """
        if not self.screenshot:
            return []

        full_w = self.screenshot.width
        full_h = self.screenshot.height
        if full_w <= 0 or full_h <= 0:
            return []

        zoom_factor = 1.6
        crop_w = max(200, int(full_w / zoom_factor))
        crop_h = max(120, int(full_h / zoom_factor))
        crop_left = max(0, (full_w - crop_w) // 2)
        crop_top = max(0, (full_h - crop_h) // 2)

        crop = self.screenshot.crop((crop_left, crop_top, crop_left + crop_w, crop_top + crop_h))
        zoom_detected = self._detect_all_elements(crop, element_types, source="zoom")
        if not zoom_detected:
            return []

        projected: List[Dict] = []
        for obj in zoom_detected:
            x_min = (crop_left + obj["x_min"] * crop_w) / float(full_w)
            y_min = (crop_top + obj["y_min"] * crop_h) / float(full_h)
            x_max = (crop_left + obj["x_max"] * crop_w) / float(full_w)
            y_max = (crop_top + obj["y_max"] * crop_h) / float(full_h)
            center_x = (crop_left + obj["center_x"] * crop_w) / float(full_w)
            center_y = (crop_top + obj["center_y"] * crop_h) / float(full_h)

            projected.append(
                {
                    **obj,
                    "x_min": max(0.0, min(1.0, x_min)),
                    "y_min": max(0.0, min(1.0, y_min)),
                    "x_max": max(0.0, min(1.0, x_max)),
                    "y_max": max(0.0, min(1.0, y_max)),
                    "center_x": max(0.0, min(1.0, center_x)),
                    "center_y": max(0.0, min(1.0, center_y)),
                    "_source": "zoom_projected",
                }
            )

        return projected

    def _deduplicate_objects(self, objects: List[Dict], iou_threshold: float = 0.5) -> List[Dict]:
        """Entfernt doppelte Erkennungen."""
        if len(objects) <= 1:
            return objects

        unique = []
        for obj in objects:
            is_duplicate = False
            for existing in unique:
                x_min = max(obj["x_min"], existing["x_min"])
                y_min = max(obj["y_min"], existing["y_min"])
                x_max = min(obj["x_max"], existing["x_max"])
                y_max = min(obj["y_max"], existing["y_max"])

                if x_max > x_min and y_max > y_min:
                    intersection = (x_max - x_min) * (y_max - y_min)
                    area1 = (obj["x_max"] - obj["x_min"]) * (obj["y_max"] - obj["y_min"])
                    area2 = (existing["x_max"] - existing["x_min"]) * (existing["y_max"] - existing["y_min"])
                    union = area1 + area2 - intersection
                    iou = intersection / union if union > 0 else 0

                    if iou > iou_threshold:
                        is_duplicate = True
                        break

            if not is_duplicate:
                unique.append(obj)

        log.debug(f"  Deduplizierung: {len(objects)} -> {len(unique)} unique")
        return unique

    def _filter_oversized_boxes(self, objects: List[Dict]) -> List[Dict]:
        """Filtert Bounding Boxes die zu groß sind."""
        filtered = []
        for obj in objects:
            x_min = obj.get("x_min", 0)
            y_min = obj.get("y_min", 0)
            x_max = obj.get("x_max", 0)
            y_max = obj.get("y_max", 0)

            width = x_max - x_min
            height = y_max - y_min
            area = width * height

            pixel_width = int(width * self.screen_width)
            pixel_height = int(height * self.screen_height)

            if area > 0.40:
                continue
            if width > 0.80:
                continue
            if height > 0.70:
                continue
            if pixel_width > 800 or pixel_height > 600:
                continue
            if width <= 0.01 or height <= 0.01:
                continue

            filtered.append(obj)

        return filtered

    def _normalized_to_pixels(
        self,
        x_min: float,
        y_min: float,
        x_max: float,
        y_max: float,
        center_x: Optional[float] = None,
        center_y: Optional[float] = None
    ) -> Tuple[int, int, int, int, int, int]:
        """Konvertiert normalisierte Koordinaten (0-1) zu absoluten Pixeln."""
        relative_pixel_x, relative_pixel_y = denormalize_point(
            x_min, y_min, self.screen_width, self.screen_height
        )
        relative_pixel_x_max, relative_pixel_y_max = denormalize_point(
            x_max, y_max, self.screen_width, self.screen_height
        )

        width = relative_pixel_x_max - relative_pixel_x
        height = relative_pixel_y_max - relative_pixel_y

        if center_x is not None and center_y is not None:
            relative_center_x, relative_center_y = denormalize_point(
                center_x, center_y, self.screen_width, self.screen_height
            )
        else:
            relative_center_x = relative_pixel_x + width // 2
            relative_center_y = relative_pixel_y + height // 2

        display_scale = sanitize_scale(os.getenv("DISPLAY_SCALE", "1.0"), default=1.0)
        pixel_center_x, pixel_center_y = to_click_point(
            relative_pixel_x=relative_center_x,
            relative_pixel_y=relative_center_y,
            monitor_offset_x=self.monitor_offset_x,
            monitor_offset_y=self.monitor_offset_y,
            dpi_scale=display_scale,
        )

        return relative_pixel_x, relative_pixel_y, width, height, pixel_center_x, pixel_center_y

    async def scan_screen(self, element_types: Optional[List[str]] = None, use_zoom: bool = True) -> List[UIElement]:
        """Scannt den Bildschirm nach UI-Elementen via Qwen-VL."""
        self.elements = []

        default_priority_types = [
            "text field", "input field", "textbox", "chat input",
            "button", "send button",
        ]

        types_to_scan = element_types or default_priority_types
        self._last_scan_types = types_to_scan

        self.screenshot = self._capture_screenshot()

        log.info(f"Scanne nach {len(types_to_scan)} Element-Typen via Qwen-VL: {', '.join(types_to_scan[:3])}...")

        detected = self._detect_all_elements(self.screenshot, types_to_scan, source="base")
        if use_zoom and len(detected) <= ZOOM_PASS_THRESHOLD:
            detected.extend(self._run_zoom_pass(types_to_scan))
        detected = self._deduplicate_objects(detected)
        detected = self._filter_oversized_boxes(detected)

        element_id = 1
        for obj in detected:
            x_min = obj.get("x_min", 0)
            y_min = obj.get("y_min", 0)
            x_max = obj.get("x_max", 0)
            y_max = obj.get("y_max", 0)
            point_center_x = obj.get("center_x")
            point_center_y = obj.get("center_y")
            elem_type = obj.get("element_type", "unknown")
            elem_text = obj.get("text", "")

            if x_max <= x_min or y_max <= y_min:
                continue

            px, py, w, h, cx, cy = self._normalized_to_pixels(
                x_min, y_min, x_max, y_max,
                center_x=point_center_x, center_y=point_center_y
            )

            element = UIElement(
                id=element_id,
                element_type=elem_type,
                x_min=x_min,
                y_min=y_min,
                x_max=x_max,
                y_max=y_max,
                pixel_x=px,
                pixel_y=py,
                pixel_width=w,
                pixel_height=h,
                center_x=cx,
                center_y=cy,
                confidence=obj.get("confidence", 1.0),
                text=elem_text
            )

            self.elements.append(element)
            element_id += 1

        log.info(f"{len(self.elements)} Elemente erkannt")
        return self.elements

    def get_element_by_id(self, element_id: int) -> Optional[UIElement]:
        """Gibt ein Element anhand seiner ID zurück."""
        for elem in self.elements:
            if elem.id == element_id:
                return elem
        return None

    def get_elements_by_type(self, element_type: str) -> List[UIElement]:
        """Gibt alle Elemente eines bestimmten Typs zurück."""
        return [e for e in self.elements if e.element_type == element_type]

    def create_annotated_screenshot(self) -> Optional[Image.Image]:
        """Erstellt einen Screenshot mit nummerierten Markierungen."""
        if not self.screenshot:
            return None

        img = self.screenshot.copy()
        draw = ImageDraw.Draw(img)

        try:
            font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 16)
        except:
            try:
                font = ImageFont.truetype("/usr/share/fonts/TTF/DejaVuSans-Bold.ttf", 16)
            except:
                font = ImageFont.load_default()

        type_colors = {
            "button": "red",
            "text field": "blue",
            "input field": "blue",
            "search bar": "green",
            "chat input": "green",
            "link": "purple",
            "icon": "orange",
        }

        for elem in self.elements:
            color = type_colors.get(elem.element_type, "red")

            draw.rectangle(
                [elem.pixel_x, elem.pixel_y,
                 elem.pixel_x + elem.pixel_width, elem.pixel_y + elem.pixel_height],
                outline=color,
                width=2
            )

            label = f"[{elem.id}]"
            label_width = len(label) * 8 + 4
            draw.rectangle(
                [elem.pixel_x, elem.pixel_y - 20, elem.pixel_x + label_width, elem.pixel_y],
                fill=color
            )

            draw.text((elem.pixel_x + 2, elem.pixel_y - 18), label, fill="white", font=font)

        return img

    def to_dict_list(self) -> List[Dict[str, Any]]:
        """Konvertiert alle Elemente zu einer Liste von Dicts."""
        return [
            {
                "id": e.id,
                "type": e.element_type,
                "x": e.center_x,
                "y": e.center_y,
                "center_x": e.center_x,
                "center_y": e.center_y,
                "click_x": e.center_x,
                "click_y": e.center_y,
                "bounds": {
                    "x": e.pixel_x,
                    "y": e.pixel_y,
                    "width": e.pixel_width,
                    "height": e.pixel_height
                },
                "text": e.text,
                "confidence": e.confidence
            }
            for e in self.elements
        ]


# Globale Engine-Instanz
som_engine = SetOfMarkEngine()


# ==============================================================================
# RPC METHODEN
# ==============================================================================

@tool(
    name="scan_ui_elements",
    description="Scannt den Bildschirm nach klickbaren UI-Elementen via Qwen-VL. Gibt IDs und Koordinaten zurück.",
    parameters=[
        P("element_types", "array", "Liste von Element-Typen (z.B. button, text field, search bar, chat input)", required=False, default=None),
        P("use_zoom", "boolean", "Multi-Resolution Erkennung", required=False, default=True),
    ],
    capabilities=["vision", "ui", "som"],
    category=C.UI
)
async def scan_ui_elements(element_types: Optional[List[str]] = None, use_zoom: bool = True) -> dict:
    """
    Scannt den Bildschirm nach klickbaren UI-Elementen.
    """
    try:
        elements = await som_engine.scan_screen(element_types, use_zoom=use_zoom)

        if not elements:
            return {
                "count": 0,
                "elements": [],
                "message": "Keine UI-Elemente erkannt. Versuche anderen Element-Typ oder prüfe ob App im Fokus ist."
            }

        zoom_msg = " (mit Zoom-Erkennung)" if use_zoom else ""
        return {
            "count": len(elements),
            "elements": som_engine.to_dict_list(),
            "message": f"{len(elements)} Elemente erkannt{zoom_msg}. Verwende click_at(x, y) mit den angegebenen Koordinaten."
        }

    except Exception as e:
        log.error(f"Fehler beim Scannen: {e}", exc_info=True)
        raise Exception(str(e))


@tool(
    name="get_element_coordinates",
    description="Gibt die Klick-Koordinaten für ein Element zurück (aus scan_ui_elements).",
    parameters=[
        P("element_id", "integer", "Die ID des Elements (aus scan_ui_elements)"),
    ],
    capabilities=["vision", "ui", "som"],
    category=C.UI
)
async def get_element_coordinates(element_id: int) -> dict:
    """
    Gibt die Klick-Koordinaten für ein Element zurück.
    """
    element = som_engine.get_element_by_id(element_id)

    if not element:
        raise Exception(
            f"Element [{element_id}] nicht gefunden. Führe zuerst scan_ui_elements aus."
        )

    return {
        "id": element.id,
        "type": element.element_type,
        "x": element.center_x,
        "y": element.center_y,
        "instruction": f"Nutze click_at(x={element.center_x}, y={element.center_y})"
    }


@tool(
    name="find_and_click_element",
    description="Sucht ein Element eines bestimmten Typs und gibt Klick-Koordinaten zurück. Kombiniert scan + get_coordinates.",
    parameters=[
        P("element_type", "string", "z.B. button, search bar, text field, chat input"),
    ],
    capabilities=["vision", "ui", "som"],
    category=C.UI
)
async def find_and_click_element(element_type: str) -> dict:
    """
    Sucht ein Element eines bestimmten Typs und gibt Klick-Koordinaten zurück.
    """
    try:
        elements = await som_engine.scan_screen([element_type])

        if not elements:
            raise Exception(
                f"Kein '{element_type}' auf dem Bildschirm gefunden. "
                f"Verfügbare Typen: {', '.join(UI_ELEMENT_TYPES[:5])}..."
            )

        elem = elements[0]

        return {
            "found": True,
            "type": element_type,
            "x": elem.center_x,
            "y": elem.center_y,
            "total_found": len(elements),
            "instruction": f"Nutze click_at(x={elem.center_x}, y={elem.center_y})"
        }

    except Exception as e:
        log.error(f"Fehler bei find_and_click: {e}", exc_info=True)
        raise Exception(str(e))


@tool(
    name="describe_screen_elements",
    description="Scannt alle UI-Elemente und gibt eine Beschreibung zurück. Nützlich für den Agent um zu verstehen was auf dem Bildschirm ist.",
    parameters=[],
    capabilities=["vision", "ui", "som"],
    category=C.UI
)
async def describe_screen_elements() -> dict:
    """
    Scannt alle UI-Elemente und gibt eine Beschreibung zurück.
    """
    try:
        priority_types = [
            "button", "text field", "search bar", "chat input",
            "link", "input field", "send button"
        ]
        elements = await som_engine.scan_screen(priority_types)

        if not elements:
            return {
                "description": "Keine klickbaren Elemente erkannt.",
                "elements": []
            }

        lines = [f"Erkannte UI-Elemente ({len(elements)}):"]
        for e in elements:
            lines.append(f"  [{e.id}] {e.element_type} bei ({e.center_x}, {e.center_y})")

        return {
            "description": "\n".join(lines),
            "elements": som_engine.to_dict_list()
        }

    except Exception as e:
        log.error(f"Fehler bei describe_screen: {e}", exc_info=True)
        raise Exception(str(e))


@tool(
    name="save_annotated_screenshot",
    description="Speichert einen Screenshot mit markierten UI-Elementen. Nützlich für Debugging.",
    parameters=[
        P("filename", "string", "Dateiname für den Screenshot", required=False, default="som_screenshot.png"),
    ],
    capabilities=["vision", "ui", "som"],
    category=C.UI
)
async def save_annotated_screenshot(filename: str = "som_screenshot.png") -> dict:
    """
    Speichert einen Screenshot mit markierten UI-Elementen.
    """
    try:
        if not som_engine.elements:
            await som_engine.scan_screen()

        img = som_engine.create_annotated_screenshot()

        if not img:
            raise Exception("Kein Screenshot verfügbar")

        save_dir = os.path.expanduser("~/dev/timus/results")
        os.makedirs(save_dir, exist_ok=True)
        save_path = os.path.join(save_dir, filename)
        img.save(save_path)

        log.info(f"Screenshot gespeichert: {save_path}")

        return {
            "saved": True,
            "path": save_path,
            "elements_marked": len(som_engine.elements)
        }

    except Exception as e:
        log.error(f"Fehler beim Speichern: {e}", exc_info=True)
        raise Exception(str(e))


@tool(
    name="get_supported_element_types",
    description="Gibt alle unterstützten UI-Element-Typen zurück.",
    parameters=[],
    capabilities=["vision", "ui", "som"],
    category=C.UI
)
async def get_supported_element_types() -> dict:
    """
    Gibt alle unterstützten UI-Element-Typen zurück.
    """
    return {
        "types": UI_ELEMENT_TYPES,
        "count": len(UI_ELEMENT_TYPES),
        "categories": {
            "standard": ["button", "text field", "input field", "search bar", "icon", "link", "menu", "checkbox", "dropdown"],
            "chat_interface": ["chat input", "message box", "textbox", "textarea", "send button", "submit button"]
        }
    }
