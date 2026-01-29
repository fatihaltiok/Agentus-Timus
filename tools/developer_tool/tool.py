# tools/developer_tool/tool.py

import logging
import os
import asyncio
from pathlib import Path
from typing import Union, List, Optional

# Drittanbieter
from jsonrpcserver import method, Success, Error
from openai import AsyncOpenAI
from utils.openai_compat import prepare_openai_params

# Interne
from tools.universal_tool_caller import register_tool

# --- Setup & Konfiguration ---
log = logging.getLogger("developer_tool")
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

# 1. API Key laden
INCEPTION_KEY = os.getenv("INCEPTION_API_KEY")

# 2. URL aus Anleitung (Fallback auf .env, sonst Default)
INCEPTION_URL = os.getenv("INCEPTION_API_URL", "https://api.inceptionlabs.ai/v1")

# 3. Modell aus Anleitung (Fallback auf .env, sonst 'mercury')
# Wir bevorzugen hier 'mercury', da es das spezialisierte Coding-Modell ist.
MODEL_NAME = os.getenv("INCEPTION_MODEL", "mercury")

try:
    if INCEPTION_KEY:
        # Wir nutzen AsyncOpenAI, da die Signatur kompatibel ist, aber besser für den Server
        client = AsyncOpenAI(
            api_key=INCEPTION_KEY, 
            base_url=INCEPTION_URL
        )
        log.info(f"✅ Developer-Tool verbunden mit {INCEPTION_URL}")
        log.info(f"✅ Aktives Modell: {MODEL_NAME}")
    else:
        client = None
        log.warning("⚠️ Developer-Tool: INCEPTION_API_KEY fehlt in .env!")
except Exception as e:
    log.error(f"Init-Fehler bei Inception Labs Client: {e}")
    client = None

# --- Hilfsfunktionen (Intern) ---
def _read_file_safe(path_str: str) -> str:
    try:
        path = (PROJECT_ROOT / path_str).resolve()
        if path.exists() and path.is_file():
            return path.read_text(encoding="utf-8")
    except Exception as e:
        log.warning(f"Konnte Datei {path_str} nicht lesen: {e}")
    return ""

def _write_file_safe(path_str: str, content: str):
    path = (PROJECT_ROOT / path_str).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")

@method
async def implement_feature(
    instruction: str,
    file_paths: Union[str, List[str]],
    context_files: Optional[List[str]] = None
) -> Union[Success, Error]:
    """
    Schreibt Code mit der Inception Labs 'Mercury' Engine.
    """
    if not client:
        return Error(code=-32031, message="Inception API Key fehlt.")

    if isinstance(file_paths, str):
        file_paths = [file_paths]

    log.info(f"🚀 Starte Coding mit '{MODEL_NAME}' für: {file_paths}")

    # 1. Inhalte laden
    files_content = ""
    for fp in file_paths:
        content = _read_file_safe(fp)
        files_content += f"\n--- TARGET FILE: {fp} ---\n{content}\n"

    context_content = ""
    if context_files:
        for cfp in context_files:
            content = _read_file_safe(cfp)
            context_content += f"\n--- CONTEXT FILE (READ-ONLY): {cfp} ---\n{content}\n"

    # 2. Prompt Engineering für Mercury
    system_msg = """
    You are an expert software engineer utilizing the Mercury engine.
    Your task is to implement the requested features into the provided files.
    
    OUTPUT RULES:
    1. Output the FULL, compilable code for each target file.
    2. Separate multiple files using the delimiter: `### FILE: path/to/file.py`
    3. Do NOT wrap the output in markdown code blocks (```python) unless necessary for the code itself.
    """

    user_msg = f"""
    INSTRUCTION: {instruction}

    TARGET FILES CONTENT:
    {files_content}

    CONTEXT FILES:
    {context_content}

    Please generate the new code for: {', '.join(file_paths)}
    """

    try:
        # 3. API Aufruf an Inception Labs
        kwargs = {
            "model": MODEL_NAME, # Hier wird 'mercury' verwendet
            "messages": [
                {"role": "system", "content": system_msg},
                {"role": "user", "content": user_msg}
            ],
            "temperature": 0.1,
            "max_tokens": 4000 # Mercury erlaubt oft große Context Windows
        }

        response = await client.chat.completions.create(**kwargs)
        
        raw_output = response.choices[0].message.content.strip()
        
        # 4. Parsing & Schreiben
        segments = raw_output.split("### FILE:")
        modified = []
        
        # Fallback: Wenn Mercury keine Header gesetzt hat und es nur eine Datei ist
        if len(file_paths) == 1 and len(segments) < 2:
            clean_code = raw_output.replace("```python", "").replace("```", "").strip()
            _write_file_safe(file_paths[0], clean_code)
            modified.append(file_paths[0])
        else:
            for seg in segments:
                if not seg.strip(): continue
                lines = seg.strip().splitlines()
                if not lines: continue
                
                path = lines[0].strip()
                code = "\n".join(lines[1:])
                # Bereinigung von Markdown-Artefakten
                code = code.replace("```python", "").replace("```", "").strip()
                
                if path and code:
                    _write_file_safe(path, code)
                    modified.append(path)

        log.info(f"✅ Mercury hat Code für {len(modified)} Dateien generiert.")
        
        return Success({
            "status": "success",
            "modified_files": modified,
            "engine": MODEL_NAME,
            "message": "Code erfolgreich implementiert."
        })

    except Exception as e:
        log.error(f"Inception/Mercury Error: {e}", exc_info=True)
        return Error(code=-32032, message=f"Fehler bei Code-Generierung: {e}")

register_tool("implement_feature", implement_feature)