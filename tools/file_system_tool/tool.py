# tools/file_system_tool/tool.py

# Standard-Bibliotheken
import logging
import asyncio
from pathlib import Path

# V2 Registry
from tools.tool_registry_v2 import tool, ToolParameter as P, ToolCategory as C

# --- ANPASSUNG: Logging wird jetzt zentral konfiguriert ---
log = logging.getLogger(__name__)

# --- Interne, synchrone Hilfsfunktionen (unverändert) ---
# Diese sind bereits gut strukturiert, um in einem Thread zu laufen.

def _get_project_root() -> Path:
    """Gibt den Root-Pfad des Projekts zurück."""
    return Path(__file__).resolve().parent.parent.parent

def _write_to_file_sync(full_path: Path, content: str):
    """Blockierende Schreib-Logik."""
    full_path.parent.mkdir(parents=True, exist_ok=True)
    with open(full_path, 'w', encoding='utf-8') as f:
        f.write(content)

def _read_file_sync(full_path: Path) -> str:
    """Blockierende Lese-Logik."""
    with open(full_path, 'r', encoding='utf-8') as f:
        return f.read()

# --- Asynchrone Tool-Methoden (jetzt mit vereinfachter Pfad-Logik) ---

@tool(
    name="list_directory",
    description="Listet den Inhalt eines Verzeichnisses asynchron auf.",
    parameters=[
        P("path", "string", "Pfad zum Verzeichnis (relativ zum Projekt-Root)", required=True),
    ],
    capabilities=["file", "filesystem"],
    category=C.FILE
)
async def list_directory(path: str) -> dict:
    """
    Listet den Inhalt eines Verzeichnisses asynchron auf.
    """
    try:
        project_root = _get_project_root()
        full_path = (project_root / path).resolve()
        if not str(full_path).startswith(str(project_root)):
             raise Exception("Zugriff außerhalb des Projektverzeichnisses verweigert.")

        if not full_path.is_dir():
            raise FileNotFoundError(f"Das Verzeichnis '{path}' existiert nicht oder ist kein Verzeichnis.")

        # Führe die synchrone Verzeichnisauflistung in einem separaten Thread aus
        directory_contents = await asyncio.to_thread(lambda: [item.name for item in full_path.iterdir()])

        log.info(f"✅ Verzeichnisinhalt von '{full_path}' aufgelistet.")
        return {"status": "success", "path": path, "contents": directory_contents}

    except FileNotFoundError as e:
        log.warning(f"Verzeichnis nicht gefunden: {e}")
        return {"status": "error", "message": str(e)}
    except Exception as e:
        log.error(f"Fehler beim Auflisten des Verzeichnisses '{path}': {e}", exc_info=True)
        return {"status": "error", "message": f"Fehler beim Auflisten des Verzeichnisses: {e}"}

@tool(
    name="write_file",
    description="Schreibt Inhalt asynchron in eine Datei.",
    parameters=[
        P("path", "string", "Dateipfad (relativ zum Projekt-Root)", required=True),
        P("content", "string", "Der zu schreibende Inhalt", required=True),
    ],
    capabilities=["file", "filesystem"],
    category=C.FILE
)
async def write_file(path: str, content: str) -> dict:
    """
    Schreibt Inhalt asynchron in eine Datei.
    """
    try:
        project_root = _get_project_root()
        full_path = (project_root / path).resolve()
        if not str(full_path).startswith(str(project_root)):
             raise Exception("Zugriff außerhalb des Projektverzeichnisses verweigert.")

        await asyncio.to_thread(_write_to_file_sync, full_path, content)

        log.info(f"✅ Datei erfolgreich nach '{full_path}' geschrieben.")
        return {"status": "success", "path": path, "bytes_written": len(content.encode('utf-8'))}

    except Exception as e:
        log.error(f"❌ Fehler beim Schreiben der Datei '{path}': {e}", exc_info=True)
        return {"status": "error", "message": f"Fehler beim Schreiben der Datei: {e}"}

@tool(
    name="read_file",
    description="Liest den Inhalt einer Datei asynchron.",
    parameters=[
        P("path", "string", "Dateipfad (relativ zum Projekt-Root)", required=True),
    ],
    capabilities=["file", "filesystem"],
    category=C.FILE
)
async def read_file(path: str) -> dict:
    """
    Liest den Inhalt einer Datei asynchron.
    """
    try:
        project_root = _get_project_root()
        full_path = (project_root / path).resolve()
        if not str(full_path).startswith(str(project_root)):
             raise Exception("Zugriff außerhalb des Projektverzeichnisses verweigert.")

        if not full_path.is_file():
            raise FileNotFoundError(f"Die Datei '{path}' existiert nicht.")

        content = await asyncio.to_thread(_read_file_sync, full_path)

        log.info(f"✅ Datei erfolgreich von '{full_path}' gelesen.")
        return {"status": "success", "path": path, "content": content}

    except FileNotFoundError as e:
        log.warning(f"Datei nicht gefunden: {e}")
        return {"status": "error", "message": str(e)}
    except Exception as e:
        log.error(f"❌ Fehler beim Lesen der Datei '{path}': {e}", exc_info=True)
        return {"status": "error", "message": f"Allgemeiner Fehler beim Lesen der Datei: {e}"}
