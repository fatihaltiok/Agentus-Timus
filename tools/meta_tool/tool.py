# tools/meta_tool/tool.py
import os
import logging
from pathlib import Path
import inspect

# Drittanbieter-Bibliotheken
from tools.tool_registry_v2 import tool, ToolParameter as P, ToolCategory as C, registry_v2

# Interne Imports
import asyncio

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
@tool(
    name="list_agent_files",
    description="Listet alle relevanten .py-Dateien im Agenten-System asynchron auf. Erlaubte Ordner: tools, agent, server, skills.",
    parameters=[
        P("subfolder", "string", "Ordner zum Auflisten (tools, agent, server, skills)", required=False, default="tools"),
    ],
    capabilities=["system", "meta"],
    category=C.SYSTEM
)
async def list_agent_files(subfolder: str = "tools") -> dict:
    """
    Listet alle relevanten .py-Dateien im Agenten-System asynchron auf.
    Erlaubte Ordner sind: tools, agent, server, skills.
    """
    ALLOWED_FOLDERS = ["tools", "agent", "server", "skills"]
    if subfolder not in ALLOWED_FOLDERS:
        raise Exception(f"Ungültiger Ordner. Erlaubt sind: {ALLOWED_FOLDERS}")

    try:
        target_dir = PROJECT_ROOT / subfolder
        py_files = await asyncio.to_thread(_list_files_sync, target_dir)
        return {"files": py_files}
    except Exception as e:
        raise Exception(f"Fehler beim Auflisten der Dateien: {e}")

@tool(
    name="list_available_tools",
    description="Listet alle offiziell registrierten und aufrufbaren Tools (RPC-Methoden) auf.",
    parameters=[],
    capabilities=["system", "meta"],
    category=C.SYSTEM
)
async def list_available_tools() -> dict:
    """
    Listet alle offiziell registrierten und aufrufbaren Tools (RPC-Methoden) auf,
    die dem Agenten zur Verfügung stehen.
    """
    try:
        tools = registry_v2.list_all_tools()
        if not tools:
             return {"tools": [], "message": "Keine Tools registriert."}
        tool_names = sorted(tools.keys())
        return {"tools": tool_names}
    except Exception as e:
        log.error(f"Fehler beim Auflisten der registrierten Tools: {e}", exc_info=True)
        raise Exception(f"Fehler beim Auflisten der Tools: {e}")

@tool(
    name="read_file_content",
    description="Liest den Inhalt einer Datei innerhalb des Projekts asynchron.",
    parameters=[
        P("path", "string", "Relativer Pfad zur Datei innerhalb des Projekts"),
    ],
    capabilities=["system", "meta"],
    category=C.SYSTEM
)
async def read_file_content(path: str) -> dict:
    """
    Liest den Inhalt einer Datei innerhalb des Projekts asynchron.
    """
    try:
        full_path = (PROJECT_ROOT / path).resolve()

        if not str(full_path).startswith(str(PROJECT_ROOT.resolve())):
            raise Exception("Zugriff außerhalb des Projektverzeichnisses verweigert.")
        if not full_path.is_file():
            raise Exception(f"Datei nicht gefunden unter: {path}")

        content = await asyncio.to_thread(_read_file_sync, full_path)
        return {"path": path, "content": content}

    except Exception as e:
        raise Exception(f"Fehler beim Lesen der Datei '{path}': {e}")

@tool(
    name="get_tool_documentation",
    description="Gibt die Dokumentation (Docstring) und die erwarteten Parameter für ein einzelnes, atomares Tool zurück.",
    parameters=[
        P("tool_name", "string", "Name des Tools"),
    ],
    capabilities=["system", "meta"],
    category=C.SYSTEM
)
async def get_tool_documentation(tool_name: str) -> dict:
    """
    Gibt die Dokumentation (Docstring) und die erwarteten Parameter für ein
    einzelnes, atomares Tool zurück.
    """
    try:
        tool_meta = registry_v2.get_tool(tool_name)
        tool_func = tool_meta.function
        docstring = inspect.getdoc(tool_func) or tool_meta.description or "Keine Dokumentation verfügbar."

        sig = inspect.signature(tool_func)
        params = {
            p.name: {
                "type": str(p.annotation) if p.annotation is not inspect.Parameter.empty else "Any",
                "default": p.default if p.default is not inspect.Parameter.empty else "REQUIRED"
            }
            for p in sig.parameters.values()
        }

        return {
            "tool_name": tool_name,
            "documentation": docstring,
            "parameters": params
        }
    except ValueError as e:
        raise Exception(str(e))
    except Exception as e:
        log.error(f"Fehler beim Abrufen der Tool-Doku für '{tool_name}': {e}", exc_info=True)
        raise Exception(f"Fehler bei Doku-Abruf: {e}")
