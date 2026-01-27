# tools/visual_click_tool/tool.py (CORRECTED ARCHITECTURE)

import logging
import asyncio
import json
from typing import Union
from PIL import Image
import mss

from jsonrpcserver import method, Success, Error

from tools.universal_tool_caller import register_tool
from tools.shared_context import log, openai_client, segmentation_engine_instance

@method
async def find_element_by_description(description: str) -> Union[Success, Error]:
    """
    Findet das beste UI-Element basierend auf einer Beschreibung und gibt seine Daten (inkl. Mittelpunkt) zurück.
    Diese Funktion führt KEINEN Klick aus, sondern liefert nur die Zieldaten für eine nachfolgende Aktion.
    Beispiel: find_element_by_description("Der 'Anmelden'-Button")
    """
    log.info(f"Suche Element anhand der Beschreibung: '{description}'")

    if not segmentation_engine_instance or not segmentation_engine_instance.initialized:
         return Error(code=-32025, message="Die Segmentation Engine ist nicht für die Elementsuche verfügbar.")
    
    try:
        # Schritt 1: Screenshot direkt hier machen
        with mss.mss() as sct:
            # Verwende den primären Monitor (Index 1 ist normalerweise der Hauptmonitor)
            monitor = sct.monitors[1] if len(sct.monitors) > 1 else sct.monitors[0]
            sct_img = sct.grab(monitor)
            image = Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")

        # Schritt 2: Elemente über die Engine finden
        elements = await asyncio.to_thread(segmentation_engine_instance.get_ui_elements_from_image, image)
        
        if not elements:
            return Success({"status": "no_elements_found", "message": "Keine UI-Elemente auf dem Bildschirm erkannt."})

        # Schritt 3: LLM zur Auswahl des besten Elements befragen
        prompt = f"""
        Ein Agent soll auf ein Element klicken, das dieser Beschreibung entspricht: "{description}"
        Die Analyse hat folgende Elemente gefunden:
        {json.dumps(elements, indent=2)}
        Wähle das eine Element aus, das am besten passt. Antworte NUR mit dem JSON des Elements.
        Wenn nichts passt, antworte mit {{}}.
        """

        response = await asyncio.to_thread(
            openai_client.chat.completions.create,
            model="gpt-4o",
            messages=[{"role": "system", "content": "Wähle das passende JSON-Objekt aus."}, {"role": "user", "content": prompt}],
            temperature=0.0, response_format={"type": "json_object"}
        )

        # Debug: Logge die Antwort
        try:
            # Prüfe die Response-Struktur
            log.info(f"Response object type: {type(response)}")
            log.info(f"Response object: {response}")

            if not hasattr(response, 'choices') or not response.choices:
                log.error("Response hat keine 'choices' oder choices ist leer")
                return Success({"status": "api_error", "message": "API Antwort hat keine 'choices'"})

            choice = response.choices[0]
            log.info(f"Choice object: {choice}")
            log.info(f"Choice type: {type(choice)}")

            if not hasattr(choice, 'message'):
                log.error("Choice hat keine 'message'")
                return Success({"status": "api_error", "message": "API Antwort-Choice hat keine 'message'"})

            message = choice.message
            log.info(f"Message object: {message}")
            log.info(f"Message type: {type(message)}")

            if not hasattr(message, 'content'):
                log.error("Message hat keine 'content'")
                return Success({"status": "api_error", "message": "API Antwort-Message hat keine 'content'"})

            response_content = message.content
            log.info(f"Response content: {response_content[:200]}...")

            if not response_content:
                return Success({"status": "no_response", "message": "Keine Antwort von OpenAI"})

            chosen_element = json.loads(response_content)
        except Exception as e:
            log.error(f"Fehler bei OpenAI Response-Verarbeitung: {e}", exc_info=True)
            return Success({"status": "parse_error", "message": f"Fehler beim Parsen der API-Antwort: {e}"})

        if not chosen_element or "bbox" not in chosen_element:
            return Success({"status": "element_not_found", "message": "Kein passendes Element für die Beschreibung gefunden."})

        # Schritt 4: Zieldaten berechnen und zurückgeben
        bbox = chosen_element["bbox"]
        center_x = bbox[0] + bbox[2] / 2
        center_y = bbox[1] + bbox[3] / 2
        
        chosen_element["center"] = {"x": int(center_x), "y": int(center_y)}

        return Success({"status": "element_found", "element_data": chosen_element})

    except Exception as e:
        log.error(f"Fehler in find_element_by_description: {e}", exc_info=True)
        return Error(code=-32000, message=f"Allgemeiner Fehler im Visual Find Tool: {e}")

# Das alte Tool entfernen wir nicht, aber registrieren das neue, bessere.
register_tool("find_element_by_description", find_element_by_description)
log.info("✅ Visual Find Tool (refactored) registriert.")