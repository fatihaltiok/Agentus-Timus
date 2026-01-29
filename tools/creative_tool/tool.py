# tools/creative_tool/tool.py

import logging
import os
import json
import asyncio
import base64
from datetime import datetime
from typing import Union
from pathlib import Path
from dotenv import load_dotenv
from openai import OpenAI
from utils.openai_compat import prepare_openai_params
from jsonrpcserver import method, Success, Error

from tools.universal_tool_caller import register_tool

# --- Setup ---
load_dotenv()
log = logging.getLogger("creative_tool")
try:
    # Annahme: Der Client wird im shared_context initialisiert
    from tools.shared_context import openai_client
    if not openai_client:
        raise RuntimeError("OpenAI-Client nicht im shared_context gefunden.")
except (ImportError, RuntimeError):
    log.warning("shared_context nicht gefunden oder Client fehlt. Erstelle lokalen Fallback-Client.")
    openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# ==============================================================================
# KORRIGIERTE `generate_image` FUNKTION
# ==============================================================================
@method
async def generate_image(prompt: str, size: str = "1024x1024", quality: str = "standard") -> Union[Success, Error]:
    """
    Erstellt ein Bild mit DALL-E 3 oder neuer. Der Parameter 'response_format' wird nicht mehr verwendet.
    """
    image_model = os.getenv("IMAGE_GENERATION_MODEL", "dall-e-3")
    log.info(f"🖼️ Erstelle Bild mit Modell '{image_model}' (Größe: {size}, Qualität: {quality})")
    log.debug(f"   Prompt: '{prompt[:80]}...'")

    try:
        response = await asyncio.to_thread(
            openai_client.images.generate,
            model=image_model,
            prompt=prompt,
            size=size,
            quality=quality, # z.B. "standard" oder "hd"
            n=1
            # DER PARAMETER 'response_format' WURDE HIER ENTFERNT
        )

        image_data = response.data[0]
        
        # Die neue API gibt entweder 'url' oder 'b64_json' zurück. Wir prüfen beides.
        image_url = image_data.url
        b64_json_data = image_data.b64_json
        
        saved_as_filename = None
        message_to_user = ""

        if b64_json_data:
            # Wenn wir Base64 bekommen, speichern wir es als Datei
            log.info("Bild als Base64-Daten erhalten. Speichere als lokale Datei...")
            image_bytes = base64.b64decode(b64_json_data)
            
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            safe_prompt = "".join(c for c in prompt[:30] if c.isalnum() or c in " _-").rstrip()
            filename = f"{timestamp}_image_{safe_prompt}.png"
            
            project_root = Path(__file__).resolve().parent.parent.parent
            results_dir = project_root / 'results'
            results_dir.mkdir(exist_ok=True)
            filepath = results_dir / filename
            
            with open(filepath, "wb") as f:
                f.write(image_bytes)
            
            saved_as_filename = str(filepath.relative_to(project_root))
            message_to_user = f"Bild erfolgreich generiert und lokal unter '{saved_as_filename}' gespeichert."
            log.info(f"✅ Bild erfolgreich gespeichert: {filepath}")

        elif image_url:
            # Wenn wir eine URL bekommen, geben wir sie zurück
            message_to_user = f"Bild erfolgreich generiert. Es ist unter dieser temporären URL verfügbar: {image_url}"
            log.info(f"✅ Bild-URL erfolgreich erhalten: {image_url}")
        
        else:
            raise ValueError("Die API-Antwort enthielt weder eine URL noch b64_json Daten.")

        return Success({
            "status": "success",
            "image_url": image_url,
            "saved_as": saved_as_filename,
            "message": message_to_user
        })

    except Exception as e:
        # Verbesserte Fehlerbehandlung, um die OpenAI-Fehlermeldung zu extrahieren
        error_message = str(e)
        if hasattr(e, 'body') and e.body and 'error' in e.body and 'message' in e.body['error']:
            error_message = f"OpenAI API Fehler: {e.body['error']['message']}"
        log.error(f"❌ {error_message}", exc_info=True)
        return Error(code=-32000, message=error_message)

# ... (deine anderen Methoden wie generate_code, generate_text bleiben unverändert) ...




@method
async def generate_code(prompt: str, language: str, context: str = "") -> Union[Success, Error]:
    """Generiert Code in einer bestimmten Programmiersprache."""
    if not openai_client:
        return Error(code=-32001, message="OpenAI-Client nicht initialisiert.")
        
    log.info(f"💻 Generiere Code in '{language}' für Prompt: '{prompt[:50]}...'")
    system_prompt = f"Du bist ein Experte für {language}. Schreibe sauberen, effizienten Code. Gib NUR den reinen Code zurück, ohne Erklärungen außerhalb von Kommentaren."
    user_message = f"Anforderung: {prompt}"
    if context:
        user_message += f"\n\nBestehender Kontext/Code:\n{context}"
        
    try:
        response = await asyncio.to_thread(
            openai_client.chat.completions.create,
            model="gpt-4o",
            messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_message}],
            temperature=0.1
        )
        code_content = response.choices[0].message.content.strip()
        
        # Entferne Markdown-Code-Blöcke
        if code_content.startswith(f"```{language}"):
            code_content = code_content.split('\n', 1)[1]
            if code_content.endswith("```"):
                code_content = code_content[:-3].strip()

        return Success({"status": "success", "language": language, "code": code_content})
    except Exception as e:
        log.error(f"❌ Fehler bei der Codegenerierung: {e}", exc_info=True)
        return Error(code=-32000, message=f"Fehler bei der Codegenerierung: {str(e)}")

@method
async def generate_text(prompt: str, style: str = "neutral", max_length: int = 500) -> Union[Success, Error]:
    """Generiert einen kreativen Text, eine Idee oder eine Antwort."""
    if not openai_client:
        return Error(code=-32001, message="OpenAI-Client nicht initialisiert.")

    log.info(f"✍️ Generiere Text im Stil '{style}' für Prompt: '{prompt[:50]}...'")
    system_prompt = f"Du bist ein vielseitiger Autor. Erstelle einen Text im Stil '{style}', der genau dem Prompt entspricht."
    try:
        response = await asyncio.to_thread(
            openai_client.chat.completions.create,
            model="gpt-4o",
            messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": prompt}],
            temperature=0.7,
            max_tokens=max_length
        )
        text_content = response.choices[0].message.content.strip()
        return Success({"status": "success", "text": text_content})
    except Exception as e:
        log.error(f"❌ Fehler bei der Texterstellung: {e}", exc_info=True)
        return Error(code=-32000, message=f"Fehler bei der Texterstellung: {str(e)}")


# Registriere die Tools
register_tool("generate_image", generate_image)
# register_tool("generate_code", generate_code)
# register_tool("generate_text", generate_text)
log.info("✅ Creative-Tools (korrigierte generate_image-Version) registriert.")
log.info("✅ Creative-Tools (generate_image, generate_code, etc.) erfolgreich registriert.")