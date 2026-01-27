# tools/moondream_tool/tool.py (FIXED v3.0 - Moondream Station API)
"""
Moondream Tool für visuelle Bildschirm-Analyse.
Nutzt die native Moondream-Station API (/v1/caption, /v1/query, /v1/detect).
"""

import logging
import asyncio
import os
import base64
import httpx
import mss
from PIL import Image
import io
from typing import Union, Optional

from jsonrpcserver import method, Success, Error
from tools.universal_tool_caller import register_tool
from dotenv import load_dotenv

# --- Setup ---
load_dotenv()
logger = logging.getLogger("moondream_tool")

# Konfiguration
MOONDREAM_BASE_URL = os.getenv("MOONDREAM_API_BASE", "http://localhost:2021/v1")
ACTIVE_MONITOR = int(os.getenv("ACTIVE_MONITOR", "1"))
TIMEOUT = 60.0

# HTTP Client
http_client = httpx.AsyncClient(timeout=TIMEOUT)

logger.info(f"✅ Moondream-Tool initialisiert. API: {MOONDREAM_BASE_URL}")


def _capture_screenshot_base64() -> str:
    """Macht einen Screenshot und gibt ihn als Base64 zurück."""
    with mss.mss() as sct:
        # Wähle den richtigen Monitor
        if ACTIVE_MONITOR < len(sct.monitors):
            monitor = sct.monitors[ACTIVE_MONITOR]
        else:
            monitor = sct.monitors[1] if len(sct.monitors) > 1 else sct.monitors[0]
        
        sct_img = sct.grab(monitor)
        img = Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")
        
        # Zu Base64 konvertieren
        buffered = io.BytesIO()
        img.save(buffered, format="PNG")
        b64 = base64.b64encode(buffered.getvalue()).decode('utf-8')
        
        logger.debug(f"Screenshot: {monitor['width']}x{monitor['height']} von Monitor {ACTIVE_MONITOR}")
        return b64


async def _call_moondream_api(endpoint: str, payload: dict) -> dict:
    """Ruft die Moondream-Station API auf."""
    url = f"{MOONDREAM_BASE_URL.rstrip('/')}/{endpoint.lstrip('/')}"
    
    try:
        response = await http_client.post(url, json=payload)
        response.raise_for_status()
        return response.json()
    except httpx.ConnectError:
        raise ConnectionError(f"Moondream-Station nicht erreichbar unter {MOONDREAM_BASE_URL}. Läuft 'moondream-station'?")
    except httpx.HTTPStatusError as e:
        raise Exception(f"Moondream API Fehler: {e.response.status_code} - {e.response.text}")
    except Exception as e:
        raise Exception(f"Moondream Fehler: {e}")


@method
async def describe_screen_with_moondream(
    question: Optional[str] = None
) -> Union[Success, Error]:
    """
    Analysiert den aktuellen Bildschirm mit Moondream.
    
    Args:
        question: Optional - Spezifische Frage zum Bild. 
                  Wenn None, wird eine allgemeine Beschreibung erstellt.
    
    Returns:
        Success mit Beschreibung oder Error
    """
    logger.info(f"🌙 Moondream-Analyse" + (f": '{question[:50]}...'" if question else " (Caption)"))
    
    try:
        # Screenshot machen
        b64_image = await asyncio.to_thread(_capture_screenshot_base64)
        
        # Data-URL Format für Moondream
        image_url = f"data:image/png;base64,{b64_image}"
        
        if question:
            # /v1/query - Frage zum Bild
            result = await _call_moondream_api("query", {
                "image_url": image_url,
                "question": question
            })
            description = result.get("answer", result.get("result", str(result)))
        else:
            # /v1/caption - Allgemeine Beschreibung
            result = await _call_moondream_api("caption", {
                "image_url": image_url
            })
            description = result.get("caption", result.get("result", str(result)))
        
        logger.info(f"✅ Moondream: {description[:100]}...")
        return Success({"description": description})
        
    except ConnectionError as e:
        logger.error(str(e))
        return Error(code=-32001, message=str(e))
    except Exception as e:
        logger.error(f"Moondream-Fehler: {e}", exc_info=True)
        return Error(code=-32000, message=str(e))


@method
async def detect_objects_with_moondream(
    object_type: str = "all"
) -> Union[Success, Error]:
    """
    Erkennt Objekte auf dem Bildschirm mit Moondream.
    
    Args:
        object_type: Was erkannt werden soll (z.B. "buttons", "text", "icons", "all")
    
    Returns:
        Success mit Liste der erkannten Objekte oder Error
    """
    logger.info(f"🌙 Moondream Objekterkennung: '{object_type}'")
    
    try:
        # Screenshot machen
        b64_image = await asyncio.to_thread(_capture_screenshot_base64)
        image_url = f"data:image/png;base64,{b64_image}"
        
        # /v1/detect
        result = await _call_moondream_api("detect", {
            "image_url": image_url,
            "object": object_type
        })
        
        objects = result.get("objects", result.get("detections", []))
        
        logger.info(f"✅ Moondream: {len(objects) if isinstance(objects, list) else '?'} Objekte erkannt")
        return Success({
            "object_type": object_type,
            "objects": objects,
            "raw_result": result
        })
        
    except ConnectionError as e:
        logger.error(str(e))
        return Error(code=-32001, message=str(e))
    except Exception as e:
        logger.error(f"Moondream-Fehler: {e}", exc_info=True)
        return Error(code=-32000, message=str(e))


@method
async def find_element_with_moondream(
    element_description: str
) -> Union[Success, Error]:
    """
    Sucht ein UI-Element auf dem Bildschirm mit Moondream.
    
    Args:
        element_description: Beschreibung des Elements (z.B. "Firefox Icon", "Suchfeld", "Schließen-Button")
    
    Returns:
        Success mit Position/Beschreibung oder Error
    """
    logger.info(f"🌙 Moondream Element-Suche: '{element_description}'")
    
    try:
        # Screenshot machen
        b64_image = await asyncio.to_thread(_capture_screenshot_base64)
        image_url = f"data:image/png;base64,{b64_image}"
        
        # Frage nach dem Element
        question = f"Wo ist '{element_description}' auf diesem Screenshot? Beschreibe die Position (oben/mitte/unten, links/mitte/rechts) und wie es aussieht. Wenn nicht gefunden, sage 'nicht gefunden'."
        
        result = await _call_moondream_api("query", {
            "image_url": image_url,
            "question": question
        })
        
        answer = result.get("answer", result.get("result", str(result)))
        
        # Prüfe ob gefunden
        not_found_indicators = ["nicht gefunden", "not found", "kann nicht", "don't see", "no ", "nicht sichtbar"]
        found = not any(indicator in answer.lower() for indicator in not_found_indicators)
        
        logger.info(f"✅ Moondream: {'Gefunden' if found else 'Nicht gefunden'} - {answer[:100]}...")
        
        return Success({
            "element": element_description,
            "found": found,
            "description": answer
        })
        
    except ConnectionError as e:
        logger.error(str(e))
        return Error(code=-32001, message=str(e))
    except Exception as e:
        logger.error(f"Moondream-Fehler: {e}", exc_info=True)
        return Error(code=-32000, message=str(e))


@method
async def ask_about_screen(
    question: str
) -> Union[Success, Error]:
    """
    Stellt eine beliebige Frage über den aktuellen Bildschirm.
    
    Args:
        question: Die Frage (z.B. "Welche Tabs sind geöffnet?", "Was zeigt das Fenster?")
    
    Returns:
        Success mit Antwort oder Error
    """
    return await describe_screen_with_moondream(question)


# Registrierung
register_tool("describe_screen_with_moondream", describe_screen_with_moondream)
register_tool("detect_objects_with_moondream", detect_objects_with_moondream)
register_tool("find_element_with_moondream", find_element_with_moondream)
register_tool("ask_about_screen", ask_about_screen)

logger.info("✅ Moondream-Tool v3.0 (Moondream Station API) registriert.")
logger.info("   Tools: describe_screen_with_moondream, detect_objects_with_moondream, find_element_with_moondream, ask_about_screen")
