# tools/som_tool/tool.py
"""
Set-of-Mark (SoM) Tool für Timus Visual Agent.

Erkennt UI-Elemente auf dem Bildschirm, nummeriert sie und gibt
präzise Klick-Koordinaten zurück.

Features:
- Nutzt Moondream /v1/detect für Objekterkennung
- Kombiniert mit OCR für Text-Elemente
- Nummeriert Elemente [1], [2], [3]...
- Berechnet Klick-Koordinaten (Mitte des Elements)
"""

import logging
import asyncio
import os
import base64
import httpx
import mss
from PIL import Image, ImageDraw, ImageFont
import io
from typing import List, Dict, Optional, Tuple, Union
from dataclasses import dataclass
from jsonrpcserver import method, Success, Error

from tools.universal_tool_caller import register_tool
from dotenv import load_dotenv

# --- Setup ---
load_dotenv()
log = logging.getLogger("som_tool")

# Konfiguration
MOONDREAM_BASE_URL = os.getenv("MOONDREAM_API_BASE", "http://localhost:2021/v1")
ACTIVE_MONITOR = int(os.getenv("ACTIVE_MONITOR", "1"))
TIMEOUT = 60.0

# UI-Element-Typen die erkannt werden sollen
UI_ELEMENT_TYPES = [
    "button",
    "text field", 
    "input field",
    "search bar",
    "icon",
    "link",
    "menu",
    "checkbox",
    "dropdown"
]

# HTTP Client
http_client = httpx.AsyncClient(timeout=TIMEOUT)


@dataclass
class UIElement:
    """Repräsentiert ein erkanntes UI-Element."""
    id: int
    element_type: str
    x_min: float  # Normalisiert 0-1
    y_min: float
    x_max: float
    y_max: float
    pixel_x: int  # Absolute Pixel
    pixel_y: int
    pixel_width: int
    pixel_height: int
    center_x: int  # Klick-Koordinate
    center_y: int
    confidence: float = 1.0
    text: str = ""  # Falls Text erkannt wurde


class SetOfMarkEngine:
    """
    Engine für Set-of-Mark UI-Erkennung.
    """
    
    def __init__(self):
        self.elements: List[UIElement] = []
        self.screenshot: Optional[Image.Image] = None
        self.screen_width: int = 1920
        self.screen_height: int = 1200
        self.monitor_offset_x: int = 0
        self.monitor_offset_y: int = 0
    
    def _capture_screenshot(self) -> Image.Image:
        """Macht einen Screenshot des aktiven Monitors."""
        with mss.mss() as sct:
            if ACTIVE_MONITOR < len(sct.monitors):
                monitor = sct.monitors[ACTIVE_MONITOR]
            else:
                monitor = sct.monitors[1] if len(sct.monitors) > 1 else sct.monitors[0]
            
            self.screen_width = monitor["width"]
            self.screen_height = monitor["height"]
            self.monitor_offset_x = monitor["left"]
            self.monitor_offset_y = monitor["top"]
            
            sct_img = sct.grab(monitor)
            img = Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")
            
            log.debug(f"Screenshot: {self.screen_width}x{self.screen_height} von Monitor {ACTIVE_MONITOR}")
            return img
    
    def _image_to_base64(self, img: Image.Image, max_size: Tuple[int, int] = (800, 600)) -> str:
        """Konvertiert PIL Image zu Base64."""
        img_copy = img.copy()
        img_copy.thumbnail(max_size)
        buffer = io.BytesIO()
        img_copy.save(buffer, format="PNG")
        return base64.b64encode(buffer.getvalue()).decode()
    
    async def _detect_elements(self, img: Image.Image, element_type: str) -> List[Dict]:
        """Ruft Moondream detect für einen Element-Typ auf."""
        b64 = self._image_to_base64(img)
        
        try:
            response = await http_client.post(
                f"{MOONDREAM_BASE_URL}/detect",
                json={
                    "image_url": f"data:image/png;base64,{b64}",
                    "object": element_type
                },
                timeout=TIMEOUT
            )
            response.raise_for_status()
            result = response.json()
            
            if "objects" in result:
                return result["objects"]
            elif "error" in result:
                log.warning(f"Moondream Fehler für '{element_type}': {result['error']}")
            
            return []
            
        except httpx.TimeoutException:
            log.warning(f"Timeout bei Detect für '{element_type}'")
            return []
        except Exception as e:
            log.error(f"Fehler bei Detect für '{element_type}': {e}")
            return []
    
    def _normalized_to_pixels(self, x_min: float, y_min: float, x_max: float, y_max: float) -> Tuple[int, int, int, int, int, int]:
        """
        Konvertiert normalisierte Koordinaten (0-1) zu Pixeln.
        Returns: (pixel_x, pixel_y, width, height, center_x, center_y)
        """
        pixel_x = int(x_min * self.screen_width)
        pixel_y = int(y_min * self.screen_height)
        pixel_x_max = int(x_max * self.screen_width)
        pixel_y_max = int(y_max * self.screen_height)
        
        width = pixel_x_max - pixel_x
        height = pixel_y_max - pixel_y
        
        center_x = pixel_x + width // 2
        center_y = pixel_y + height // 2
        
        return pixel_x, pixel_y, width, height, center_x, center_y
    
    async def scan_screen(self, element_types: Optional[List[str]] = None) -> List[UIElement]:
        """
        Scannt den Bildschirm nach UI-Elementen.
        
        Args:
            element_types: Liste von Element-Typen zum Suchen (default: alle)
        
        Returns:
            Liste von erkannten UIElements
        """
        self.elements = []
        types_to_scan = element_types or UI_ELEMENT_TYPES
        
        # Screenshot machen
        self.screenshot = self._capture_screenshot()
        log.info(f"🔍 Scanne nach {len(types_to_scan)} Element-Typen...")
        
        element_id = 1
        
        # Für jeden Element-Typ Moondream aufrufen
        for elem_type in types_to_scan:
            detected = await self._detect_elements(self.screenshot, elem_type)
            
            for obj in detected:
                x_min = obj.get("x_min", 0)
                y_min = obj.get("y_min", 0)
                x_max = obj.get("x_max", 0)
                y_max = obj.get("y_max", 0)
                
                # Zu Pixeln konvertieren
                px, py, w, h, cx, cy = self._normalized_to_pixels(x_min, y_min, x_max, y_max)
                
                # Element erstellen
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
                    confidence=obj.get("confidence", 1.0)
                )
                
                self.elements.append(element)
                element_id += 1
                
                log.debug(f"  [{element.id}] {elem_type} @ ({cx}, {cy})")
        
        log.info(f"✅ {len(self.elements)} Elemente erkannt")
        return self.elements
    
    def get_element_by_id(self, element_id: int) -> Optional[UIElement]:
        """Gibt ein Element anhand seiner ID zurück."""
        for elem in self.elements:
            if elem.id == element_id:
                return elem
        return None
    
    def create_annotated_screenshot(self) -> Image.Image:
        """
        Erstellt einen Screenshot mit nummerierten Markierungen.
        Nützlich für Debugging und Visualisierung.
        """
        if not self.screenshot:
            return None
        
        img = self.screenshot.copy()
        draw = ImageDraw.Draw(img)
        
        # Versuche eine Schrift zu laden
        try:
            font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 16)
        except:
            font = ImageFont.load_default()
        
        for elem in self.elements:
            # Rechteck zeichnen
            draw.rectangle(
                [elem.pixel_x, elem.pixel_y, 
                 elem.pixel_x + elem.pixel_width, elem.pixel_y + elem.pixel_height],
                outline="red",
                width=2
            )
            
            # Nummer zeichnen
            label = f"[{elem.id}]"
            draw.rectangle(
                [elem.pixel_x, elem.pixel_y - 20, elem.pixel_x + 30, elem.pixel_y],
                fill="red"
            )
            draw.text((elem.pixel_x + 2, elem.pixel_y - 18), label, fill="white", font=font)
        
        return img
    
    def to_dict_list(self) -> List[Dict]:
        """Konvertiert alle Elemente zu einer Liste von Dicts."""
        return [
            {
                "id": e.id,
                "type": e.element_type,
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

@method
async def scan_ui_elements(element_types: Optional[List[str]] = None) -> Union[Success, Error]:
    """
    Scannt den Bildschirm nach klickbaren UI-Elementen.
    
    Args:
        element_types: Optional - Liste von Element-Typen 
                       (z.B. ["button", "text field", "icon"])
                       Default: Alle unterstützten Typen
    
    Returns:
        Liste von erkannten Elementen mit IDs und Koordinaten
    """
    try:
        elements = await som_engine.scan_screen(element_types)
        
        if not elements:
            return Success({
                "count": 0,
                "elements": [],
                "message": "Keine UI-Elemente erkannt"
            })
        
        return Success({
            "count": len(elements),
            "elements": som_engine.to_dict_list(),
            "message": f"{len(elements)} Elemente erkannt. Nutze get_element_coordinates(id) für Klick-Koordinaten."
        })
        
    except Exception as e:
        log.error(f"Fehler beim Scannen: {e}", exc_info=True)
        return Error(code=-32000, message=str(e))


@method
async def get_element_coordinates(element_id: int) -> Union[Success, Error]:
    """
    Gibt die Klick-Koordinaten für ein Element zurück.
    
    Args:
        element_id: Die ID des Elements (aus scan_ui_elements)
    
    Returns:
        x, y Koordinaten für click_at
    """
    element = som_engine.get_element_by_id(element_id)
    
    if not element:
        return Error(
            code=-32001, 
            message=f"Element [{element_id}] nicht gefunden. Führe zuerst scan_ui_elements aus."
        )
    
    return Success({
        "id": element.id,
        "type": element.element_type,
        "x": element.center_x,
        "y": element.center_y,
        "instruction": f"Nutze click_at(x={element.center_x}, y={element.center_y})"
    })


@method
async def find_and_click_element(element_type: str) -> Union[Success, Error]:
    """
    Sucht ein Element eines bestimmten Typs und gibt Klick-Koordinaten zurück.
    Kombiniert scan + get_coordinates in einem Aufruf.
    
    Args:
        element_type: z.B. "button", "search bar", "text field"
    
    Returns:
        Koordinaten des ersten gefundenen Elements
    """
    try:
        elements = await som_engine.scan_screen([element_type])
        
        if not elements:
            return Error(
                code=-32002,
                message=f"Kein '{element_type}' auf dem Bildschirm gefunden"
            )
        
        # Erstes Element zurückgeben
        elem = elements[0]
        
        return Success({
            "found": True,
            "type": element_type,
            "x": elem.center_x,
            "y": elem.center_y,
            "total_found": len(elements),
            "instruction": f"Nutze click_at(x={elem.center_x}, y={elem.center_y})"
        })
        
    except Exception as e:
        log.error(f"Fehler bei find_and_click: {e}", exc_info=True)
        return Error(code=-32000, message=str(e))


@method
async def describe_screen_elements() -> Union[Success, Error]:
    """
    Scannt alle UI-Elemente und gibt eine Beschreibung zurück.
    Nützlich für den Agent um zu verstehen was auf dem Bildschirm ist.
    
    Returns:
        Textuelle Beschreibung aller Elemente
    """
    try:
        # Nur die wichtigsten Element-Typen scannen (schneller)
        elements = await som_engine.scan_screen(["button", "text field", "search bar", "link"])
        
        if not elements:
            return Success({
                "description": "Keine klickbaren Elemente erkannt.",
                "elements": []
            })
        
        # Beschreibung erstellen
        lines = [f"Erkannte UI-Elemente ({len(elements)}):"]
        for e in elements:
            lines.append(f"  [{e.id}] {e.element_type} bei ({e.center_x}, {e.center_y})")
        
        return Success({
            "description": "\n".join(lines),
            "elements": som_engine.to_dict_list()
        })
        
    except Exception as e:
        log.error(f"Fehler bei describe_screen: {e}", exc_info=True)
        return Error(code=-32000, message=str(e))


@method  
async def save_annotated_screenshot(filename: str = "som_screenshot.png") -> Union[Success, Error]:
    """
    Speichert einen Screenshot mit markierten UI-Elementen.
    Nützlich für Debugging.
    
    Args:
        filename: Dateiname für den Screenshot
    """
    try:
        if not som_engine.elements:
            # Erst scannen
            await som_engine.scan_screen()
        
        img = som_engine.create_annotated_screenshot()
        
        if not img:
            return Error(code=-32003, message="Kein Screenshot verfügbar")
        
        # Speichern
        save_path = os.path.expanduser(f"~/dev/timus/results/{filename}")
        os.makedirs(os.path.dirname(save_path), exist_ok=True)
        img.save(save_path)
        
        log.info(f"📸 Screenshot gespeichert: {save_path}")
        
        return Success({
            "saved": True,
            "path": save_path,
            "elements_marked": len(som_engine.elements)
        })
        
    except Exception as e:
        log.error(f"Fehler beim Speichern: {e}", exc_info=True)
        return Error(code=-32000, message=str(e))


# ==============================================================================
# REGISTRIERUNG
# ==============================================================================

register_tool("scan_ui_elements", scan_ui_elements)
register_tool("get_element_coordinates", get_element_coordinates)
register_tool("find_and_click_element", find_and_click_element)
register_tool("describe_screen_elements", describe_screen_elements)
register_tool("save_annotated_screenshot", save_annotated_screenshot)

log.info("✅ Set-of-Mark Tool v1.0 registriert")
log.info("   Tools: scan_ui_elements, get_element_coordinates, find_and_click_element, describe_screen_elements")
