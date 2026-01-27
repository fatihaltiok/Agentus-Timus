# tools/skill_manager_tool/tool.py

import os
import logging
import asyncio
from pathlib import Path
import re
from typing import Union, List
import sys
import inspect
import importlib 


from jsonrpcserver import method, Success, Error

# Import für interne Tool-Aufrufe, um den Developer-Agenten zu beauftragen.
from tools.planner.planner_helpers import call_tool_internal

from tools.universal_tool_caller import register_tool

# Konsistentes Logging-Setup
log = logging.getLogger(__name__)

# Setup der globalen Pfade
try:
    PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
    SKILLS_DIR = PROJECT_ROOT / "skills"
    # Stelle sicher, dass das Verzeichnis existiert
    SKILLS_DIR.mkdir(exist_ok=True)
    log.info(f"Skill-Verzeichnis initialisiert unter: {SKILLS_DIR}")
except Exception as e:
    log.error(f"FATAL: Konnte das Skill-Verzeichnis nicht initialisieren: {e}")
    SKILLS_DIR = None

# --- Interne, synchrone Hilfsfunktionen (für asyncio.to_thread) ---

def _list_skills_sync() -> List[dict]:
    """
    Blockierende Logik zum Auflisten existierender Skills, inklusive ihrer
    Funktionen, Docstrings und Parameter.
    """
    if not SKILLS_DIR:
        raise RuntimeError("Skill-Verzeichnis ist nicht initialisiert.")
    
    skills_details = []
    
    # Füge den skills-Ordner temporär zum Pfad hinzu, um Importe zu ermöglichen
    sys_path_modified = False
    if str(SKILLS_DIR.parent) not in sys.path:
        sys.path.insert(0, str(SKILLS_DIR.parent))
        sys_path_modified = True

    for skill_file in SKILLS_DIR.glob("*_skill.py"):
        skill_name = skill_file.stem.replace("_skill", "")
        try:
            # Dynamisches Laden des Moduls, um es zu inspizieren
            module_name = f"skills.{skill_file.stem}"
            spec = importlib.util.spec_from_file_location(module_name, skill_file)
            if spec and spec.loader:
                skill_module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(skill_module)
                
                skill_functions = []
                for func_name, func_obj in inspect.getmembers(skill_module, inspect.isfunction):
                    if not func_name.startswith("_"):
                        sig = inspect.signature(func_obj)
                        params = {p.name: str(p.annotation) for p in sig.parameters.values()}
                        skill_functions.append({
                            "name": func_name,
                            "docstring": inspect.getdoc(func_obj) or "Keine Beschreibung verfügbar.",
                            "parameters": params
                        })
                
                if skill_functions:
                    skills_details.append({
                        "skill_name": skill_name,
                        "file_path": str(skill_file.relative_to(PROJECT_ROOT)),
                        "functions": skill_functions
                    })
        except Exception as e:
            log.error(f"Konnte Skill '{skill_name}' nicht inspizieren: {e}")
    
    # Bereinige den sys.path, wenn wir ihn modifiziert haben
    if sys_path_modified:
        sys.path.pop(0)
        
    return skills_details

# --- Asynchrone Tool-Methoden (verfügbar über JSON-RPC) ---


# ... (Ihre bestehenden Funktionen wie list_skills, learn_new_skill) ...

@method
async def register_new_tool_in_server(tool_module_path: str) -> Union[Success, Error]:
    """
    Fügt ein neues Tool-Modul sicher zur TOOL_MODULES-Liste im mcp_server.py hinzu.
    """
    try:
        log.info(f"Registriere neues Tool '{tool_module_path}' im MCP-Server...")
        server_file = PROJECT_ROOT / "server" / "mcp_server.py"

        if not server_file.exists():
            return Error(code=-32085, message="mcp_server.py nicht gefunden.")

        def read_and_write_sync():
            content = server_file.read_text(encoding="utf-8")
            
            # KORREKTUR 1: Robusterer Weg, die Liste zu finden und zu modifizieren.
            # Wir suchen den Anker `TOOL_MODULES = [` und die schließende `]`.
            list_pattern = re.compile(r"(TOOL_MODULES\s*=\s*\[\n)(.*?)(^\s*\])", re.DOTALL | re.MULTILINE)
            match = list_pattern.search(content)

            if not match:
                raise RuntimeError("TOOL_MODULES-Liste in mcp_server.py konnte nicht gefunden oder geparst werden.")

            opening_tag, list_content, closing_tag = match.groups()

            # Prüfen, ob das Modul schon da ist.
            if f'"{tool_module_path}"' in list_content:
                log.info(f"Tool '{tool_module_path}' ist bereits registriert. Keine Änderung nötig.")
                return {"status": "already_registered"}

            # Füge das neue Modul hinzu. Stellt sicher, dass am Ende ein Komma steht.
            if list_content.strip().endswith(','):
                new_list_content = list_content + f'    "{tool_module_path}",\n'
            else:
                new_list_content = list_content.rstrip() + ',\n' + f'    "{tool_module_path}",\n'
            
            # Baue den neuen Gesamtinhalt zusammen
            new_content = content[:match.start()] + opening_tag + new_list_content + closing_tag + content[match.end():]
            
            server_file.write_text(new_content, encoding="utf-8")
            return {"status": "registered"}

        result = await asyncio.to_thread(read_and_write_sync)
        
        if result["status"] == "already_registered":
            return Success({"status": "already_registered", "message": f"Tool {tool_module_path} ist bereits registriert."})
            
        log.info(f"✅ Tool '{tool_module_path}' erfolgreich zu mcp_server.py hinzugefügt.")
        return Success({"status": "registered", "message": f"Tool {tool_module_path} wurde zur Server-Konfiguration hinzugefügt. Ein Neustart des Servers ist erforderlich."})

    except Exception as e:
        log.error(f"Fehler bei der Registrierung des neuen Tools: {e}", exc_info=True)
        return Error(code=-32000, message=f"Fehler bei der Tool-Registrierung: {e}")



# ... (Ihre bestehenden Funktionen wie list_skills, learn_new_skill) ...

@method
async def register_new_tool_in_server(tool_module_path: str) -> Union[Success, Error]:
    """
    Fügt ein neues Tool-Modul sicher zur TOOL_MODULES-Liste im mcp_server.py hinzu.
    """
    try:
        log.info(f"Registriere neues Tool '{tool_module_path}' im MCP-Server...")
        server_file = PROJECT_ROOT / "server" / "mcp_server.py"

        if not server_file.exists():
            return Error(code=-32085, message="mcp_server.py nicht gefunden.")

        def read_and_write_sync():
            content = server_file.read_text(encoding="utf-8")
            
            # KORREKTUR 1: Robusterer Weg, die Liste zu finden und zu modifizieren.
            # Wir suchen den Anker `TOOL_MODULES = [` und die schließende `]`.
            list_pattern = re.compile(r"(TOOL_MODULES\s*=\s*\[\n)(.*?)(^\s*\])", re.DOTALL | re.MULTILINE)
            match = list_pattern.search(content)

            if not match:
                raise RuntimeError("TOOL_MODULES-Liste in mcp_server.py konnte nicht gefunden oder geparst werden.")

            opening_tag, list_content, closing_tag = match.groups()

            # Prüfen, ob das Modul schon da ist.
            if f'"{tool_module_path}"' in list_content:
                log.info(f"Tool '{tool_module_path}' ist bereits registriert. Keine Änderung nötig.")
                return {"status": "already_registered"}

            # Füge das neue Modul hinzu. Stellt sicher, dass am Ende ein Komma steht.
            if list_content.strip().endswith(','):
                new_list_content = list_content + f'    "{tool_module_path}",\n'
            else:
                new_list_content = list_content.rstrip() + ',\n' + f'    "{tool_module_path}",\n'
            
            # Baue den neuen Gesamtinhalt zusammen
            new_content = content[:match.start()] + opening_tag + new_list_content + closing_tag + content[match.end():]
            
            server_file.write_text(new_content, encoding="utf-8")
            return {"status": "registered"}

        result = await asyncio.to_thread(read_and_write_sync)
        
        if result["status"] == "already_registered":
            return Success({"status": "already_registered", "message": f"Tool {tool_module_path} ist bereits registriert."})
            
        log.info(f"✅ Tool '{tool_module_path}' erfolgreich zu mcp_server.py hinzugefügt.")
        return Success({"status": "registered", "message": f"Tool {tool_module_path} wurde zur Server-Konfiguration hinzugefügt. Ein Neustart des Servers ist erforderlich."})

    except Exception as e:
        log.error(f"Fehler bei der Registrierung des neuen Tools: {e}", exc_info=True)
        return Error(code=-32000, message=f"Fehler bei der Tool-Registrierung: {e}")



@method
async def list_skills() -> Union[Success, Error]:
    """
    Listet alle aktuell erlernten Fähigkeiten (d.h. alle *_skill.py Dateien) im 'skills'-Ordner auf.
    """
    if not SKILLS_DIR:
        return Error(code=-32081, message="Skill-Verzeichnis konnte nicht initialisiert werden.")
    try:
        skill_list = await asyncio.to_thread(_list_skills_sync)
        return Success({
            "status": "success",
            "skills_found": len(skill_list),
            "skills": skill_list
        })
    except Exception as e:
        log.error(f"Fehler beim Auflisten der Skills: {e}", exc_info=True)
        return Error(code=-32080, message=f"Fehler beim Auflisten der Skills: {e}")


@method
async def learn_new_skill(skill_name: str, description: str) -> Union[Success, Error]:
    """
    Beauftragt den Developer-Agenten, eine neue Fähigkeit zu erlernen, indem eine neue Python-Datei
    im 'skills'-Verzeichnis erstellt wird.
    """
    if not SKILLS_DIR:
        return Error(code=-32081, message="Skill-Verzeichnis konnte nicht initialisiert werden.")

    
    # KORREKTUR 2: Bereinige den `skill_name`, um ungültige Zeichen und Pfad-Manipulation zu verhindern.
    safe_skill_name = re.sub(r'[^a-zA-Z0-9_]', '', skill_name).lower()
    if not safe_skill_name:
        return Error(code=-32602, message="Ungültiger Skill-Name. Muss alphanumerische Zeichen enthalten.")

    skill_file_path = f"skills/{safe_skill_name}_skill.py"
    log.info(f"Versuche, neuen Skill '{skill_name}' durch Erstellen von '{skill_file_path}' zu erlernen...")

    # Der Instruction-Prompt bleibt gleich
    instruction = f"""
    Erstelle eine neue, wiederverwendbare Fähigkeit als Python-Modul in der Datei '{skill_file_path}'.
    Die Datei soll eine oder mehrere saubere, gut dokumentierte Python-Funktionen enthalten, die die folgende Aufgabe erfüllen: '{description}'.

    Anforderungen:
    1. Modularität: Code muss in importierbaren Funktionen liegen.
    2. Keine Seiteneffekte: Nutze `if __name__ == "__main__":` für Tests.
    3. Abhängigkeiten: Standardbibliotheken oder bereits im Projekt genutzte sind ok.
    4. Dokumentation: Klare Docstrings für jede Funktion.
    5. Fehlerbehandlung: Grundlegende `try...except`-Blöcke.
    """


    try:
        result = await call_tool_internal(
            "implement_feature",
            {
                "file_paths": [skill_file_path],
                "instruction": instruction,
                "strategy": "inception_then_aider"
            }
        )

        if isinstance(result, dict) and result.get("error"):
            error_details = result.get("error", {})
            error_message = error_details.get("message", "Unbekannter Fehler beim Aufruf des Developer-Tools.")
            return Error(code=-32082, message=error_message, data=error_details)

        return Success({
            "status": "skill_creation_initiated",
            "details": result,
            "message": f"Der Prozess zum Erlernen des Skills '{skill_name}' wurde übergeben. Die neue Datei wird unter '{skill_file_path}' erstellt."
        })
                
    except Exception as e:
        log.error(f"Kritischer Fehler im 'learn_new_skill'-Tool: {e}", exc_info=True)
        return Error(code=-32000, message=f"Ein unerwarteter interner Fehler ist im Skill-Manager aufgetreten: {e}")
    


# --- Registrierung der Tools ---
register_tool("list_skills", list_skills)
register_tool("learn_new_skill", learn_new_skill)
register_tool("register_new_tool_in_server", register_new_tool_in_server)


log.info("✅ Skill Manager Tools registriert.")


# Vergessen Sie nicht, das neue Tool zu registrieren
register_tool("register_new_tool_in_server", register_new_tool_in_server)
   