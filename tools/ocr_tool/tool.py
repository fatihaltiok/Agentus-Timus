# tools/ocr_tool/tool.py

# ERSETZE den kompletten Inhalt dieser Datei.

import logging
import asyncio
from typing import Dict, Any, List
import mss
from PIL import Image

try:
    from tools.shared_context import ocr_engine_instance
    OCR_ENGINE_AVAILABLE = ocr_engine_instance.is_initialized()
except (ImportError, AttributeError):
    OCR_ENGINE_AVAILABLE = False

from tools.universal_tool_caller import register_tool

log = logging.getLogger("OCREngineTool")

async def read_text_from_screen(with_boxes: bool = False) -> Dict[str, Any]:
    """
    Erfasst den Bildschirm und extrahiert Text mit der zentralen, GPU-beschleunigten OCREngine.
    
    :param with_boxes: Wenn True, gibt auch die Bounding-Boxen für jeden Textblock zurück.
    :return: Ein Dictionary mit dem extrahierten Text.
    """
    if not OCR_ENGINE_AVAILABLE:
        msg = "Zentrale OCREngine ist nicht verfügbar. Prüfe Server-Startlogs."
        log.error(msg)
        return {"error": msg}

    log.info("Erfasse Screenshot für zentrale OCREngine...")
    try:
        def capture_screenshot_sync():
            with mss.mss() as sct:
                sct_img = sct.grab(sct.monitors[1])
                return Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")

        screenshot_image = await asyncio.to_thread(capture_screenshot_sync)
        
        log.info("Verarbeite Bild mit OCREngine...")
        # Die `process` Methode der Engine aufrufen
        result = await ocr_engine_instance.process(screenshot_image, with_boxes=with_boxes)
        
        log.info(f"OCREngine hat {len(result.get('extracted_text', []))} Textblöcke gefunden.")
        return result

    except Exception as e:
        log.error(f"Fehler in read_text_from_screen: {e}", exc_info=True)
        return {"error": str(e)}

# Registrierung am Ende der Datei
register_tool("read_text_from_screen", read_text_from_screen)
log.info("✅ Zentrales OCR Tool (read_text_from_screen via OCREngine) registriert.")