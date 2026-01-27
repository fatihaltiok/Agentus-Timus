# tools/tasks/tasks.py
import os
import logging
import json
import uuid
from pathlib import Path
from datetime import datetime
from typing import Union, List, Optional
import asyncio

from jsonrpcserver import method, Success, Error
from tools.universal_tool_caller import register_tool

log = logging.getLogger(__name__)

# --- Pfad- und Datei-Setup ---
try:
    PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
    TASKS_FILE = PROJECT_ROOT / "tasks.json"
except Exception as e:
    log.error(f"Konnte Task-Datei-Pfad nicht initialisieren: {e}")
    TASKS_FILE = None

# --- Interne, synchrone Hilfsfunktionen ---
def _read_tasks_sync() -> dict:
    if TASKS_FILE and TASKS_FILE.exists():
        try:
            with open(TASKS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, FileNotFoundError):
            return {"tasks": []}
    return {"tasks": []}

def _write_tasks_sync(tasks_data: dict):
    if TASKS_FILE:
        TASKS_FILE.parent.mkdir(exist_ok=True)
        with open(TASKS_FILE, "w", encoding="utf-8") as f:
            json.dump(tasks_data, f, indent=2, ensure_ascii=False)

# --- Asynchrone Tool-Methoden ---
@method
async def add_task(description: str, priority: int = 2, target_agent: str = "research") -> Union[Success, Error]:
    if not TASKS_FILE: return Error(code=-32090, message="Task-Datei nicht konfiguriert.")
    try:
        tasks_data = await asyncio.to_thread(_read_tasks_sync)
        new_task = {
            "id": str(uuid.uuid4()), "description": description, "priority": priority,
            "target_agent": target_agent, "status": "pending",
            "created_at": datetime.now().isoformat(), "completed_at": None, "result_summary": None
        }
        if "tasks" not in tasks_data or not isinstance(tasks_data["tasks"], list):
            tasks_data["tasks"] = []
        tasks_data["tasks"].append(new_task)
        await asyncio.to_thread(_write_tasks_sync, tasks_data)
        log.info(f"✅ Neue Aufgabe hinzugefügt: '{description[:50]}...'")
        return Success({"status": "task_added", "task": new_task})
    except Exception as e:
        return Error(code=-32091, message=f"Fehler beim Hinzufügen der Aufgabe: {e}")

@method
async def get_next_task() -> Union[Success, Error]:
    """
    Holt die nächste ausstehende Aufgabe. Ist robust gegenüber fehlerhaften
    oder inkonsistenten Daten in tasks.json.
    """
    if not TASKS_FILE: return Success({"task": None, "message": "Task-Datei nicht konfiguriert."})
    try:
        tasks_data = await asyncio.to_thread(_read_tasks_sync)
        all_tasks = tasks_data.get("tasks", [])
        
        pending_tasks = [t for t in all_tasks if isinstance(t, dict) and t.get("status") == "pending"]
        if not pending_tasks: return Success({"task": None})

        def sort_key(task):
            # --- Robuste Prioritäts-Ermittlung ---
            priority_val = 99 # Standard-Fallback-Priorität
            priority = task.get("priority")
            if isinstance(priority, int):
                priority_val = priority
            elif isinstance(priority, str):
                try:
                    priority_val = int(priority)
                except ValueError:
                    # Konnte nicht in Zahl umgewandelt werden, prüfe auf Keywords
                    p_lower = priority.lower()
                    if "high" in p_lower or "hoch" in p_lower: priority_val = 1
                    elif "medium" in p_lower or "mittel" in p_lower: priority_val = 2
                    elif "low" in p_lower or "niedrig" in p_lower: priority_val = 3
            
            # --- Robuste Datums-Ermittlung ---
            # Gib ein sehr altes Datum zurück, wenn der Zeitstempel fehlt,
            # damit diese Aufgaben nicht bevorzugt werden.
            created_at = task.get("created_at", "1970-01-01T00:00:00.000000")
            
            return (priority_val, created_at)

        pending_tasks.sort(key=sort_key)
        
        return Success({"task": pending_tasks[0]})

    except Exception as e:
        log.error(f"Unerwarteter Fehler in get_next_task: {e}", exc_info=True)
        return Error(code=-32094, message=f"Fehler beim Abrufen der nächsten Aufgabe: {e}")

@method
async def update_task_status(task_id: str, status: str, result_summary: Optional[str] = None) -> Union[Success, Error]:
    if not TASKS_FILE: return Error(code=-32090, message="Task-Datei nicht konfiguriert.")
    try:
        tasks_data = await asyncio.to_thread(_read_tasks_sync)
        task_found = False
        for task in tasks_data.get("tasks", []):
            if isinstance(task, dict) and task.get("id") == task_id:
                task["status"] = status
                if status in ["completed", "failed"]: task["completed_at"] = datetime.now().isoformat()
                if result_summary: task["result_summary"] = result_summary
                task_found = True
                break
        if not task_found: return Error(code=-32092, message=f"Aufgabe mit ID '{task_id}' nicht gefunden.")
        await asyncio.to_thread(_write_tasks_sync, tasks_data)
        log.info(f"🔄 Status von Aufgabe '{task_id}' auf '{status}' aktualisiert.")
        return Success({"status": "updated", "task_id": task_id, "new_status": status})
    except Exception as e:
        return Error(code=-32093, message=f"Fehler beim Aktualisieren der Aufgabe: {e}")

# --- Registrierung ---
# Annahme: Sie haben eine register_tool-Funktion. Falls nicht, entfernen Sie diese Zeilen.
try:
    from tools.universal_tool_caller import register_tool
    register_tool("add_task", add_task)
    register_tool("get_next_task", get_next_task)
    register_tool("update_task_status", update_task_status)
    log.info("✅ Task-Management-Tools registriert.")
except ImportError:
    log.warning("Konnte `register_tool` nicht importieren. Task-Tools sind möglicherweise nicht für alle Agenten verfügbar.")