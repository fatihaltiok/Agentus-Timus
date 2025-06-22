import logging
import asyncio
import os
from typing import Union, Optional
from jsonrpcserver import method, Success, Error
from tools.universal_tool_caller import register_tool

# Logger für dieses Modul
log = logging.getLogger(__name__)

# --- Synchrone Hilfsfunktionen ---
def _create_directory_sync(directory: str):
    """Erstellt ein Verzeichnis, falls es nicht existiert."""
    if not os.path.exists(directory):
        os.makedirs(directory)

def _create_empty_file_sync(file_path: str):
    """Erstellt eine leere Datei."""
    with open(file_path, 'w') as file:
        pass

# --- Asynchrone RPC-Methoden ---

@method
async def create_directory(directory: str) -> Union[Success, Error]:
    """
    Erstellt ein Verzeichnis asynchron.
    """
    log.info(f"Erstelle Verzeichnis: {directory}")
    try:
        await asyncio.to_thread(_create_directory_sync, directory)
        return Success({"status": "directory_created", "directory": directory})
    except Exception as e:
        log.error(f"Fehler beim Erstellen des Verzeichnisses: {e}", exc_info=True)
        return Error(code=-32032, message=f"Verzeichniserstellung fehlgeschlagen: {e}")

@method
async def create_empty_file(directory: str, file_name: str) -> Union[Success, Error]:
    """
    Erstellt eine leere Datei im angegebenen Verzeichnis.
    """
    file_path = os.path.join(directory, file_name)
    log.info(f"Erstelle leere Datei: {file_path}")
    try:
        await asyncio.to_thread(_create_empty_file_sync, file_path)
        return Success({"status": "file_created", "file_path": file_path})
    except Exception as e:
        log.error(f"Fehler beim Erstellen der Datei: {e}", exc_info=True)
        return Error(code=-32030, message=f"Dateierstellung fehlgeschlagen: {e}")

# --- Registrierung der neuen Tools ---
register_tool("create_directory", create_directory)
register_tool("create_empty_file", create_empty_file)

log.info("✅ Directory & File Creation Tools (create_directory, create_empty_file) registriert.")
