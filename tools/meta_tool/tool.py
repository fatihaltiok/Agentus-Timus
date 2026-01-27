# tools/meta_tool/tool.py
import os
import logging
from pathlib import Path
from typing import Union
import inspect
import re

# Drittanbieter-Bibliotheken
from jsonrpcserver import method, Success, Error

# Interne Imports
import asyncio
from tools.universal_tool_caller import register_tool, list_registered_tools, get_tool

# Logger
log = logging.getLogger(__name__)

# Projekt-Root
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

# --- Interne, synchrone Hilfsfunktionen ---
def _list_files_sync(target_dir: Path) -> list[str]:
    """Die eigentliche, blockierende Logik zum Auflisten von Dateien."""
    py_files = []
    for root, _, files in os.walk(target_dir):
        for file in files:
            if file.endswith(".py"):
                relative_path = os.path.relpath(os.path.join(root, file), PROJECT_ROOT)
                py_files.append(str(relative_path).replace(os.path.sep, '/')) # Slashes normalisieren
    return py_files

def _read_file_sync(full_path: Path) -> str:
    """Die eigentliche, blockierende Logik zum Lesen einer Datei."""
    return full_path.read_text(encoding="utf-8")

def _write_file_sync(full_path: Path, content: str):
    """Die eigentliche, blockierende Logik zum Schreiben einer Datei."""
    full_path.parent.mkdir(parents=True, exist_ok=True)
    full_path.write_text(content, encoding="utf-8")

# --- Asynchrone Tool-Methoden ---
@method
async def list_agent_files(subfolder: str = "tools") -> Union[Success, Error]:
    """
    Listet alle relevanten .py-Dateien im Agenten-System asynchron auf.
    Erlaubte Ordner sind: tools, agent, server, skills.
    """
    ALLOWED_FOLDERS = ["tools", "agent", "server", "skills"]
    if subfolder not in ALLOWED_FOLDERS:
        return Error(code=-32602, message=f"Ungültiger Ordner. Erlaubt sind: {ALLOWED_FOLDERS}")

    try:
        target_dir = PROJECT_ROOT / subfolder
        py_files = await asyncio.to_thread(_list_files_sync, target_dir)
        return Success({"files": py_files})
    except Exception as e:
        return Error(code=-32050, message=f"Fehler beim Auflisten der Dateien: {e}")

@method
async def list_available_tools() -> Union[Success, Error]:
    """
    Listet alle offiziell registrierten und aufrufbaren Tools (RPC-Methoden) auf,
    die dem Agenten zur Verfügung stehen.
    """
    try:
        tools = list_registered_tools()
        if not tools:
             return Success({"tools": [], "message": "Keine Tools registriert."})
        tool_names = sorted(list(tools.keys()))
        return Success({"tools": tool_names})
    except Exception as e:
        log.error(f"Fehler beim Auflisten der registrierten Tools: {e}", exc_info=True)
        return Error(code=-32055, message=f"Fehler beim Auflisten der Tools: {e}")

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

        content = await asyncio.to_thread(_read_file_sync, full_path)
        return Success({"path": path, "content": content})

    except Exception as e:
        return Error(code=-32050, message=f"Fehler beim Lesen der Datei '{path}': {e}")

@method
async def get_tool_documentation(tool_name: str) -> Union[Success, Error]:
    """
    Gibt die Dokumentation (Docstring) und die erwarteten Parameter für ein
    einzelnes, atomares Tool zurück.
    """
    try:
        tool_func = get_tool(tool_name)
        docstring = inspect.getdoc(tool_func) or "Keine Dokumentation verfügbar."

        sig = inspect.signature(tool_func)
        params = {
            p.name: {
                "type": str(p.annotation) if p.annotation is not inspect.Parameter.empty else "Any",
                "default": p.default if p.default is not inspect.Parameter.empty else "REQUIRED"
            }
            for p in sig.parameters.values()
        }

        return Success({
            "tool_name": tool_name,
            "documentation": docstring,
            "parameters": params
        })
    except ValueError as e:
        return Error(code=-32601, message=str(e))
    except Exception as e:
        log.error(f"Fehler beim Abrufen der Tool-Doku für '{tool_name}': {e}", exc_info=True)
        return Error(code=-32000, message=f"Fehler bei Doku-Abruf: {e}")

# --- Registrierung aller Methoden in diesem Modul ---
register_tool("list_agent_files", list_agent_files)
register_tool("read_file_content", read_file_content)
register_tool("list_available_tools", list_available_tools)
register_tool("get_tool_documentation", get_tool_documentation)


log.info("✅ Meta-Tools (list_agent_files, etc.) registriert.")