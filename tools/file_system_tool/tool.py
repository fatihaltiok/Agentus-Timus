# tools/file_system_tool/tool.py
import os
import logging
from pathlib import Path
from typing import Union
import asyncio  # <--- Wichtig: asyncio importieren

from jsonrpcserver import method, Success, Error

log = logging.getLogger(__name__)
# --- Interne, synchrone Hilfsfunktion ---
def _write_to_file_sync(full_path: Path, content: str):
    """
    Diese Funktion enthält die blockierende Schreib-Logik.
    """
    # Erstelle übergeordnete Verzeichnisse, falls sie nicht existieren
    full_path.parent.mkdir(parents=True, exist_ok=True)
    # Schreibe den Inhalt in die Datei
    with open(full_path, 'w', encoding='utf-8') as f:
        f.write(content)

def _read_file_sync(full_path: Path) -> str:
    """
    Diese Funktion enthält die blockierende Lese-Logik.
    """
    with open(full_path, 'r', encoding='utf-8') as f:
        return f.read()

# --- Asynchrone Tool-Methoden ---
@method
async def write_file(path: str, content: str) -> Union[Success, Error]:
    """
    Schreibt Inhalt asynchron in eine Datei. Erstellt die Datei und Verzeichnisse, wenn sie nicht existieren.
    """
    try:
        project_root = Path(__file__).resolve().parent.parent.parent
        full_path = project_root / path

        # Führe die synchrone Schreib-Operation in einem separaten Thread aus
        await asyncio.to_thread(_write_to_file_sync, full_path, content)
        
        log.info(f"✅ Datei erfolgreich nach '{full_path}' geschrieben.")
        return Success({"status": "success", "path": path, "bytes_written": len(content.encode('utf-8'))})

    except Exception as e:
        log.error(f"❌ Fehler beim Schreiben der Datei '{path}': {e}", exc_info=True)
        return Error(code=-32040, message=f"Fehler beim Schreiben der Datei: {e}")

@method
async def read_file(path: str) -> Union[Success, Error]:
    """
    Liest den Inhalt einer Datei asynchron und gibt ihn als String zurück.
    """
    try:
        project_root = Path(__file__).resolve().parent.parent.parent
        full_path = project_root / path

        if not full_path.exists():
            raise FileNotFoundError(f"Die Datei '{path}' existiert nicht.")

        # Führe die synchrone Lese-Operation in einem separaten Thread aus
        content = await asyncio.to_thread(_read_file_sync, full_path)
        
        log.info(f"✅ Datei erfolgreich von '{full_path}' gelesen.")
        return Success({"status": "success", "path": path, "content": content})

    except FileNotFoundError as fnf_error:
        log.error(f"❌ Datei nicht gefunden: {fnf_error}", exc_info=True)
        return Error(code=-32041, message=str(fnf_error))
        log.error(f"❌ Fehler beim Schreiben der Datei '{path}': {e}", exc_info=True)
        return Error(code=-32040, message=f"Fehler beim Schreiben der Datei: {e}")
