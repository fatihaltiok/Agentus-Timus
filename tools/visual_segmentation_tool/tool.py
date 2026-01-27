# tools/visual_segmentation_tool/tool.py (FINAL, MSS-Version)

import logging
import asyncio
from PIL import Image
import mss  # Wir verwenden jetzt ausschließlich mss
from typing import Union, Optional
from pathlib import Path
from datetime import datetime
import io 
import base64

# Interne Imports
from tools.engines.object_detection_engine import object_detection_engine_instance
from tools.universal_tool_caller import register_tool
from jsonrpcserver import method, Success, Error

import mss
import logging as log

log = logging.getLogger(__name__)

# Definiere ein Verzeichnis zum Speichern der Screenshots
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
RESULTS_DIR = PROJECT_ROOT / "results"
RESULTS_DIR.mkdir(exist_ok=True)


def ensure_engine_ready() -> None:
    """Lazy-Init der Objekterkennungs-Engine."""
    try:
        if hasattr(object_detection_engine_instance, "is_ready"):
            if not object_detection_engine_instance.is_ready():
                log.info("Initialisiere YOLOS-Engine (lazy)...")
                # init oder load_model – je nach Implementierung
                if hasattr(object_detection_engine_instance, "init"):
                    object_detection_engine_instance.init()
                elif hasattr(object_detection_engine_instance, "load_model"):
                    object_detection_engine_instance.load_model()
                else:
                    log.warning("Engine hat weder init() noch load_model(). Setze voraus, dass sie einsatzbereit ist.")
                # Optionales Warmup
                if hasattr(object_detection_engine_instance, "warmup"):
                    try:
                        object_detection_engine_instance.warmup()
                    except Exception as we:
                        log.debug(f"Warmup übersprungen/fehlgeschlagen: {we}")
        else:
            # Falls kein is_ready existiert – versuche init() einmal
            if hasattr(object_detection_engine_instance, "init"):
                object_detection_engine_instance.init()
    except Exception as e:
        raise RuntimeError(f"Engine-Initialisierung fehlgeschlagen: {e}")

def _get_elements_sync(delay_seconds: int, confidence_threshold: float):
    try:
        ensure_engine_ready()

        if delay_seconds > 0:
            log.info(f"Warte {delay_seconds} Sekunden vor dem Screenshot...")
            import time; time.sleep(delay_seconds)

        log.info("Mache Screenshot mit mss...")
        with mss.mss() as sct:
            monitor = sct.monitors[1] if len(sct.monitors) > 1 else sct.monitors[0]
            sct_img = sct.grab(monitor)
            screenshot_pil_image = Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")

        log.info(f"Screenshot erstellt, übergebe an YOLOS-Engine (threshold={confidence_threshold})...")
        elements = object_detection_engine_instance.find_ui_elements(
            screenshot_pil_image, confidence_threshold=confidence_threshold
        )
        return elements
    except Exception as e:
        log.error(f"Fehler bei Screenshot/Engine: {e}", exc_info=True)
        return [{"internal_error": str(e)}]

@method
async def get_clickable_elements(delay_seconds: int = 0, threshold: float = 0.5) -> Union[Success, Error]:
    log.info(f"Starte Objekterkennung (Delay: {delay_seconds}s, Threshold: {threshold})...")
    try:
        result = await asyncio.to_thread(_get_elements_sync, delay_seconds, threshold)
        if result and isinstance(result[0], dict) and "internal_error" in result[0]:
            raise RuntimeError(result[0]["internal_error"])
        log.info(f"✅ {len(result)} Elemente erkannt.")
        return Success({"status": "success", "elements": result})
    except Exception as e:
        return Error(code=-32060, message=f"Fehler bei der visuellen Objekterkennung: {e}")


# --- Werkzeug zum manuellen Speichern von Screenshots ---

# Erst die Funktionen definieren
@method
async def save_screenshot(path: str = None, region: dict = None) -> Union[Success, Error]:
    """
    Speichert einen Screenshot des aktuellen Bildschirms.
    """
    try:
        if not path:
            # Auto-generierter Filename
            from datetime import datetime
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            path = str(RESULTS_DIR / f"screenshot_{timestamp}.png")
            
        with mss.mss() as sct:
            if region:
                screenshot = sct.grab(region)
            else:
                monitor = sct.monitors[1] if len(sct.monitors) > 1 else sct.monitors[0]
                screenshot = sct.grab(monitor)
                
            mss.tools.to_png(screenshot.rgb, screenshot.size, output=path)
            
        return Success({"success": True, "path": path})
    except Exception as e:
        return Error(code=-32000, message=f"Screenshot fehlgeschlagen: {e}")

# Dann die Tools registrieren
register_tool("get_clickable_elements", get_clickable_elements)
register_tool("save_screenshot", save_screenshot)

log.info("✅ Visual Tools (get_clickable_elements, save_screenshot) mit MSS-Screenshot-Engine registriert.")

@method
async def get_screenshot() -> Union[Success, Error]:
    try:
        with mss.mss() as sct:
            monitor_index = 1 if len(sct.monitors) > 1 else 0
            sct_img = sct.grab(sct.monitors[monitor_index])
            img = Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")
        buffered = io.BytesIO()
        img.save(buffered, format="PNG")
        b64_image = base64.b64encode(buffered.getvalue()).decode('utf-8')
        return Success({"base64_image": b64_image, "width": img.width, "height": img.height})
    except Exception as e:
        return Error(code=-32000, message=f"Fehler beim Erstellen des Screenshots: {e}")
    

async def _internal_get_screenshot() -> dict:
    try:
        with mss.mss() as sct:
            monitor_index = 1 if len(sct.monitors) > 1 else 0
            sct_img = sct.grab(sct.monitors[monitor_index])
            img = Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")
        buffered = io.BytesIO()
        img.save(buffered, format="PNG")
        b64_image = base64.b64encode(buffered.getvalue()).decode('utf-8')
        return {"base64_image": b64_image, "width": img.width, "height": img.height}
    except Exception as e:
        return {"error": f"Fehler beim Erstellen des Screenshots: {e}"}

# Der RPC-Wrapper ruft jetzt nur noch die interne Funktion auf.
@method
async def get_screenshot() -> Union[Success, Error]:
    result = await _internal_get_screenshot()
    if "error" in result:
        return Error(code=-32000, message=result["error"])
    return Success(result)

register_tool("get_screenshot", get_screenshot)

# Registriere das neue Tool am Ende der Datei
register_tool("get_screenshot", get_screenshot)

# --- Registrierung ---
register_tool("get_clickable_elements", get_clickable_elements)
register_tool("save_screenshot", save_screenshot)

log.info("✅ Visual Tools (get_clickable_elements, save_screenshot) mit MSS-Screenshot-Engine registriert.")