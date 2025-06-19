# skills/visual_navigator_skill.py

import pyautogui
import logging
import base64
import os
import json
import traceback
import asyncio
from openai import OpenAI
from jsonrpcserver import method, Success, Error # Wichtig: Success und Error sind jetzt importiert

# --- Konfiguration ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
log = logging.getLogger(__name__)

# Initialisiere den OpenAI-Client
try:
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
except Exception as e:
    log.error(f"Fehler bei der Initialisierung des OpenAI-Clients: {e}")
    client = None

# Der @method-Decorator registriert diese Funktion beim Server.

@method
async def move_mouse_to_position(x: int, y: int):
    """
    Bewegt die Maus zu den angegebenen Bildschirmkoordinaten (x, y).
    """
    try:
        await asyncio.to_thread(pyautogui.moveTo, x, y)
        log.info(f"Maus erfolgreich zu Position ({x}, {y}) bewegt.")
        return Success({"status": "success", "message": f"Maus zu Position ({x}, {y}) bewegt."})
    except Exception as e:
        log.error(f"Fehler beim Bewegen der Maus: {e}", exc_info=True)
        return Error(code=-32003, message=f"Fehler beim Bewegen der Maus: {str(e)}", data=traceback.format_exc())
# Wir machen die Funktion 'async', damit sie sich korrekt in den Server einfügt.
@method
async def click_element_on_screen(element_description: str):
    """
    Nimmt einen Screenshot auf, sendet ihn mit einer Beschreibung an GPT-4o,
    um Koordinaten zu erhalten, und klickt dann auf diese Stelle.
    """
    if not client:
        log.error("OpenAI-Client ist nicht initialisiert.")
        return Error(code=-32001, message="OpenAI-Client ist nicht initialisiert. API-Key prüfen.")

    try:
        # Führe alle blockierenden Operationen in einem Thread aus, um den Server nicht anzuhalten.
        def sync_operations_part1():
            # 1. Screenshot
            screenshot = pyautogui.screenshot()
            screenshot_path = "temp_screenshot.png"
            screenshot.save(screenshot_path)

            # 2. Base64 Kodierung
            with open(screenshot_path, "rb") as image_file:
                base64_image = base64.b64encode(image_file.read()).decode('utf-8')
            os.remove(screenshot_path)
            return base64_image

        base64_image = await asyncio.to_thread(sync_operations_part1)

        # 3. API Payload (bleibt unverändert)
        messages = [
            {
                "role": "system",
                "content": "Du bist ein präziser visueller Assistent. Deine Aufgabe ist es, die X/Y-Koordinaten eines beschriebenen Elements in einem Bild zu finden. Antworte ausschließlich mit einem JSON-Objekt im Format: {\"x\": <number>, \"y\": <number>}. Wenn du das Element nicht finden kannst, antworte mit {\"error\": \"Element nicht gefunden\"}."
            },
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": f"Finde die Mitte des folgenden Elements in diesem Bild: '{element_description}'"},
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{base64_image}"}}
                ]
            }
        ]
        
        # 4. API Aufruf
        response = await asyncio.to_thread(
            client.chat.completions.create,
            model="gpt-4o", messages=messages, max_tokens=100
        )
        response_content = response.choices[0].message.content

        # 5. Koordinaten parsen
        data = json.loads(response_content)
        if "error" in data:
            log.error(f"LLM konnte Element nicht finden: {data['error']}")
            return Error(code=-32002, message=f"LLM konnte Element nicht finden: {data['error']}")
        
        x, y = int(data['x']), int(data['y'])
        log.info(f"Koordinaten erfolgreich extrahiert: ({x}, {y})")

        # 6. Mausklick (ebenfalls blockierend)
        await asyncio.to_thread(pyautogui.click, x, y)
        log.info(f"Mausklick bei ({x}, {y}) ausgeführt.")

        # KORREKTUR: Gib ein Success-Objekt zurück
        return Success({"status": "success", "message": f"Klick bei ({x}, {y}) ausgeführt."})

    except Exception as e:
        log.error(f"Ein unerwarteter Fehler ist im Visual Navigator aufgetreten: {e}", exc_info=True)
        # KORREKTUR: Gib ein Error-Objekt zurück
        return Error(code=-32000, message=f"Internal error in visual_navigator: {str(e)}", data=traceback.format_exc())
