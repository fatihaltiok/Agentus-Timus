# tools/skill_manager_tool/tool.py

import os
import logging
import asyncio
from pathlib import Path
import re
from typing import List
import sys
import inspect
import importlib


from tools.tool_registry_v2 import tool, ToolParameter as P, ToolCategory as C

# Import für interne Tool-Aufrufe, um den Developer-Agenten zu beauftragen.
from tools.planner.planner_helpers import call_tool_internal

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


@tool(
    name="register_new_tool_in_server",
    description="Fügt ein neues Tool-Modul sicher zur TOOL_MODULES-Liste im mcp_server.py hinzu.",
    parameters=[
        P("tool_module_path", "string", "Python-Modulpfad des Tools (z.B. tools.my_tool.tool)"),
    ],
    capabilities=["automation", "skills"],
    category=C.AUTOMATION
)
async def register_new_tool_in_server(tool_module_path: str) -> dict:
    """
    Fügt ein neues Tool-Modul sicher zur TOOL_MODULES-Liste im mcp_server.py hinzu.
    """
    try:
        log.info(f"Registriere neues Tool '{tool_module_path}' im MCP-Server...")
        server_file = PROJECT_ROOT / "server" / "mcp_server.py"

        if not server_file.exists():
            raise Exception("mcp_server.py nicht gefunden.")

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
            return {"status": "already_registered", "message": f"Tool {tool_module_path} ist bereits registriert."}

        log.info(f"✅ Tool '{tool_module_path}' erfolgreich zu mcp_server.py hinzugefügt.")
        return {"status": "registered", "message": f"Tool {tool_module_path} wurde zur Server-Konfiguration hinzugefügt. Ein Neustart des Servers ist erforderlich."}

    except Exception as e:
        log.error(f"Fehler bei der Registrierung des neuen Tools: {e}", exc_info=True)
        raise Exception(f"Fehler bei der Tool-Registrierung: {e}")


@tool(
    name="list_skills",
    description="Listet alle aktuell erlernten Fähigkeiten (d.h. alle *_skill.py Dateien) im skills-Ordner auf.",
    parameters=[],
    capabilities=["automation", "skills"],
    category=C.AUTOMATION
)
async def list_skills() -> dict:
    """
    Listet alle aktuell erlernten Fähigkeiten (d.h. alle *_skill.py Dateien) im 'skills'-Ordner auf.
    """
    if not SKILLS_DIR:
        raise Exception("Skill-Verzeichnis konnte nicht initialisiert werden.")
    try:
        skill_list = await asyncio.to_thread(_list_skills_sync)
        return {
            "status": "success",
            "skills_found": len(skill_list),
            "skills": skill_list
        }
    except Exception as e:
        log.error(f"Fehler beim Auflisten der Skills: {e}", exc_info=True)
        raise Exception(f"Fehler beim Auflisten der Skills: {e}")


@tool(
    name="learn_new_skill",
    description="Beauftragt den Developer-Agenten, eine neue Fähigkeit zu erlernen, indem eine neue Python-Datei im skills-Verzeichnis erstellt wird.",
    parameters=[
        P("skill_name", "string", "Name des neuen Skills"),
        P("description", "string", "Beschreibung was der Skill tun soll"),
    ],
    capabilities=["automation", "skills"],
    category=C.AUTOMATION
)
async def learn_new_skill(skill_name: str, description: str) -> dict:
    """
    Beauftragt den Developer-Agenten, eine neue Fähigkeit zu erlernen, indem eine neue Python-Datei
    im 'skills'-Verzeichnis erstellt wird.
    """
    if not SKILLS_DIR:
        raise Exception("Skill-Verzeichnis konnte nicht initialisiert werden.")


    # KORREKTUR 2: Bereinige den `skill_name`, um ungültige Zeichen und Pfad-Manipulation zu verhindern.
    safe_skill_name = re.sub(r'[^a-zA-Z0-9_]', '', skill_name).lower()
    if not safe_skill_name:
        raise Exception("Ungültiger Skill-Name. Muss alphanumerische Zeichen enthalten.")

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
                "instruction": instruction,
                "file_paths": [skill_file_path]
            }
        )

        if isinstance(result, dict) and result.get("error"):
            error_details = result.get("error", {})
            if isinstance(error_details, dict):
                error_message = error_details.get("message", "Unbekannter Fehler beim Aufruf des Developer-Tools.")
            else:
                error_message = str(error_details)
            raise Exception(error_message)

        return {
            "status": "skill_creation_initiated",
            "details": result,
            "message": f"Der Prozess zum Erlernen des Skills '{skill_name}' wurde übergeben. Die neue Datei wird unter '{skill_file_path}' erstellt."
        }

    except Exception as e:
        log.error(f"Kritischer Fehler im 'learn_new_skill'-Tool: {e}", exc_info=True)
        raise Exception(f"Ein unerwarteter interner Fehler ist im Skill-Manager aufgetreten: {e}")


# =================================================================
# TOOL-GENERIERUNG AUS FEHLERN (B1)
# =================================================================

import ast


def _sanitize_skill_name(name: str) -> str:
    """Bereinigt einen Skill-Namen für sichere Dateinamen."""
    # Nur alphanumerische Zeichen und Unterstriche
    safe = re.sub(r'[^a-zA-Z0-9_]', '_', name.lower())
    # Führende/Zurückfolgende Unterstriche entfernen
    safe = safe.strip('_')
    # Max 40 Zeichen
    return safe[:40] if safe else "unnamed_skill"


def _generate_skill_hash(pattern: str) -> str:
    """Generiert einen stabilen Hash für ein Pattern."""
    import hashlib
    return hashlib.md5(pattern.encode()).hexdigest()[:8]


async def _check_duplicate_skill(skill_name: str) -> bool:
    """Prüft ob ein Skill bereits existiert."""
    skills = _list_skills_sync()
    for skill in skills:
        if skill_name in skill.get("skill_name", "").lower():
            return True
    return False


@tool(
    name="create_tool_from_pattern",
    description="Generiert ein neues Tool aus einem erkannten Fehler-Pattern mit Quality-Gate.",
    parameters=[
        P("pattern_description", "string", "Beschreibung des Fehler-Patterns", required=True),
        P("source_task", "string", "Ursprüngliche Task die fehlschlug", required=True),
        P("improvements", "array", "Liste der Verbesserungsvorschläge", required=True),
    ],
    capabilities=["automation", "skills", "self_improvement"],
    category=C.AUTOMATION
)
async def create_tool_from_pattern(
    pattern_description: str,
    source_task: str,
    improvements: list
) -> dict:
    """
    Generiert ein neues Tool aus einem erkannten Fehler-Pattern.

    Quality-Gate:
    1. Duplikat-Check gegen bestehende Skills
    2. Code-Generierung via implement_feature
    3. AST-Validierung vor Registrierung
    4. Registrierung nur bei bestandener Validierung

    Args:
        pattern_description: Beschreibung des Problems/Musters
        source_task: Die ursprüngliche Task die fehlschlug
        improvements: Liste der Verbesserungsvorschläge

    Returns:
        dict mit Status und Skill-Informationen
    """
    if not SKILLS_DIR:
        return {"error": "Skill-Verzeichnis nicht initialisiert"}

    # 1. Skill-Namen generieren
    skill_name = _sanitize_skill_name(pattern_description)
    pattern_hash = _generate_skill_hash(pattern_description)
    skill_name = f"{skill_name}_{pattern_hash}"
    skill_file_path = f"skills/{skill_name}_skill.py"

    # 2. Duplikat-Check
    if await _check_duplicate_skill(skill_name):
        return {
            "skipped": True,
            "reason": f"Skill ähnlich '{skill_name}' existiert bereits",
            "skill_name": skill_name
        }

    log.info(f"Erstelle neues Tool aus Pattern: {skill_name}")

    # 3. Code-Generierung Prompt
    improvements_str = "\n".join(f"  - {imp}" for imp in improvements[:5])
    
    instruction = f"""
    Erstelle ein wiederverwendbares Python-Tool als Skill.

    PROBLEM-BESCHREIBUNG:
    {pattern_description}

    URSÜNGLICHE TASK:
    {source_task}

    VORSCHLÄGE ZUR VERBESSERUNG:
    {improvements_str}

    ANFORDERUNGEN:
    1. Erstelle die Datei: {skill_file_path}
    2. Nutze den @tool Decorator von tools.tool_registry_v2
    3. Definiere klare Parameter mit ToolParameter (P)
    4. Füge eine aussagekräftige Description hinzu
    5. Implementiere die Kern-Logik mit Fehlerbehandlung
    6. Füge einen Docstring hinzu

    BEISPIEL-STRUKTUR:
    ```python
    from tools.tool_registry_v2 import tool, ToolParameter as P, ToolCategory as C

    @tool(
        name="skill_name",
        description="Beschreibung",
        parameters=[
            P("param1", "string", "Beschreibung", required=True),
        ],
        capabilities=["automation"],
        category=C.AUTOMATION
    )
    async def skill_name(param1: str) -> dict:
        '''Docstring'''
        try:
            # Implementierung
            return {{\"status\": \"success\", \"result\": ...}}
        except Exception as e:
            return {{\"error\": str(e)}}
    ```
    """

    try:
        # 4. Code generieren
        result = await call_tool_internal(
            "implement_feature",
            {
                "instruction": instruction,
                "file_paths": [skill_file_path]
            }
        )

        if isinstance(result, dict) and result.get("error"):
            return {
                "error": "Code-Generierung fehlgeschlagen",
                "detail": result.get("error")
            }

        # 5. AST-Validierung
        skill_path = SKILLS_DIR / f"{skill_name}_skill.py"
        if skill_path.exists():
            code = skill_path.read_text(encoding="utf-8")
            try:
                ast.parse(code)
                log.info(f"AST-Validierung bestanden für {skill_name}")
            except SyntaxError as e:
                # Fehlerhaften Code entfernen
                skill_path.unlink()
                return {
                    "error": f"Generierter Code hat Syntax-Fehler: {e}",
                    "line": e.lineno,
                    "skill_name": skill_name
                }
        else:
            return {
                "error": "Skill-Datei wurde nicht erstellt",
                "expected_path": str(skill_path)
            }

        # 6. Tool registrieren
        register_result = await call_tool_internal(
            "register_new_tool_in_server",
            {"tool_module_path": f"skills.{skill_name}_skill"}
        )

        return {
            "success": True,
            "skill_name": skill_name,
            "path": str(skill_path),
            "registered": bool(register_result and not register_result.get("error")),
            "message": f"Neues Tool '{skill_name}' erfolgreich erstellt und validiert"
        }

    except Exception as e:
        log.error(f"Fehler bei Tool-Generierung: {e}", exc_info=True)
        return {
            "error": str(e),
            "skill_name": skill_name
        }
