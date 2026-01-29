# tools/annotator_tool/tool.py

# --- STANDARD-BIBLIOTHEKEN ---
import logging
import json
import asyncio
import sys
import os
import io
import base64
from typing import Union
from pathlib import Path

# --- DRITTANBIETER-BIBLIOTHEKEN ---
from openai import OpenAI
from utils.openai_compat import prepare_openai_params
from jsonrpcserver import method, Success, Error
import mss
from PIL import Image

# --- MODULPFAD-KORREKTUR ---
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# --- INTERNE IMPORTS ---
from tools.universal_tool_caller import register_tool

# --- Setup ---
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
logger = logging.getLogger("annotator_tool")

# WICHTIG: Wir nutzen das "Gehirn" (GPT-5.2) für beste Bilderkennung
MODEL_NAME = os.getenv("SMART_MODEL", "gpt-5.2-2025-12-11")

ANNOTATION_PROMPT = """
Deine Aufgabe ist es, einen Screenshot einer Benutzeroberfläche zu analysieren.
Identifiziere alle wichtigen, klickbaren Elemente (Icons, Buttons, Textfelder, Links).

Gib deine Antwort als JSON-Objekt mit einem einzigen Schlüssel "elements" zurück.
Der Wert von "elements" muss ein Array von Objekten sein. Jedes Objekt muss haben:
- "box": [x1, y1, x2, y2] die exakten Pixel-Koordinaten des Elements.
- "label": Ein kurzer, einzigartiger Identifikator (z.B. "btn_login", "input_search").
- "description": Eine kurze Beschreibung (z.B. "Login Button", "Suchfeld").

Ignoriere rein dekorative Elemente. Konzentriere dich auf Interaktionselemente.
"""

def _capture_screen_base64() -> str:
    """
    Erstellt einen Screenshot intern (schnell & sicher) ohne externe Tool-Aufrufe.
    """
    with mss.mss() as sct:
        # Monitor 1 ist meist der Hauptmonitor
        monitor = sct.monitors[1] if len(sct.monitors) > 1 else sct.monitors[0]
        sct_img = sct.grab(monitor)
        img = Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")
        
        # Resize für Performance (Full HD reicht für GPT-5 meist aus und spart Token)
        img.thumbnail((1920, 1080))
        
        buffered = io.BytesIO()
        img.save(buffered, format="PNG", quality=85)
        return base64.b64encode(buffered.getvalue()).decode('utf-8')

@method
async def annotate_screenshot() -> Union[Success, Error]:
    """
    Nimmt einen Screenshot auf und lässt das SMART_MODEL (GPT-5.2) alle UI-Elemente
    darauf mit Labels und Koordinaten annotieren.
    """
    logger.info(f"📸 Starte Annotation mit Modell: {MODEL_NAME}")
    
    try:
        # 1. Screenshot machen (im Thread, um Server nicht zu blockieren)
        b64_image = await asyncio.to_thread(_capture_screen_base64)
        
        # 2. KI-Analyse mit GPT-5.2
        response = await asyncio.to_thread(
            client.chat.completions.create,
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": ANNOTATION_PROMPT},
                {"role": "user", "content": [
                    {"type": "text", "text": "Annotiere die UI-Elemente auf diesem Bild."},
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64_image}"}}
                ]}
            ],
            response_format={"type": "json_object"},
            max_completion_tokens=2000, # GPT-5 Parameter
            temperature=0.0
        )
        
        content = response.choices[0].message.content
        
        # 3. Parsing
        elements_data = json.loads(content or "{}")
        elements = elements_data.get("elements", [])
        
        if not isinstance(elements, list):
            return Error(code=-32002, message="KI-Antwort enthielt kein gültiges 'elements'-Array.")

        logger.info(f"✅ {len(elements)} UI-Elemente erfolgreich annotiert.")
        return Success({
            "status": "success",
            "model_used": MODEL_NAME,
            "element_count": len(elements),
            "elements": elements
        })
        
    except Exception as e:
        logger.error(f"Fehler bei der Annotation: {e}", exc_info=True)
        return Error(code=-32000, message=str(e))

register_tool("annotate_screenshot", annotate_screenshot)
logger.info("✅ Annotator-Tool (GPT-5.2 Powered) registriert.")