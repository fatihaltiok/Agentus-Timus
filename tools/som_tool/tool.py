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
- Multi-Monitor Support mit Offset-Tracking
- Erweiterte Chat-Interface-Erkennung

Version: 1.1 (Merged)
"""

import logging
import asyncio
import os
import base64
import httpx
import mss
from PIL import Image, ImageDraw, ImageFont
import io
from typing import List, Dict, Optional, Tuple, Union, Any
from dataclasses import dataclass, field
from jsonrpcserver import method, Success, Error

from tools.universal_tool_caller import register_tool
from dotenv import load_dotenv

# --- Setup ---
load_dotenv()
log = logging.getLogger("som_tool")

# Konfiguration
MOONDREAM_BASE_URL = os.getenv("MOONDREAM_API_BASE", "http://localhost:2021/v1")
ACTIVE_MONITOR = int(os.getenv("ACTIVE_MONITOR", "1"))
TIMEOUT = 120.0  # Erhöht auf 120s für GPU-Modelle (besonders bei RTX 3090)

# Erweiterte UI-Element-Typen (Merged aus beiden Versionen)
# Standard-Elemente + Chat-Interface-spezifische Typen
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
    # Chat-Interface spezifisch (aus tool.py fixed)
    "chat input",
    "message box",
    "textbox",
    "textarea",
    "send button",
    "submit button",
]

# HTTP Client (global, wiederverwendbar)
http_client: Optional[httpx.AsyncClient] = None


def get_http_client() -> httpx.AsyncClient:
    """Lazy-initialisierter HTTP Client."""
    global http_client
    if http_client is None or http_client.is_closed:
        http_client = httpx.AsyncClient(timeout=TIMEOUT)
    return http_client


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
    
    Scannt den Bildschirm, erkennt UI-Elemente via Moondream,
    nummeriert sie und berechnet Klick-Koordinaten.
    """
    
    def __init__(self):
        self.elements: List[UIElement] = []
        self.screenshot: Optional[Image.Image] = None
        self.screen_width: int = 1920
        self.screen_height: int = 1200
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
    
    def _image_to_base64(self, img: Image.Image, max_size: Tuple[int, int] = (800, 600), quality: int = 85) -> str:
        """
        Konvertiert PIL Image zu Base64 (optional verkleinert für API).

        Args:
            img: PIL Image
            max_size: Maximale Größe (None = keine Verkleinerung)
            quality: JPEG Qualität (85 = gut, 95 = sehr gut)
        """
        img_copy = img.copy()

        # Nur verkleinern wenn max_size angegeben
        if max_size:
            img_copy.thumbnail(max_size, Image.Resampling.LANCZOS)

        buffer = io.BytesIO()
        img_copy.save(buffer, format="JPEG", quality=quality)
        return base64.b64encode(buffer.getvalue()).decode()
    
    def _smart_crop_regions(self, img: Image.Image) -> List[Tuple[str, Image.Image, Tuple[int, int]]]:
        """
        Erstellt intelligente Crop-Regionen für bessere Erkennung.

        Returns:
            Liste von (region_name, cropped_image, (offset_x, offset_y))
        """
        width, height = img.size
        regions = []

        # Region 1: Bottom half (für Chat-Eingabefelder, Formulare)
        bottom_half = img.crop((0, height // 2, width, height))
        regions.append(("bottom_half", bottom_half, (0, height // 2)))

        # Region 2: Center (für Hauptinhalte)
        center_y_start = height // 4
        center_y_end = 3 * height // 4
        center = img.crop((0, center_y_start, width, center_y_end))
        regions.append(("center", center, (0, center_y_start)))

        # Region 3: Full (als Fallback, verkleinert)
        regions.append(("full_reduced", img, (0, 0)))

        return regions

    async def _detect_elements(self, img: Image.Image, element_type: str, use_zoom: bool = True) -> List[Dict]:
        """
        Ruft Moondream detect für einen Element-Typ auf.

        Args:
            img: Screenshot
            element_type: Element-Typ zum Suchen
            use_zoom: Multi-Resolution + Smart Crop verwenden
        """
        client = get_http_client()
        all_objects = []

        if use_zoom:
            # Multi-Resolution Strategie mit Smart Crop
            regions = self._smart_crop_regions(img)

            for region_name, region_img, (offset_x, offset_y) in regions:
                # Volle Auflösung für crops, verkleinert für full
                if region_name == "full_reduced":
                    b64 = self._image_to_base64(region_img, max_size=(800, 600), quality=85)
                    log.debug(f"  Scanne {region_name} (verkleinert)")
                else:
                    b64 = self._image_to_base64(region_img, max_size=None, quality=90)
                    log.debug(f"  Scanne {region_name} (volle Auflösung)")

                try:
                    response = await client.post(
                        f"{MOONDREAM_BASE_URL}/detect",
                        json={
                            "image_url": f"data:image/jpeg;base64,{b64}",
                            "object": element_type
                        },
                        timeout=TIMEOUT
                    )
                    response.raise_for_status()
                    result = response.json()

                    if "objects" in result and result["objects"]:
                        objects = result["objects"]

                        # Koordinaten zurückrechnen (relativ zum Crop)
                        region_width, region_height = region_img.size
                        for obj in objects:
                            # Von Region-Koordinaten zu Full-Screen
                            obj["x_min"] = (obj["x_min"] * region_width + offset_x) / self.screen_width
                            obj["y_min"] = (obj["y_min"] * region_height + offset_y) / self.screen_height
                            obj["x_max"] = (obj["x_max"] * region_width + offset_x) / self.screen_width
                            obj["y_max"] = (obj["y_max"] * region_height + offset_y) / self.screen_height
                            obj["_source_region"] = region_name

                        all_objects.extend(objects)
                        log.debug(f"    → {len(objects)} in {region_name} gefunden")

                        # Wenn in hochauflösenden Regionen gefunden, stoppe (keine Redundanz)
                        if region_name in ["bottom_half", "center"] and len(objects) > 0:
                            break

                except Exception as e:
                    log.debug(f"    → Fehler in {region_name}: {e}")
                    continue
        else:
            # Legacy: Einzelnes verkleinertes Bild
            b64 = self._image_to_base64(img, max_size=(800, 600))
            try:
                response = await client.post(
                    f"{MOONDREAM_BASE_URL}/detect",
                    json={
                        "image_url": f"data:image/jpeg;base64,{b64}",
                        "object": element_type
                    },
                    timeout=TIMEOUT
                )
                response.raise_for_status()
                result = response.json()

                if "objects" in result:
                    all_objects = result["objects"]
                elif "error" in result:
                    log.warning(f"Moondream Fehler für '{element_type}': {result['error']}")

            except httpx.TimeoutException:
                log.warning(f"Timeout bei Detect für '{element_type}'")
            except httpx.HTTPStatusError as e:
                log.warning(f"HTTP Fehler bei Detect für '{element_type}': {e.response.status_code}")
            except Exception as e:
                log.error(f"Fehler bei Detect für '{element_type}': {e}")

        # Deduplizierung (falls mehrere Regionen gleiches Element fanden)
        all_objects = self._deduplicate_objects(all_objects)

        # Filter: Zu große Boxen entfernen
        filtered = self._filter_oversized_boxes(all_objects)
        log.debug(f"  {element_type}: {len(all_objects)} erkannt, {len(filtered)} nach Filterung")

        return filtered

    def _deduplicate_objects(self, objects: List[Dict], iou_threshold: float = 0.5) -> List[Dict]:
        """
        Entfernt doppelte Erkennungen (gleiche Elemente in verschiedenen Regionen).
        Verwendet IoU (Intersection over Union) für Vergleich.
        """
        if len(objects) <= 1:
            return objects

        unique = []
        for obj in objects:
            is_duplicate = False
            for existing in unique:
                # IoU berechnen
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

        log.debug(f"  Deduplizierung: {len(objects)} → {len(unique)} unique")
        return unique

    def _filter_oversized_boxes(self, objects: List[Dict]) -> List[Dict]:
        """
        Filtert Bounding Boxes die zu groß sind (wahrscheinlich falsch erkannt).

        Filterkriterien:
        - Fläche > 40% vom Bildschirm = zu groß
        - Breite > 80% vom Bildschirm = zu breit
        - Höhe > 70% vom Bildschirm = zu hoch
        - Absolute Größe > 800x600px = zu groß
        """
        filtered = []
        for obj in objects:
            x_min = obj.get("x_min", 0)
            y_min = obj.get("y_min", 0)
            x_max = obj.get("x_max", 0)
            y_max = obj.get("y_max", 0)

            # Berechne relative Größe (0-1)
            width = x_max - x_min
            height = y_max - y_min
            area = width * height

            # Berechne absolute Pixel-Größe
            pixel_width = int(width * self.screen_width)
            pixel_height = int(height * self.screen_height)

            # Filter 1: Zu große Fläche (> 40% vom Bildschirm)
            if area > 0.40:
                log.debug(f"  ✂️ Zu große Fläche: {width:.2f}x{height:.2f} = {area:.1%} vom Bildschirm")
                continue

            # Filter 2: Zu breit (> 80% vom Bildschirm)
            if width > 0.80:
                log.debug(f"  ✂️ Zu breit: {width:.1%} vom Bildschirm")
                continue

            # Filter 3: Zu hoch (> 70% vom Bildschirm)
            if height > 0.70:
                log.debug(f"  ✂️ Zu hoch: {height:.1%} vom Bildschirm")
                continue

            # Filter 4: Absolute Größe zu groß (> 800x600px)
            if pixel_width > 800 or pixel_height > 600:
                log.debug(f"  ✂️ Absolute Größe zu groß: {pixel_width}x{pixel_height}px")
                continue

            # Filter 5: Zu klein
            if width <= 0.01 or height <= 0.01:
                log.debug(f"  ✂️ Zu klein: {width:.2f}x{height:.2f}")
                continue

            # Box ist OK
            log.debug(f"  ✅ OK: {width:.1%}x{height:.1%} ({pixel_width}x{pixel_height}px)")
            filtered.append(obj)

        return filtered
    
    def _normalized_to_pixels(
        self, 
        x_min: float, 
        y_min: float, 
        x_max: float, 
        y_max: float
    ) -> Tuple[int, int, int, int, int, int]:
        """
        Konvertiert normalisierte Koordinaten (0-1) zu absoluten Pixeln.
        
        Returns: 
            (pixel_x, pixel_y, width, height, center_x, center_y)
            center_x/y sind absolute Koordinaten für PyAutoGUI (inkl. Monitor-Offset)
        """
        # Relative Pixel auf dem Monitor
        pixel_x = int(x_min * self.screen_width)
        pixel_y = int(y_min * self.screen_height)
        pixel_x_max = int(x_max * self.screen_width)
        pixel_y_max = int(y_max * self.screen_height)
        
        width = pixel_x_max - pixel_x
        height = pixel_y_max - pixel_y
        
        # Absolute Koordinaten für PyAutoGUI (mit Monitor-Offset)
        center_x = self.monitor_offset_x + pixel_x + width // 2
        center_y = self.monitor_offset_y + pixel_y + height // 2
        
        return pixel_x, pixel_y, width, height, center_x, center_y
    
    async def scan_screen(self, element_types: Optional[List[str]] = None, use_zoom: bool = True) -> List[UIElement]:
        """
        Scannt den Bildschirm nach UI-Elementen.

        Args:
            element_types: Liste von Element-Typen zum Suchen (default: wichtigste Typen)
            use_zoom: Multi-Resolution + Smart Crop verwenden (empfohlen für kleine Elemente)

        Returns:
            Liste von erkannten UIElements
        """
        self.elements = []

        # DEFAULT: Nur die wichtigsten Element-Typen scannen (für Performance)
        default_priority_types = [
            "text field", "input field", "textbox", "chat input",  # Eingabefelder
            "button", "send button",  # Buttons
        ]

        types_to_scan = element_types or default_priority_types
        self._last_scan_types = types_to_scan

        # Screenshot machen
        self.screenshot = self._capture_screenshot()

        zoom_status = "mit Zoom/Crop" if use_zoom else "Standard"
        log.info(f"🔍 Scanne nach {len(types_to_scan)} Element-Typen ({zoom_status}): {', '.join(types_to_scan[:3])}...")

        element_id = 1

        # Für jeden Element-Typ Moondream aufrufen
        for elem_type in types_to_scan:
            detected = await self._detect_elements(self.screenshot, elem_type, use_zoom=use_zoom)

            for obj in detected:
                x_min = obj.get("x_min", 0)
                y_min = obj.get("y_min", 0)
                x_max = obj.get("x_max", 0)
                y_max = obj.get("y_max", 0)

                # Validierung: Überspringe ungültige Bounding Boxes
                if x_max <= x_min or y_max <= y_min:
                    log.debug(f"Überspringe ungültiges Element: {obj}")
                    continue

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

                source = obj.get("_source_region", "unknown")
                log.debug(f"  [{element.id}] {elem_type} @ ({cx}, {cy}) from {source}")

        log.info(f"✅ {len(self.elements)} Elemente erkannt")
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
            try:
                font = ImageFont.truetype("/usr/share/fonts/TTF/DejaVuSans-Bold.ttf", 16)
            except:
                font = ImageFont.load_default()
        
        # Farben für verschiedene Element-Typen
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
            
            # Rechteck zeichnen
            draw.rectangle(
                [elem.pixel_x, elem.pixel_y, 
                 elem.pixel_x + elem.pixel_width, elem.pixel_y + elem.pixel_height],
                outline=color,
                width=2
            )
            
            # Label-Hintergrund
            label = f"[{elem.id}]"
            label_width = len(label) * 8 + 4
            draw.rectangle(
                [elem.pixel_x, elem.pixel_y - 20, elem.pixel_x + label_width, elem.pixel_y],
                fill=color
            )
            
            # Label-Text
            draw.text((elem.pixel_x + 2, elem.pixel_y - 18), label, fill="white", font=font)
        
        return img
    
    def to_dict_list(self) -> List[Dict[str, Any]]:
        """Konvertiert alle Elemente zu einer Liste von Dicts für JSON-RPC."""
        return [
            {
                "id": e.id,
                "type": e.element_type,
                "x": e.center_x,  # Direkt nutzbar für click_at
                "y": e.center_y,
                "click_x": e.center_x,  # Alias für Kompatibilität
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
async def scan_ui_elements(element_types: Optional[List[str]] = None, use_zoom: bool = True) -> Union[Success, Error]:
    """
    Scannt den Bildschirm nach klickbaren UI-Elementen.

    Args:
        element_types: Optional - Liste von Element-Typen
                       (z.B. ["button", "text field", "search bar", "chat input"])
                       Default: Wichtigste Typen
        use_zoom: Multi-Resolution Erkennung (empfohlen für kleine Elemente)
                  Default: True

    Returns:
        Liste von erkannten Elementen mit IDs und Koordinaten.
        Nutze die x/y Koordinaten direkt mit click_at(x, y).

    Beispiel:
        scan_ui_elements(["button", "text field"], use_zoom=True)
        → {"count": 5, "elements": [{"id": 1, "type": "button", "x": 500, "y": 300}, ...]}
    """
    try:
        elements = await som_engine.scan_screen(element_types, use_zoom=use_zoom)

        if not elements:
            return Success({
                "count": 0,
                "elements": [],
                "message": "Keine UI-Elemente erkannt. Versuche anderen Element-Typ oder prüfe ob App im Fokus ist."
            })

        zoom_msg = " (mit Zoom-Erkennung)" if use_zoom else ""
        return Success({
            "count": len(elements),
            "elements": som_engine.to_dict_list(),
            "message": f"{len(elements)} Elemente erkannt{zoom_msg}. Verwende click_at(x, y) mit den angegebenen Koordinaten."
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
        element_type: z.B. "button", "search bar", "text field", "chat input"
    
    Returns:
        Koordinaten des ersten gefundenen Elements
    """
    try:
        elements = await som_engine.scan_screen([element_type])
        
        if not elements:
            return Error(
                code=-32002,
                message=f"Kein '{element_type}' auf dem Bildschirm gefunden. "
                        f"Verfügbare Typen: {', '.join(UI_ELEMENT_TYPES[:5])}..."
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
    
    Scannt nur wichtige Element-Typen für schnellere Antwort.
    
    Returns:
        Textuelle Beschreibung aller Elemente
    """
    try:
        # Wichtigste Element-Typen scannen (schneller)
        priority_types = [
            "button", "text field", "search bar", "chat input", 
            "link", "input field", "send button"
        ]
        elements = await som_engine.scan_screen(priority_types)
        
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
            # Erst scannen falls keine Elemente vorhanden
            await som_engine.scan_screen()
        
        img = som_engine.create_annotated_screenshot()
        
        if not img:
            return Error(code=-32003, message="Kein Screenshot verfügbar")
        
        # Speichern
        save_dir = os.path.expanduser("~/dev/timus/results")
        os.makedirs(save_dir, exist_ok=True)
        save_path = os.path.join(save_dir, filename)
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


@method
async def get_supported_element_types() -> Success:
    """
    Gibt alle unterstützten UI-Element-Typen zurück.
    
    Returns:
        Liste der Element-Typen die gescannt werden können
    """
    return Success({
        "types": UI_ELEMENT_TYPES,
        "count": len(UI_ELEMENT_TYPES),
        "categories": {
            "standard": ["button", "text field", "input field", "search bar", "icon", "link", "menu", "checkbox", "dropdown"],
            "chat_interface": ["chat input", "message box", "textbox", "textarea", "send button", "submit button"]
        }
    })


# ==============================================================================
# REGISTRIERUNG
# ==============================================================================

register_tool("scan_ui_elements", scan_ui_elements)
register_tool("get_element_coordinates", get_element_coordinates)
register_tool("find_and_click_element", find_and_click_element)
register_tool("describe_screen_elements", describe_screen_elements)
register_tool("save_annotated_screenshot", save_annotated_screenshot)
register_tool("get_supported_element_types", get_supported_element_types)

log.info("✅ Set-of-Mark Tool v1.1 (Merged) registriert")
log.info(f"   Unterstützte Typen: {len(UI_ELEMENT_TYPES)}")
log.info("   Tools: scan_ui_elements, get_element_coordinates, find_and_click_element, "
         "describe_screen_elements, save_annotated_screenshot, get_supported_element_types")
