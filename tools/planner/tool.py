# tools/planner/tool.py

import json
import logging
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml
from tools.tool_registry_v2 import tool, ToolParameter as P, ToolCategory as C

from tools.planner.planner_helpers import call_tool_internal

log = logging.getLogger(__name__)

# --- Finale, korrigierte Hilfsfunktion zur Variablensubstitution ---
def _substitute_variables(data: Any, context: Dict[str, Any]) -> Any:
    """
    Durchläuft rekursiv ein Datenobjekt und ersetzt Platzhalter im Format {{...}}.
    Unterstützt den Zugriff auf verschachtelte Schlüssel und einfache Berechnungen sicher mit eval().
    """
    if isinstance(data, dict):
        return {k: _substitute_variables(v, context) for k, v in data.items()}
    elif isinstance(data, list):
        return [_substitute_variables(item, context) for item in data]
    elif isinstance(data, str):
        # KORREKTUR: Verwende re.sub mit einer Lambda-Funktion, um alle Platzhalter
        # in einem Durchgang sicher auszuwerten und zu ersetzen.
        def replace_match(match):
            expression = match.group(1).strip()
            try:
                # DotDict-Klasse zur Vereinfachung des Zugriffs im eval (z.B. coords.x1)
                class DotDict(dict):
                    __getattr__ = dict.get
                    def __init__(self, d=None):
                        super().__init__()
                        if d:
                            for k, v in d.items():
                                self[k] = DotDict(v) if isinstance(v, dict) else v
                eval_context = {k: DotDict(v) if isinstance(v, dict) else v for k, v in context.items()}

                # Führe die Auswertung im sicheren Kontext durch
                result = eval(expression, {"__builtins__": None}, eval_context)

                # Wenn der gesamte String der Platzhalter war, gib den Typ-korrekten Wert zurück
                if data.strip() == match.group(0):
                    return result

                # Ansonsten gib den String-Wert zurück
                return str(result)
            except Exception as e:
                log.warning(f"Konnte Platzhalter '{{{{{expression}}}}}' nicht auswerten: {e}")
                # Wenn die Auswertung fehlschlägt, gib den Original-Platzhalter zurück
                return match.group(0)

        # Überprüfen, ob der String nur aus einem einzigen Platzhalter besteht,
        # um den Original-Datentyp zu erhalten (wichtig für Zahlen).
        single_match = re.fullmatch(r"\{\{\s*(.*?)\s*\}\}", data.strip())
        if single_match:
            return replace_match(single_match)
        else:
            # Für Strings mit mehreren Platzhaltern oder Text dazwischen
            return re.sub(r"\{\{(.*?)\}\}", replace_match, data)
    else:
        return data

# --- Zentrale Ausführungslogik ---
async def _execute_plan_logic(steps: List[Dict[str, Any]], initial_context: Dict[str, Any] = None) -> dict:
    """
    Die zentrale Logik zur Ausführung eines Plans mit Kontext-Management.
    """
    execution_context = initial_context or {}
    observations: List[Dict[str, Any]] = []

    for idx, step in enumerate(steps):
        if not isinstance(step, dict):
            raise Exception(f"Schritt {idx+1} hat ein ungültiges Format.")

        try:
            current_params = _substitute_variables(step.get("params", {}), execution_context)
            method_name = step.get("method")
            if not method_name:
                raise Exception(f"Keine Methode in Schritt {idx+1} angegeben.")
            log.info(f"DEBUG: execution_context = {execution_context}")
            log.info(f"DEBUG: raw params = {step.get('params', {})}")
            log.info(f"PLANNER Step {idx+1}: Führe '{method_name}' mit Parametern aus: {current_params}")
            result = await call_tool_internal(method_name, current_params)
            observations.append({method_name: result})

            # --- expected_state Check ---
            step_ok = True
            expected = step.get("expected_state")
            if expected and isinstance(result, dict):
                result_str = json.dumps(result, ensure_ascii=False, default=str).lower()
                for term in expected.get("must_contain", []):
                    if term.lower() not in result_str:
                        log.warning(f"PLANNER Step {idx+1}: Erwartet '{term}' nicht im Ergebnis gefunden")
                        step_ok = False
                        break
                if step_ok:
                    for term in expected.get("must_not_contain", []):
                        if term.lower() in result_str:
                            log.warning(f"PLANNER Step {idx+1}: Unerwarteter Term '{term}' im Ergebnis")
                            step_ok = False
                            break

            # Originaler Fehler-Check
            if isinstance(result, dict) and result.get("error"):
                step_ok = False

            # --- Fallback-Logik ---
            if not step_ok:
                fallbacks = step.get("fallbacks", [])
                recovered = False
                for fb in fallbacks:
                    fb_action = fb.get("action", "abort")
                    if fb_action == "retry":
                        log.info(f"PLANNER Step {idx+1}: Retry...")
                        result = await call_tool_internal(method_name, current_params)
                        if not (isinstance(result, dict) and result.get("error")):
                            observations[-1] = {method_name: result}
                            recovered = True
                            break
                    elif fb_action == "alternative":
                        alt_method = fb.get("method")
                        alt_params = _substitute_variables(fb.get("params", {}), execution_context)
                        log.info(f"PLANNER Step {idx+1}: Alternative '{alt_method}'...")
                        result = await call_tool_internal(alt_method, alt_params)
                        if not (isinstance(result, dict) and result.get("error")):
                            observations[-1] = {alt_method: result}
                            recovered = True
                            break
                    elif fb_action == "skip":
                        log.info(f"PLANNER Step {idx+1}: Überspringe...")
                        recovered = True
                        break
                    elif fb_action == "abort":
                        break

                if not recovered:
                    error_detail = result.get("error", "expected_state nicht erfüllt") if isinstance(result, dict) else "Step fehlgeschlagen"
                    error_message = f"Plan bei Schritt {idx+1} ('{method_name}') fehlgeschlagen."
                    log.error(f"{error_message}: {error_detail}")
                    raise Exception(f"{error_message}: {error_detail}")

            result_key = step.get("register_result_as")
            if result_key:
                log.info(f"PLANNER: Speichere Ergebnis von '{method_name}' als Variable '{result_key}'.")
                execution_context[result_key] = result

        except Exception as e:
            log.error(f"Kritischer Fehler während der Planausführung bei Schritt {idx+1}: {e}", exc_info=True)
            raise Exception(f"Kritischer Fehler bei Planausführung: {e}")

    final_result = observations[-1] if observations else {}
    return {"plan_status": "done", "final_result": final_result, "all_observations": observations}


# --- Öffentliche RPC-Methoden ---

@tool(
    name="run_plan",
    description="Führt eine Liste von Aktionen nacheinander aus.",
    parameters=[
        P("steps", "array", "Liste von Schritten mit method und params"),
        P("initial_params", "object", "Optionale initiale Kontextparameter", required=False),
    ],
    capabilities=["automation", "planning"],
    category=C.AUTOMATION
)
async def run_plan(steps: List[Dict[str, Any]], initial_params: Optional[Dict[str, Any]] = None) -> dict:
    """Führt eine Liste von Aktionen nacheinander aus."""
    if not isinstance(steps, list):
        raise Exception("Der Plan muss eine Liste von Schritten sein.")
    return await _execute_plan_logic(steps, initial_context=initial_params)

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
SKILLS_PATH = PROJECT_ROOT / "agent" / "skills.yml"
SKILL_MD_DIR = PROJECT_ROOT / "skills"


def _load_yaml_skills() -> Dict[str, Any]:
    if not SKILLS_PATH.exists():
        return {}
    with open(SKILLS_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _load_skill_md_registry():
    try:
        from utils.skill_types import SkillRegistry
    except Exception as exc:
        log.warning(f"SKILL.md Registry konnte nicht importiert werden: {exc}")
        return None

    registry = SkillRegistry()
    try:
        registry.load_all_from_directory(SKILL_MD_DIR)
    except Exception as exc:
        log.warning(f"SKILL.md Registry konnte nicht geladen werden: {exc}")
        return None
    return registry


def _pick_entry_script(script_names: List[str]) -> Optional[str]:
    if not script_names:
        return None

    preferred = ("main.py", "run.py", "entrypoint.py")
    names_set = set(script_names)
    for candidate in preferred:
        if candidate in names_set:
            return candidate

    sorted_names = sorted(script_names)
    for suffix in (".py", ".sh", ".bash"):
        for name in sorted_names:
            if name.endswith(suffix):
                return name
    return sorted_names[0]


def _build_skill_catalog() -> Dict[str, Dict[str, Any]]:
    """
    Vereinheitlicht Skills aus:
    - agent/skills.yml (workflow skills)
    - skills/*/SKILL.md (instructional/script skills)
    """
    catalog: Dict[str, Dict[str, Any]] = {}

    skills_yml = _load_yaml_skills()
    for name, skill_data in skills_yml.items():
        if not isinstance(skill_data, dict):
            continue
        meta = skill_data.get("meta", {}) if isinstance(skill_data.get("meta"), dict) else {}
        params_meta = meta.get("params", {}) if isinstance(meta.get("params"), dict) else {}
        steps = skill_data.get("steps", [])
        catalog[name] = {
            "name": name,
            "source": "skills_yml",
            "execution_mode": "workflow",
            "description": meta.get("description", "Keine Beschreibung."),
            "required_params": sorted(params_meta.keys()),
            "steps_count": len(steps) if isinstance(steps, list) else 0,
            "skill_data": skill_data,
        }

    registry = _load_skill_md_registry()
    if registry:
        for name in registry.list_all():
            skill = registry.get(name)
            if not skill:
                continue

            scripts = skill.get_scripts()
            references = skill.get_references()
            assets = skill.get_assets()
            entry_script = _pick_entry_script(list(scripts.keys()))
            execution_mode = "script" if entry_script else "instructional"

            if name in catalog:
                # YAML hat Vorrang bei run_skill, aber SKILL.md Metadaten ergänzen.
                catalog[name]["also_available_as"] = "skill_md"
                catalog[name]["skill_md_execution_mode"] = execution_mode
                catalog[name]["skill_md_scripts"] = sorted(scripts.keys())
                catalog[name]["skill_md_references"] = sorted(references.keys())
                continue

            catalog[name] = {
                "name": name,
                "source": "skill_md",
                "execution_mode": execution_mode,
                "description": skill.description or "Keine Beschreibung.",
                "required_params": [],
                "steps_count": 0,
                "entry_script": entry_script,
                "available_scripts": sorted(scripts.keys()),
                "available_references": sorted(references.keys()),
                "available_assets": sorted(assets.keys()),
            }

    return catalog


def _resolve_skill_name(raw_name: str, catalog: Dict[str, Dict[str, Any]]) -> Optional[str]:
    if not raw_name:
        return None
    if raw_name in catalog:
        return raw_name

    normalized = raw_name.strip().lower().replace("_", "-")
    if normalized in catalog:
        return normalized
    return None


def _load_skill_md_by_name(skill_name: str):
    registry = _load_skill_md_registry()
    if not registry:
        return None
    skill = registry.get(skill_name)
    if skill:
        return skill
    return registry.get(skill_name.replace("_", "-"))

@tool(
    name="run_skill",
    description="Lädt einen Skill aus skills.yml und führt dessen steps-Liste aus.",
    parameters=[
        P("name", "string", "Name des Skills"),
        P("params", "object", "Optionale Parameter für den Skill", required=False),
    ],
    capabilities=["automation", "planning"],
    category=C.AUTOMATION
)
async def run_skill(name: str, params: Optional[Dict[str, Any]] = None) -> dict:
    """Führt einen Skill aus (skills.yml Workflow oder SKILL.md Skill)."""
    catalog = _build_skill_catalog()
    resolved_name = _resolve_skill_name((name or "").strip(), catalog)
    if not resolved_name:
        raise Exception(f"Skill '{name}' nicht gefunden.")

    skill_meta = catalog[resolved_name]
    source = skill_meta.get("source")
    log.info(
        f"SKILL: Führe Skill '{resolved_name}' aus "
        f"(source={source}, mode={skill_meta.get('execution_mode')})"
    )

    # Workflow-Skill aus agent/skills.yml
    if source == "skills_yml":
        skill_data = skill_meta.get("skill_data", {})
        skill_plan = skill_data.get("steps")
        if not isinstance(skill_plan, list):
            raise Exception(f"Skill '{resolved_name}' hat keine gültige 'steps'-Liste.")
        return await _execute_plan_logic(skill_plan, initial_context=params)

    # SKILL.md Skill (script-basiert oder instructional)
    if source == "skill_md":
        skill = _load_skill_md_by_name(resolved_name)
        if not skill:
            raise Exception(f"SKILL.md Skill '{resolved_name}' konnte nicht geladen werden.")

        entry_script = skill_meta.get("entry_script")
        if entry_script:
            script_args: List[str] = []
            if params:
                # Übergabe als JSON-String für generische Script-Entrypoints.
                script_args.append(json.dumps(params, ensure_ascii=False))

            script_result = skill.execute_script(entry_script, *script_args)
            if not isinstance(script_result, dict):
                raise Exception(
                    f"Skill-Script '{entry_script}' lieferte ein ungültiges Ergebnis: {type(script_result).__name__}"
                )
            if not script_result.get("success"):
                raise Exception(
                    f"Skill-Script '{entry_script}' fehlgeschlagen: {script_result.get('error') or script_result.get('stderr') or 'unknown error'}"
                )

            return {
                "plan_status": "done",
                "skill_name": resolved_name,
                "source": "skill_md",
                "execution_mode": "script",
                "entry_script": entry_script,
                "result": script_result,
            }

        full_context = skill.get_full_context()
        return {
            "plan_status": "done",
            "skill_name": resolved_name,
            "source": "skill_md",
            "execution_mode": "instructional",
            "instructions": full_context[:8000],
            "available_scripts": skill_meta.get("available_scripts", []),
            "available_references": skill_meta.get("available_references", []),
            "message": (
                "Instructional skill loaded. Use these instructions/resources "
                "to execute the task with appropriate tools."
            ),
        }

    raise Exception(
        f"Skill '{resolved_name}' hat eine unbekannte Source '{source}'."
    )

@tool(
    name="list_available_skills",
    description="Gibt eine Liste aller Skill-Namen und ihrer Meta-Beschreibung zurück.",
    parameters=[],
    capabilities=["automation", "planning"],
    category=C.AUTOMATION
)
async def list_available_skills() -> dict:
    """Gibt eine Liste aller Skill-Namen und ihrer Meta-Beschreibung zurück."""
    try:
        catalog = _build_skill_catalog()
    except Exception as e:
        raise Exception(f"Fehler beim Laden der Skills: {e}")

    result = []
    for name in sorted(catalog.keys()):
        skill_meta = catalog[name]
        result.append(
            {
                "name": name,
                "steps": int(skill_meta.get("steps_count", 0)),
                "description": skill_meta.get("description", "Keine Beschreibung."),
                "source": skill_meta.get("source", "unknown"),
                "execution_mode": skill_meta.get("execution_mode", "unknown"),
                "required_params": skill_meta.get("required_params", []),
            }
        )

    return {"skills": result}

@tool(
    name="get_skill_details",
    description="Gibt die detaillierte Beschreibung und die erwarteten Parameter für einen Skill zurück.",
    parameters=[
        P("name", "string", "Name des Skills"),
    ],
    capabilities=["automation", "planning"],
    category=C.AUTOMATION
)
async def get_skill_details(name: str) -> dict:
    """Gibt die detaillierte Beschreibung und die erwarteten Parameter für einen Skill zurück."""
    log.info(f"Suche Details für Skill '{name}'...")
    try:
        catalog = _build_skill_catalog()
    except Exception as e:
        raise Exception(f"Fehler beim Laden der Skills: {e}")

    skill_meta = catalog.get(name)
    if not skill_meta:
        raise Exception(f"Skill '{name}' nicht gefunden.")

    response = {
        "name": name,
        "description": skill_meta.get("description", "Keine Beschreibung verfügbar."),
        "required_params": sorted(skill_meta.get("required_params", [])),
        "source": skill_meta.get("source", "unknown"),
        "execution_mode": skill_meta.get("execution_mode", "unknown"),
        "steps_count": int(skill_meta.get("steps_count", 0)),
    }

    if skill_meta.get("source") == "skill_md":
        response["available_scripts"] = skill_meta.get("available_scripts", [])
        response["available_references"] = skill_meta.get("available_references", [])
        response["available_assets"] = skill_meta.get("available_assets", [])
        response["entry_script"] = skill_meta.get("entry_script")
    elif skill_meta.get("source") == "skills_yml":
        response["also_available_as"] = skill_meta.get("also_available_as")
        if "skill_md_scripts" in skill_meta:
            response["skill_md_scripts"] = skill_meta.get("skill_md_scripts", [])
            response["skill_md_references"] = skill_meta.get("skill_md_references", [])

    return response
