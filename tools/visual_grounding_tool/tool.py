# tools/visual_grounding_tool/tool.py (IMPROVED VERSION v2.0)
"""
Verbessertes Visual Grounding Tool für präzisere Button-Erkennung.

Fixes:
1. Gibt Zentrum-Koordinaten zurück (x, y) statt nur Bounding-Box
2. Fuzzy-Matching für ähnliche Texte
3. DPI-Skalierung wird berücksichtigt
4. Multi-Match: Findet alle Vorkommen, wählt das beste
5. Bessere Vorverarbeitung für verschiedene Hintergründe
6. Konfidenz-Score für Match-Qualität
"""

import logging
import asyncio
import os
from typing import Dict, Optional, List, Tuple
import numpy as np
import cv2

# Drittanbieter-Bibliotheken
import mss
from tools.tool_registry_v2 import tool, ToolParameter as P, ToolCategory as C
from utils.coordinate_converter import sanitize_scale, to_click_point

# Dynamischer Import
try:
    import pytesseract
    from PIL import Image
    from fuzzywuzzy import fuzz
    TESSERACT_AVAILABLE = True
except ImportError as e:
    TESSERACT_AVAILABLE = False
    _import_error = str(e)

log = logging.getLogger("visual_grounding_tool")

# Konfiguration
MIN_CONFIDENCE = 50  # Minimale OCR-Konfidenz
FUZZY_THRESHOLD = 70  # Minimale Fuzzy-Match-Ähnlichkeit
ACTIVE_MONITOR = int(os.getenv("ACTIVE_MONITOR", "1"))  # 1 = Hauptmonitor, 2 = Zweiter, etc.


def _display_scale() -> float:
    """Liest den aktuellen Display-Scale robust ein."""
    return sanitize_scale(os.getenv("DISPLAY_SCALE", "1.0"), default=1.0)


def _get_screenshot_with_offset() -> Tuple[Image.Image, int, int]:
    """
    Macht einen Screenshot und gibt das Bild plus Monitor-Offset zurück.
    Wichtig für Multi-Monitor-Setups.
    """
    with mss.mss() as sct:
        # Wähle den konfigurierten Monitor
        if ACTIVE_MONITOR < len(sct.monitors):
            monitor = sct.monitors[ACTIVE_MONITOR]
        else:
            # Fallback auf Hauptmonitor
            monitor = sct.monitors[1] if len(sct.monitors) > 1 else sct.monitors[0]

        sct_img = sct.grab(monitor)
        img = Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")

        # Offset ist wichtig für korrekte Klick-Koordinaten bei Multi-Monitor
        offset_x = monitor["left"]
        offset_y = monitor["top"]

        log.debug(f"Screenshot von Monitor {ACTIVE_MONITOR}: {monitor['width']}x{monitor['height']} @ ({offset_x}, {offset_y})")

        return img, offset_x, offset_y


def _preprocess_for_ocr(image: Image.Image, method: str = "adaptive") -> np.ndarray:
    """
    Bereitet Bild für OCR vor. Verschiedene Methoden für verschiedene Hintergründe.

    Args:
        image: PIL Image
        method: "adaptive", "otsu", "simple", oder "invert"
    """
    img_np = np.array(image)
    gray = cv2.cvtColor(img_np, cv2.COLOR_RGB2GRAY)

    if method == "adaptive":
        # Gut für ungleichmäßige Beleuchtung/Hintergründe
        processed = cv2.adaptiveThreshold(
            gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2
        )
    elif method == "otsu":
        # Gut für bimodale Histogramme (klarer Kontrast)
        _, processed = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    elif method == "invert":
        # Für hellen Text auf dunklem Hintergrund
        _, processed = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    else:
        # Simple threshold
        _, processed = cv2.threshold(gray, 127, 255, cv2.THRESH_BINARY)

    return processed


def _extract_text_blocks(ocr_data: Dict) -> List[Dict]:
    """
    Extrahiert zusammenhängende Textblöcke aus OCR-Daten.
    Gruppiert Wörter nach Zeilen.
    """
    n_boxes = len(ocr_data['text'])
    lines = {}

    for i in range(n_boxes):
        text = ocr_data['text'][i].strip()
        conf = int(ocr_data['conf'][i]) if ocr_data['conf'][i] != '-1' else 0

        if not text or conf < MIN_CONFIDENCE:
            continue

        # Gruppiere nach Block, Paragraph und Zeile
        line_key = (
            ocr_data['block_num'][i],
            ocr_data['par_num'][i],
            ocr_data['line_num'][i]
        )

        if line_key not in lines:
            lines[line_key] = []

        lines[line_key].append({
            "text": text,
            "left": ocr_data['left'][i],
            "top": ocr_data['top'][i],
            "width": ocr_data['width'][i],
            "height": ocr_data['height'][i],
            "conf": conf
        })

    # Konvertiere zu Liste von Textblöcken
    blocks = []
    for line_key, words in lines.items():
        if not words:
            continue

        # Sortiere Wörter von links nach rechts
        words.sort(key=lambda w: w['left'])

        # Kombiniere zu einem Block
        full_text = " ".join(w['text'] for w in words)
        x1 = min(w['left'] for w in words)
        y1 = min(w['top'] for w in words)
        x2 = max(w['left'] + w['width'] for w in words)
        y2 = max(w['top'] + w['height'] for w in words)
        avg_conf = sum(w['conf'] for w in words) / len(words)

        blocks.append({
            "text": full_text,
            "x1": x1,
            "y1": y1,
            "x2": x2,
            "y2": y2,
            "center_x": (x1 + x2) // 2,
            "center_y": (y1 + y2) // 2,
            "width": x2 - x1,
            "height": y2 - y1,
            "confidence": avg_conf
        })

    return blocks


def _find_best_match(
    search_text: str,
    blocks: List[Dict],
    offset_x: int = 0,
    offset_y: int = 0
) -> Optional[Dict]:
    """
    Findet den besten Match für den Suchtext.
    Verwendet sowohl exaktes als auch Fuzzy-Matching.
    """
    search_lower = search_text.lower().strip()
    search_words = search_lower.split()
    min_search_len = len(search_lower)

    candidates = []
    display_scale = _display_scale()

    for block in blocks:
        block_text = block['text'].lower()

        # FILTER: Block muss mindestens so lang sein wie die Hälfte des Suchtexts
        if len(block_text) < min_search_len // 2:
            continue

        # Methode 1: Exakter Substring-Match
        if search_lower in block_text:
            # Bonus wenn die Längen ähnlich sind
            len_ratio = min_search_len / max(len(block_text), 1)
            score = 90 + int(len_ratio * 10)  # 90-100 je nach Längenübereinstimmung
        # Methode 2: Alle Suchwörter enthalten
        elif all(word in block_text for word in search_words):
            score = 85
        # Methode 3: Fuzzy-Match (nur wenn Längen ähnlich)
        else:
            # Ignoriere wenn Längenunterschied zu groß
            if len(block_text) < min_search_len * 0.5 or len(block_text) > min_search_len * 3:
                continue

            # token_set_ratio ist besser für Wort-Matching
            score = fuzz.token_set_ratio(search_lower, block_text)

        if score >= FUZZY_THRESHOLD:
            click_x, click_y = to_click_point(
                relative_pixel_x=block["center_x"],
                relative_pixel_y=block["center_y"],
                monitor_offset_x=offset_x,
                monitor_offset_y=offset_y,
                dpi_scale=display_scale,
            )
            candidates.append({
                **block,
                "match_score": score,
                "click_x": click_x,
                "click_y": click_y,
            })

    if not candidates:
        return None

    # Sortiere nach Match-Score (höher = besser), dann nach OCR-Konfidenz
    candidates.sort(key=lambda c: (c['match_score'], c['confidence']), reverse=True)

    return candidates[0]


def _find_all_matches(
    search_text: str,
    blocks: List[Dict],
    offset_x: int = 0,
    offset_y: int = 0,
    max_results: int = 5
) -> List[Dict]:
    """
    Findet alle Matches für den Suchtext.
    Nützlich wenn ein Element mehrfach vorkommt.
    """
    search_lower = search_text.lower().strip()
    search_words = search_lower.split()
    min_search_len = len(search_lower)

    matches = []
    display_scale = _display_scale()

    for block in blocks:
        block_text = block['text'].lower()

        # Filter: Zu kurze Texte ignorieren
        if len(block_text) < min_search_len // 2:
            continue

        if search_lower in block_text:
            len_ratio = min_search_len / max(len(block_text), 1)
            score = 90 + int(len_ratio * 10)
        elif all(word in block_text for word in search_words):
            score = 85
        else:
            if len(block_text) < min_search_len * 0.5 or len(block_text) > min_search_len * 3:
                continue
            score = fuzz.token_set_ratio(search_lower, block_text)

        if score >= FUZZY_THRESHOLD:
            click_x, click_y = to_click_point(
                relative_pixel_x=block["center_x"],
                relative_pixel_y=block["center_y"],
                monitor_offset_x=offset_x,
                monitor_offset_y=offset_y,
                dpi_scale=display_scale,
            )
            matches.append({
                "text": block['text'],
                "x": click_x,
                "y": click_y,
                "click_x": click_x,
                "click_y": click_y,
                "width": block['width'],
                "height": block['height'],
                "match_score": score,
                "confidence": block['confidence']
            })

    matches.sort(key=lambda m: (m['match_score'], m['confidence']), reverse=True)
    return matches[:max_results]


def _find_text_sync(text_to_find: str) -> Dict:
    """
    Synchrone Hauptfunktion für die Textsuche.
    Versucht verschiedene Vorverarbeitungsmethoden.
    """
    if not TESSERACT_AVAILABLE:
        raise ImportError(f"Fehlende Module: {_import_error}")

    # Screenshot mit Offset
    img, offset_x, offset_y = _get_screenshot_with_offset()

    # Versuche verschiedene Vorverarbeitungsmethoden
    preprocessing_methods = ["adaptive", "otsu", "simple"]

    best_result = None
    best_score = 0

    for preprocess_method in preprocessing_methods:
        try:
            processed = _preprocess_for_ocr(img, preprocess_method)

            # OCR ausführen
            ocr_data = pytesseract.image_to_data(
                processed,
                output_type=pytesseract.Output.DICT,
                lang='deu+eng',
                config='--psm 11'  # Sparse text - findet auch einzelne Wörter
            )

            # Textblöcke extrahieren
            blocks = _extract_text_blocks(ocr_data)

            if not blocks:
                continue

            # Besten Match finden
            match = _find_best_match(text_to_find, blocks, offset_x, offset_y)

            if match and match['match_score'] > best_score:
                best_result = match
                best_score = match['match_score']

                # Bei perfektem Match sofort zurückgeben
                if best_score >= 95:
                    break

        except Exception as e:
            log.warning(f"Fehler bei Methode {preprocess_method}: {e}")
            continue

    if best_result:
        return {
            "found": True,
            "x": best_result['click_x'],
            "y": best_result['click_y'],
            "text_found": best_result['text'],
            "match_score": best_result['match_score'],
            "confidence": best_result['confidence'],
            "bbox": {
                "x1": best_result['x1'],
                "y1": best_result['y1'],
                "x2": best_result['x2'],
                "y2": best_result['y2']
            }
        }
    else:
        return {"found": False, "error": f"Text '{text_to_find}' nicht gefunden"}


def _find_all_text_sync(text_to_find: str, max_results: int = 5) -> Dict:
    """
    Findet alle Vorkommen eines Textes.
    """
    if not TESSERACT_AVAILABLE:
        raise ImportError(f"Fehlende Module: {_import_error}")

    img, offset_x, offset_y = _get_screenshot_with_offset()
    processed = _preprocess_for_ocr(img, "adaptive")

    ocr_data = pytesseract.image_to_data(
        processed,
        output_type=pytesseract.Output.DICT,
        lang='deu+eng',
        config='--psm 11'
    )

    blocks = _extract_text_blocks(ocr_data)
    matches = _find_all_matches(text_to_find, blocks, offset_x, offset_y, max_results)

    return {
        "count": len(matches),
        "matches": matches
    }


# ==============================================================================
# RPC METHODEN
# ==============================================================================

@tool(
    name="list_monitors",
    description="Listet alle verfügbaren Monitore auf. Nützlich um den richtigen Monitor für ACTIVE_MONITOR zu finden.",
    parameters=[],
    capabilities=["vision", "ocr", "grounding"],
    category=C.VISION
)
async def list_monitors() -> dict:
    """
    Listet alle verfügbaren Monitore auf.
    Nützlich um den richtigen Monitor für ACTIVE_MONITOR zu finden.
    """
    try:
        with mss.mss() as sct:
            monitors = []
            for i, mon in enumerate(sct.monitors):
                if i == 0:
                    monitors.append({
                        "index": 0,
                        "name": "Alle Monitore",
                        "width": mon["width"],
                        "height": mon["height"],
                        "left": mon["left"],
                        "top": mon["top"]
                    })
                else:
                    monitors.append({
                        "index": i,
                        "name": f"Monitor {i}",
                        "width": mon["width"],
                        "height": mon["height"],
                        "left": mon["left"],
                        "top": mon["top"]
                    })

            return {
                "count": len(monitors) - 1,  # Ohne "alle zusammen"
                "active": ACTIVE_MONITOR,
                "monitors": monitors
            }
    except Exception as e:
        raise Exception(str(e))


@tool(
    name="set_active_monitor",
    description="Setzt den aktiven Monitor für Screenshots.",
    parameters=[
        P("monitor_index", "integer", "Monitor-Index: 1 = Hauptmonitor, 2 = Zweiter, etc."),
    ],
    capabilities=["vision", "ocr", "grounding"],
    category=C.VISION
)
async def set_active_monitor(monitor_index: int) -> dict:
    """
    Setzt den aktiven Monitor für Screenshots.

    Args:
        monitor_index: 1 = Hauptmonitor, 2 = Zweiter, etc.
    """
    global ACTIVE_MONITOR

    try:
        with mss.mss() as sct:
            if monitor_index < 0 or monitor_index >= len(sct.monitors):
                raise Exception(
                    f"Monitor {monitor_index} existiert nicht. Verfügbar: 0-{len(sct.monitors)-1}"
                )

            ACTIVE_MONITOR = monitor_index
            mon = sct.monitors[monitor_index]

            log.info(f"Aktiver Monitor: {monitor_index} ({mon['width']}x{mon['height']})")

            return {
                "active_monitor": monitor_index,
                "width": mon["width"],
                "height": mon["height"],
                "offset_x": mon["left"],
                "offset_y": mon["top"]
            }
    except Exception as e:
        raise Exception(str(e))


@tool(
    name="find_text_coordinates",
    description="Findet die Bildschirmkoordinaten (Zentrum) eines Textes via OCR mit Fuzzy-Matching.",
    parameters=[
        P("text_to_find", "string", "Der zu suchende Text (kann mehrere Wörter sein)"),
        P("fuzzy_threshold", "integer", "Minimale Ähnlichkeit für Fuzzy-Match (0-100)", required=False, default=70),
    ],
    capabilities=["vision", "ocr", "grounding"],
    category=C.VISION
)
async def find_text_coordinates(
    text_to_find: str,
    fuzzy_threshold: int = 70
) -> dict:
    """
    Findet die Bildschirmkoordinaten (Zentrum) eines Textes.
    """
    global FUZZY_THRESHOLD
    FUZZY_THRESHOLD = fuzzy_threshold

    log.info(f"Suche nach: '{text_to_find}' (threshold={fuzzy_threshold})")

    if not TESSERACT_AVAILABLE:
        raise Exception(f"OCR nicht verfügbar: {_import_error}")

    try:
        result = await asyncio.to_thread(_find_text_sync, text_to_find)

        if result.get("found"):
            log.info(f"Gefunden: '{result['text_found']}' bei ({result['x']}, {result['y']}) "
                    f"- Match: {result['match_score']}%, OCR-Conf: {result['confidence']:.0f}%")
            return result
        else:
            log.warning(f"Text '{text_to_find}' nicht gefunden")
            raise Exception(result.get("error", "Text nicht gefunden"))

    except ImportError as e:
        raise Exception(str(e))
    except Exception as e:
        if "nicht gefunden" in str(e) or "Text nicht gefunden" in str(e):
            raise
        log.error(f"Fehler bei Textsuche: {e}", exc_info=True)
        raise Exception(f"Fehler: {e}")


@tool(
    name="find_all_text_occurrences",
    description="Findet alle Vorkommen eines Textes auf dem Bildschirm.",
    parameters=[
        P("text_to_find", "string", "Der zu suchende Text"),
        P("max_results", "integer", "Maximale Anzahl Ergebnisse", required=False, default=5),
    ],
    capabilities=["vision", "ocr", "grounding"],
    category=C.VISION
)
async def find_all_text_occurrences(
    text_to_find: str,
    max_results: int = 5
) -> dict:
    """
    Findet alle Vorkommen eines Textes auf dem Bildschirm.
    """
    log.info(f"Suche alle Vorkommen von: '{text_to_find}'")

    if not TESSERACT_AVAILABLE:
        raise Exception(f"OCR nicht verfügbar: {_import_error}")

    try:
        result = await asyncio.to_thread(_find_all_text_sync, text_to_find, max_results)

        log.info(f"{result['count']} Vorkommen gefunden")
        return result

    except Exception as e:
        log.error(f"Fehler: {e}", exc_info=True)
        raise Exception(str(e))


@tool(
    name="find_ui_element_by_text",
    description="Alias für find_text_coordinates (Kompatibilität mit anderen Tools).",
    parameters=[
        P("text_to_find", "string", "Der zu suchende Text"),
    ],
    capabilities=["vision", "ocr", "grounding"],
    category=C.VISION
)
async def find_ui_element_by_text(text_to_find: str, **kwargs) -> dict:
    """
    Alias für find_text_coordinates (Kompatibilität mit anderen Tools).
    """
    return await find_text_coordinates(text_to_find, **kwargs)


@tool(
    name="get_all_screen_text",
    description="Extrahiert allen sichtbaren Text vom Bildschirm. Nützlich zum Debuggen oder für Übersicht.",
    parameters=[],
    capabilities=["vision", "ocr", "grounding"],
    category=C.VISION
)
async def get_all_screen_text() -> dict:
    """
    Extrahiert allen sichtbaren Text vom Bildschirm.
    Nützlich zum Debuggen oder für Übersicht.
    """
    log.info("Extrahiere allen Bildschirmtext...")

    if not TESSERACT_AVAILABLE:
        raise Exception("OCR nicht verfügbar")

    try:
        img, offset_x, offset_y = await asyncio.to_thread(_get_screenshot_with_offset)
        processed = await asyncio.to_thread(_preprocess_for_ocr, img, "adaptive")

        ocr_data = await asyncio.to_thread(
            pytesseract.image_to_data,
            processed,
            output_type=pytesseract.Output.DICT,
            lang='deu+eng'
        )

        blocks = _extract_text_blocks(ocr_data)

        # Filtere kurze Texte und bereite Daten mit Koordinaten auf
        text_elements = []
        for b in blocks:
            text = b.get('text', '').strip()
            if len(text) > 2:  # Nur Texte mit >2 Zeichen
                click_x, click_y = to_click_point(
                    relative_pixel_x=b.get("center_x", 0),
                    relative_pixel_y=b.get("center_y", 0),
                    monitor_offset_x=offset_x,
                    monitor_offset_y=offset_y,
                    dpi_scale=_display_scale(),
                )
                text_elements.append({
                    "text": text,
                    "x": click_x,
                    "y": click_y,
                    "click_x": click_x,
                    "click_y": click_y,
                    "center_x": click_x,
                    "center_y": click_y,
                    "width": b.get('width', 0),
                    "height": b.get('height', 0),
                    "bbox": {
                        "x1": b.get("x1", 0),
                        "y1": b.get("y1", 0),
                        "x2": b.get("x2", 0),
                        "y2": b.get("y2", 0),
                    },
                    "confidence": b.get('confidence', 0.0)
                })

        return {
            "text_count": len(text_elements),
            "texts": text_elements[:50]  # Limit für Response-Größe
        }

    except Exception as e:
        log.error(f"Fehler: {e}", exc_info=True)
        raise Exception(str(e))
