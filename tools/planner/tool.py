# tools/planner/tool.py

import json
import logging
import os
import re
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

SKILLS_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../agent/skills.yml"))

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
    """Lädt einen Skill aus skills.yml und führt dessen 'steps'-Liste aus."""
    try:
        with open(SKILLS_PATH, "r", encoding="utf-8") as f:
            skills_data = yaml.safe_load(f) or {}
    except Exception as e:
        raise Exception(f"Skills-Datei kann nicht geladen werden: {e}")

    skill_data = skills_data.get(name)
    if not skill_data:
        raise Exception(f"Skill '{name}' nicht in skills.yml gefunden.")

    skill_plan = skill_data.get("steps")
    if not isinstance(skill_plan, list):
        raise Exception(f"Skill '{name}' hat keine gültige 'steps'-Liste.")

    log.info(f"SKILL: Führe Skill '{name}' mit Startparametern aus: {params}")
    return await _execute_plan_logic(skill_plan, initial_context=params)

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
        with open(SKILLS_PATH, "r", encoding="utf-8") as f:
            skills = yaml.safe_load(f) or {}
    except Exception as e:
        raise Exception(f"Fehler beim Laden der Skills: {e}")

    result = []
    for name, skill_data in skills.items():
        if not isinstance(skill_data, dict): continue
        meta = skill_data.get("meta", {})
        desc = meta.get("description", "Keine Beschreibung.")
        steps = skill_data.get("steps", [])
        result.append({"name": name, "steps": len(steps), "description": desc})

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
        with open(SKILLS_PATH, "r", encoding="utf-8") as f:
            skills_data = yaml.safe_load(f) or {}
    except Exception as e:
        raise Exception(f"Fehler beim Laden der skills.yml: {e}")

    skill_data = skills_data.get(name)
    if not skill_data or not isinstance(skill_data, dict):
        raise Exception(f"Skill '{name}' nicht in skills.yml gefunden oder hat ungültiges Format.")

    # KORREKTUR: Lese Daten aus der neuen YAML-Struktur
    meta = skill_data.get("meta", {})
    description = meta.get("description", "Keine Beschreibung verfügbar.")
    # Extrahiere Parameter aus dem 'params'-Block in 'meta'
    required_params = list(meta.get("params", {}).keys())

    return {
        "name": name,
        "description": description,
        "required_params": sorted(required_params)
    }
