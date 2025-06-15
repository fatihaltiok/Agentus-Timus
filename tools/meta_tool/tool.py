# tools/meta_tool/tool.py
import os
import logging
from pathlib import Path
from typing import Union
import asyncio # <--- Wichtig: asyncio importieren

from jsonrpcserver import method, Success, Error

log = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

# --- Interne, synchrone Hilfsfunktionen ---
def _list_files_sync(target_dir: Path) -> list[str]:
    """Die eigentliche, blockierende Logik zum Auflisten von Dateien."""
    py_files = []
    for root, _, files in os.walk(target_dir):
        for file in files:
            if file.endswith(".py"):
                relative_path = os.path.relpath(os.path.join(root, file), PROJECT_ROOT)
                py_files.append(str(relative_path))
    return py_files

def _read_file_sync(full_path: Path) -> str:
    """Die eigentliche, blockierende Logik zum Lesen einer Datei."""
    return full_path.read_text(encoding="utf-8")

# --- Asynchrone Tool-Methoden ---
@method
async def list_agent_files(subfolder: str = "tools") -> Union[Success, Error]:
    """
    Listet alle relevanten .py-Dateien im Agenten-System asynchron auf.
    """
    ALLOWED_FOLDERS = ["tools", "agent", "server"]
    if subfolder not in ALLOWED_FOLDERS:
        return Error(code=-32602, message=f"Ungültiger Ordner. Erlaubt sind: {ALLOWED_FOLDERS}")
    
    try:
        target_dir = PROJECT_ROOT / subfolder
        # Führe die synchrone Logik in einem Thread aus
        py_files = await asyncio.to_thread(_list_files_sync, target_dir)
        return Success({"files": py_files})
    except Exception as e:
        return Error(code=-32050, message=f"Fehler beim Auflisten der Dateien: {e}")

@method
async def read_file_content(path: str) -> Union[Success, Error]:
    """
    Liest den Inhalt einer Datei innerhalb des Projekts asynchron.
    """
    try:
        full_path = (PROJECT_ROOT / path).resolve()
        
        if not str(full_path).startswith(str(PROJECT_ROOT.resolve())):
            return Error(code=-32052, message="Zugriff außerhalb des Projektverzeichnisses verweigert.")
        if not full_path.is_file():
            return Error(code=-32051, message=f"Datei nicht gefunden unter: {path}")

        # Führe die synchrone Logik in einem Thread aus
        content = await asyncio.to_thread(_read_file_sync, full_path)
        return Success({"path": path, "content": content})

    except Exception as e:
        return Error(code=-32050, message=f"Fehler beim Lesen der Datei '{path}': {e}")
