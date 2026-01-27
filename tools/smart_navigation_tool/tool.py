# tools/smart_navigation_tool/tool.py - Intelligente Web-Navigation für wetter.de

import logging
import asyncio
import re
from typing import Union, Optional, Dict, List
from PIL import Image
import mss
import pytesseract
from jsonrpcserver import method, Success, Error
from tools.universal_tool_caller import register_tool

# --- Setup ---
log = logging.getLogger("smart_navigation_tool")

# Bekannte UI-Patterns für verschiedene Websites
WEBSITE_PATTERNS = {
    "wetter.de": {
        "search_field_coords": (550, 146),  # Approximative Position des Suchfelds
        "search_field_size": (200, 40),     # Approximative Größe  
        "search_terms": ["Suche nach Ort", "PLZ", "Ort eingeben", "Stadt suchen"],
        "search_button_terms": ["Suchen", "Los", "OK"],
        "fallback_click_area": (400, 120, 700, 180)  # Bereich um das Suchfeld
    },
    "accuweather.com": {
        "search_field_coords": (710, 80),
        "search_terms": ["Search", "Enter Location", "City"],
        "fallback_click_area": (600, 60, 850, 120)
    }
}

@method
async def smart_website_navigation(
    website: str,
    search_query: str,
    action: str = "search_location"
) -> Union[Success, Error]:
    """
    Intelligente Navigation für bekannte Websites mit fallback-Strategien.
    
    Args:
        website: Website-Name (z.B. "wetter.de")
        search_query: Suchbegriff (z.B. "Offenbach")
        action: Art der Aktion ("search_location", "click_element")
    """
    log.info(f"🧭 Smart Navigation für {website}: {action} mit '{search_query}'")
    
    if website not in WEBSITE_PATTERNS:
        return Error(
            code=-32001,
            message=f"Website '{website}' ist nicht in bekannten Patterns. Verfügbar: {list(WEBSITE_PATTERNS.keys())}"
        )
    
    patterns = WEBSITE_PATTERNS[website]
    
    try:
        # Strategie 1: Versuche OCR-basierte Suche
        ocr_result = await _try_ocr_search(patterns["search_terms"])
        if ocr_result["found"]:
            log.info("✅ OCR-Suche erfolgreich")
            return await _execute_search_action(ocr_result["coordinates"], search_query)
        
        # Strategie 2: Versuche bekannte Koordinaten
        log.info("🔄 OCR fehlgeschlagen, versuche bekannte Koordinaten")
        if "search_field_coords" in patterns:
            coords = patterns["search_field_coords"]
            return await _execute_search_action({"x": coords[0], "y": coords[1]}, search_query)
        
        # Strategie 3: Area-based clicking
        log.info("🔄 Versuche Area-basierte Klicks")
        if "fallback_click_area" in patterns:
            area = patterns["fallback_click_area"]
            center_x = (area[0] + area[2]) // 2
            center_y = (area[1] + area[3]) // 2
            return await _execute_search_action({"x": center_x, "y": center_y}, search_query)
        
        return Error(
            code=-32002,
            message=f"Alle Navigationstrategien für {website} fehlgeschlagen"
        )
        
    except Exception as e:
        log.error(f"❌ Fehler bei Smart Navigation: {e}", exc_info=True)
        return Error(
            code=-32000,
            message=f"Unerwarteter Fehler bei Smart Navigation: {str(e)}"
        )

async def _try_ocr_search(search_terms: List[str]) -> Dict:
    """Versucht OCR-basierte Suche nach UI-Elementen."""
    try:
        # Screenshot machen
        def capture_screenshot():
            with mss.mss() as sct:
                monitor = sct.monitors[1] if len(sct.monitors) > 1 else sct.monitors[0]
                sct_img = sct.grab(monitor)
                return Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")
        
        screenshot = await asyncio.to_thread(capture_screenshot)
        
        # OCR durchführen
        def perform_ocr():
            custom_config = r'--oem 3 --psm 6 -l deu+eng'
            ocr_data = pytesseract.image_to_data(
                screenshot, 
                config=custom_config, 
                output_type=pytesseract.Output.DICT
            )
            return ocr_data
        
        ocr_data = await asyncio.to_thread(perform_ocr)
        
        # Suche nach passenden Begriffen
        for search_term in search_terms:
            for i in range(len(ocr_data['text'])):
                detected_text = ocr_data['text'][i].strip().lower()
                if not detected_text:
                    continue
                
                if search_term.lower() in detected_text or detected_text in search_term.lower():
                    x = ocr_data['left'][i]
                    y = ocr_data['top'][i]
                    width = ocr_data['width'][i]
                    height = ocr_data['height'][i]
                    
                    return {
                        "found": True,
                        "coordinates": {
                            "x": x + width // 2,
                            "y": y + height // 2
                        },
                        "text": detected_text,
                        "confidence": ocr_data['conf'][i]
                    }
        
        return {"found": False}
        
    except Exception as e:
        log.warning(f"OCR-Suche fehlgeschlagen: {e}")
        return {"found": False}

async def _execute_search_action(coordinates: Dict, search_query: str) -> Success:
    """Führt die eigentliche Such-Aktion aus - verbesserte Version für Browser."""
    try:
        # Import der Tool-Funktionen
        from tools.universal_tool_caller import tool_caller_instance

        # Schritt 1: Klicke auf das Suchfeld
        click_tool = tool_caller_instance.get_tool("click_at")
        click_result = await click_tool(coordinates["x"], coordinates["y"])

        log.info(f"🖱️ Klick auf ({coordinates['x']}, {coordinates['y']}): {click_result}")

        if click_result.get("status") != "clicked":
            log.warning(f"⚠️ Klick möglicherweise fehlgeschlagen: {click_result}")
            # Fallback: Versuche es nochmal mit etwas Verzögerung
            await asyncio.sleep(0.5)
            click_result = await click_tool(coordinates["x"], coordinates["y"])

        # Kurze Pause für UI-Reaktion
        await asyncio.sleep(1.5)  # Etwas länger warten

        # Schritt 2: Lösche vorhandenen Text durch mehrmaliges Backspace
        type_tool = tool_caller_instance.get_tool("type_text")

        # Mehrere Backspaces senden um vorhandenen Text zu löschen
        for _ in range(10):  # Bis zu 10 Zeichen löschen
            await type_tool("\b", False)  # Backspace ohne Enter
            await asyncio.sleep(0.1)

        await asyncio.sleep(0.5)

        # Schritt 3: Gib den Suchbegriff ein
        await type_tool(search_query, True)  # Mit Enter am Ende

        log.info(f"⌨️ Text eingegeben: '{search_query}' mit Enter")

        # Längere Pause für Suchergebnisse
        await asyncio.sleep(3)

        return Success({
            "status": "search_executed",
            "coordinates": coordinates,
            "search_query": search_query,
            "message": f"Suche nach '{search_query}' erfolgreich ausgeführt"
        })

    except Exception as e:
        log.error(f"❌ Fehler bei Search-Ausführung: {e}", exc_info=True)
        return Success({
            "status": "search_attempted",
            "error": str(e),
            "message": f"Suchversuch für '{search_query}' durchgeführt, aber mit Fehlern"
        })

@method
async def analyze_current_page() -> Union[Success, Error]:
    """Analysiert die aktuelle Webseite und erkennt verfügbare Interaktionen."""
    log.info("🔍 Analysiere aktuelle Webseite...")
    
    try:
        # Screenshot machen
        def capture_and_analyze():
            with mss.mss() as sct:
                monitor = sct.monitors[1] if len(sct.monitors) > 1 else sct.monitors[0]
                sct_img = sct.grab(monitor)
                image = Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")
            
            # OCR für Text-Analyse
            custom_config = r'--oem 3 --psm 6 -l deu+eng'
            ocr_data = pytesseract.image_to_data(
                image, 
                config=custom_config, 
                output_type=pytesseract.Output.DICT
            )
            
            return ocr_data
        
        ocr_data = await asyncio.to_thread(capture_and_analyze)
        
        # Analysiere erkannte Elemente
        interactive_elements = []
        for i in range(len(ocr_data['text'])):
            text = ocr_data['text'][i].strip()
            if not text or len(text) < 2:
                continue
                
            confidence = ocr_data['conf'][i]
            if confidence < 30:  # Filtere unsichere Erkennungen
                continue
            
            x = ocr_data['left'][i]
            y = ocr_data['top'][i]
            width = ocr_data['width'][i]
            height = ocr_data['height'][i]
            
            # Klassifiziere Element-Typ
            element_type = "text"
            if any(keyword in text.lower() for keyword in ["suche", "search", "eingeben", "plz"]):
                element_type = "search_field"
            elif any(keyword in text.lower() for keyword in ["button", "klick", "los", "ok"]):
                element_type = "button"
            elif any(keyword in text.lower() for keyword in ["morgen", "heute", "wetter"]):
                element_type = "weather_info"
            
            interactive_elements.append({
                "text": text,
                "type": element_type,
                "coordinates": {
                    "x": x + width // 2,
                    "y": y + height // 2,
                    "x1": x, "y1": y, "x2": x + width, "y2": y + height
                },
                "confidence": confidence
            })
        
        # Sortiere nach Confidence
        interactive_elements.sort(key=lambda x: x['confidence'], reverse=True)
        
        return Success({
            "status": "page_analyzed",
            "elements": interactive_elements[:10],  # Top 10 Elemente
            "total_elements": len(interactive_elements),
            "message": f"{len(interactive_elements)} interaktive Elemente gefunden"
        })
        
    except Exception as e:
        log.error(f"❌ Fehler bei Seiten-Analyse: {e}", exc_info=True)
        return Error(
            code=-32000,
            message=f"Fehler bei der Seiten-Analyse: {str(e)}"
        )

@method 
async def click_by_area_search(
    search_area: List[int],  # [x1, y1, x2, y2]
    search_terms: List[str]
) -> Union[Success, Error]:
    """Sucht in einem bestimmten Bereich nach Begriffen und klickt darauf."""
    log.info(f"🎯 Area-Search in {search_area} nach {search_terms}")
    
    try:
        # Screenshot des Bereichs machen
        def capture_area():
            with mss.mss() as sct:
                # Konvertiere Area-Koordinaten für mss
                area_coords = {
                    "top": search_area[1],
                    "left": search_area[0], 
                    "width": search_area[2] - search_area[0],
                    "height": search_area[3] - search_area[1]
                }
                sct_img = sct.grab(area_coords)
                return Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")
        
        area_image = await asyncio.to_thread(capture_area)
        
        # OCR auf den Bereich anwenden
        def area_ocr():
            custom_config = r'--oem 3 --psm 6 -l deu+eng'
            return pytesseract.image_to_data(
                area_image, 
                config=custom_config, 
                output_type=pytesseract.Output.DICT
            )
        
        ocr_data = await asyncio.to_thread(area_ocr)
        
        # Suche nach Begriffen im Bereich
        for search_term in search_terms:
            for i in range(len(ocr_data['text'])):
                detected_text = ocr_data['text'][i].strip().lower()
                if not detected_text:
                    continue
                
                if search_term.lower() in detected_text:
                    # Konvertiere relative Koordinaten zu absoluten
                    rel_x = ocr_data['left'][i] + ocr_data['width'][i] // 2
                    rel_y = ocr_data['top'][i] + ocr_data['height'][i] // 2
                    
                    abs_x = search_area[0] + rel_x
                    abs_y = search_area[1] + rel_y
                    
                    # Klicke auf die Position
                    from tools.universal_tool_caller import tool_caller_instance
                    click_tool = tool_caller_instance.get_tool("click_at")
                    click_result = await click_tool(abs_x, abs_y)
                    
                    log.info(f"✅ Area-Click erfolgreich auf '{detected_text}' bei ({abs_x}, {abs_y})")
                    
                    return Success({
                        "status": "area_click_success",
                        "found_text": detected_text,
                        "coordinates": {"x": abs_x, "y": abs_y},
                        "search_term": search_term
                    })
        
        # Fallback: Klicke in die Mitte des Bereichs
        center_x = (search_area[0] + search_area[2]) // 2
        center_y = (search_area[1] + search_area[3]) // 2
        
        from tools.universal_tool_caller import tool_caller_instance
        click_tool = tool_caller_instance.get_tool("click_at")
        await click_tool(center_x, center_y)
        
        return Success({
            "status": "area_click_fallback",
            "coordinates": {"x": center_x, "y": center_y},
            "message": f"Kein spezifischer Text gefunden, klickte in Bereichs-Mitte"
        })
        
    except Exception as e:
        log.error(f"❌ Fehler bei Area-Search: {e}", exc_info=True)
        return Error(
            code=-32000,
            message=f"Fehler bei Area-Search: {str(e)}"
        )

# Tools registrieren
register_tool("smart_website_navigation", smart_website_navigation)
register_tool("analyze_current_page", analyze_current_page)
register_tool("click_by_area_search", click_by_area_search)

log.info("✅ Smart Navigation Tool registriert (smart_website_navigation, analyze_current_page, click_by_area_search)")


