# tools/planner/tool.py

import json
import logging
import os
import re
from typing import Any, Dict, List, Optional, Union

import yaml
from jsonrpcserver import method, Success, Error

from tools.universal_tool_caller import register_tool
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
async def _execute_plan_logic(steps: List[Dict[str, Any]], initial_context: Dict[str, Any] = None) -> Union[Success, Error]:
    """
    Die zentrale Logik zur Ausführung eines Plans mit Kontext-Management.
    """
    execution_context = initial_context or {}
    observations: List[Dict[str, Any]] = []

    for idx, step in enumerate(steps):
        if not isinstance(step, dict):
            return Error(code=-32602, message=f"Schritt {idx+1} hat ein ungültiges Format.")

        try:
            current_params = _substitute_variables(step.get("params", {}), execution_context)
            method_name = step.get("method")
            if not method_name:
                return Error(code=-32602, message=f"Keine Methode in Schritt {idx+1} angegeben.")
            log.info(f"DEBUG: execution_context = {execution_context}")
            log.info(f"DEBUG: raw params = {step.get('params', {})}")
            log.info(f"PLANNER Step {idx+1}: Führe '{method_name}' mit Parametern aus: {current_params}")
            result = await call_tool_internal(method_name, current_params)
            observations.append({method_name: result})

            if isinstance(result, dict) and result.get("error"):
                error_message = f"Plan bei Schritt {idx+1} ('{method_name}') fehlgeschlagen."
                log.error(f"{error_message}: {result['error']}")
                return Error(code=-32010, message=error_message, data={"error_details": result['error'], "completed_observations": observations})

            result_key = step.get("register_result_as")
            if result_key:
                log.info(f"PLANNER: Speichere Ergebnis von '{method_name}' als Variable '{result_key}'.")
                execution_context[result_key] = result
        
        except Exception as e:
            log.error(f"Kritischer Fehler während der Planausführung bei Schritt {idx+1}: {e}", exc_info=True)
            return Error(code=-32000, message=f"Kritischer Fehler bei Planausführung: {e}")

    final_result = observations[-1] if observations else {}
    return Success({"plan_status": "done", "final_result": final_result, "all_observations": observations})


# --- Öffentliche RPC-Methoden ---

@method
async def run_plan(steps: List[Dict[str, Any]], initial_params: Optional[Dict[str, Any]] = None) -> Union[Success, Error]:
    """Führt eine Liste von Aktionen nacheinander aus."""
    if not isinstance(steps, list):
        return Error(code=-32602, message="Der Plan muss eine Liste von Schritten sein.")
    return await _execute_plan_logic(steps, initial_context=initial_params)

SKILLS_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../agent/skills.yml"))

@method
async def run_skill(name: str, params: Optional[Dict[str, Any]] = None) -> Union[Success, Error]:
    """Lädt einen Skill aus skills.yml und führt dessen 'steps'-Liste aus."""
    try:
        with open(SKILLS_PATH, "r", encoding="utf-8") as f:
            skills_data = yaml.safe_load(f) or {}
    except Exception as e:
        return Error(code=-32011, message=f"Skills-Datei kann nicht geladen werden: {e}")

    skill_data = skills_data.get(name)
    if not skill_data:
        return Error(code=-32601, message=f"Skill '{name}' nicht in skills.yml gefunden.")
    
    skill_plan = skill_data.get("steps")
    if not isinstance(skill_plan, list):
        return Error(code=-32602, message=f"Skill '{name}' hat keine gültige 'steps'-Liste.")

    log.info(f"SKILL: Führe Skill '{name}' mit Startparametern aus: {params}")
    return await _execute_plan_logic(skill_plan, initial_context=params)

@method
async def list_available_skills() -> Union[Success, Error]:
    """Gibt eine Liste aller Skill-Namen und ihrer Meta-Beschreibung zurück."""
    try:
        with open(SKILLS_PATH, "r", encoding="utf-8") as f:
            skills = yaml.safe_load(f) or {}
    except Exception as e:
        return Error(code=-32013, message=f"Fehler beim Laden der Skills: {e}")
    
    result = []
    for name, skill_data in skills.items():
        if not isinstance(skill_data, dict): continue
        meta = skill_data.get("meta", {})
        desc = meta.get("description", "Keine Beschreibung.")
        steps = skill_data.get("steps", [])
        result.append({"name": name, "steps": len(steps), "description": desc})
        
    return Success({"skills": result})

@method
async def get_skill_details(name: str) -> Union[Success, Error]:
    """Gibt die detaillierte Beschreibung und die erwarteten Parameter für einen Skill zurück."""
    log.info(f"Suche Details für Skill '{name}'...")
    try:
        with open(SKILLS_PATH, "r", encoding="utf-8") as f:
            skills_data = yaml.safe_load(f) or {}
    except Exception as e:
        return Error(code=-32013, message=f"Fehler beim Laden der skills.yml: {e}")

    skill_data = skills_data.get(name)
    if not skill_data or not isinstance(skill_data, dict):
        return Error(code=-32601, message=f"Skill '{name}' nicht in skills.yml gefunden oder hat ungültiges Format.")
    
    # KORREKTUR: Lese Daten aus der neuen YAML-Struktur
    meta = skill_data.get("meta", {})
    description = meta.get("description", "Keine Beschreibung verfügbar.")
    # Extrahiere Parameter aus dem 'params'-Block in 'meta'
    required_params = list(meta.get("params", {}).keys())
    
    return Success({
        "name": name,
        "description": description,
        "required_params": sorted(required_params)
    })

# --- Registrierung ---
register_tool("run_plan", run_plan)
register_tool("run_skill", run_skill)
register_tool("list_available_skills", list_available_skills)
register_tool("get_skill_details", get_skill_details)

log.info("✅ Advanced Planner Tools (Finale Version) registriert.")