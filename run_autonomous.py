# run_autonomous.py (Refactored to use consolidated agent classes)

import logging
import os
import sys
import asyncio
import re
import textwrap
from pathlib import Path

# --- Modulpfad-Korrektur ---
CURRENT_SCRIPT_PATH = Path(__file__).resolve()
PROJECT_ROOT = CURRENT_SCRIPT_PATH.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# --- Konfiguration ---
# Der MCP_URL wird nicht mehr benötigt, da wir `call_tool_internal` verwenden.
TICK_INTERVAL_SECONDS = 15  # Wir können das Intervall verkürzen, da die Operationen schneller sind.

# --- Logging ---
# Wir verwenden den gleichen Logging-Stil wie im MCP-Server.
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s | %(levelname)-7s | %(name)-20s | %(message)s",
    stream=sys.stdout
)
log = logging.getLogger("TimusAutonomousMainframe")

# --- WICHTIG: Importiere die Agenten-Klassen und den internen Tool-Caller ---
from agent.timus_consolidated import BaseAgent, CreativeAgent, DeveloperAgent, MetaAgent, VisualAgent
from tools.planner.planner_helpers import call_tool_internal

# Mapping von Agenten-Namen aus der Task-Queue zu den Klassen
AGENT_CLASS_MAP = {
    "executor": BaseAgent,
    "research": BaseAgent,  # Alias für den Standard-Executor
    "creative": CreativeAgent,
    "development": DeveloperAgent,
    "meta": MetaAgent,
    "visual": VisualAgent,
}
DEFAULT_AGENT_PROMPT = "Du bist Timus, ein KI-Agent. Nutze die dir zur Verfügung stehenden Werkzeuge, um die Aufgabe zu lösen."


# --- Haupt-Loop ---
async def autonomous_loop():
    """
    Der Haupt-Herzschlag des Systems. Holt periodisch Aufgaben und führt sie aus,
    indem die entsprechenden Agenten-Klassen instanziiert werden.
    """
    log.info("🚀 TIMUS AUTONOMOUS MAINFRAME GESTARTET (v2.0 - Class-Based). Warte auf Aufgaben...")
    
    # Warte kurz, um sicherzustellen, dass der MCP-Server vollständig gestartet ist.
    await asyncio.sleep(5) 
    
    while True:
        log.info(f"--- Tick --- (Nächste Prüfung in {TICK_INTERVAL_SECONDS}s)")
        
        # Rufe das Tool intern und ohne HTTP-Overhead auf.
        next_task_result = await call_tool_internal("get_next_task")
        
        if "error" in next_task_result:
            log.error(f"Fehler beim Abrufen der Aufgabe: {next_task_result['error']}")
            await asyncio.sleep(TICK_INTERVAL_SECONDS)
            continue
        
        task = next_task_result.get("task")
        if task:
            task_id = task['id']
            description = task['description']
            
            # Bereinige den Agenten-Namen
            agent_name_raw = task.get('target_agent', 'executor')
            agent_name = re.split(r'[-\s]', agent_name_raw)[0].lower()
            
            log.info("="*80)
            log.info(f"🎯 NEUE AUFGABE GEFUNDEN: {description}")
            log.info(f"   ID: {task_id[:8]}, Ziel-Agent: '{agent_name}'")
            log.info("="*80)

            await call_tool_internal("update_task_status", {"task_id": task_id, "status": "in_progress"})
            
            AgentClass = AGENT_CLASS_MAP.get(agent_name)
            if AgentClass:
                try:
                    # Instanziiere die richtige Agenten-Klasse
                    if agent_name in ["executor", "research"]:
                        agent_instance = AgentClass(system_prompt=DEFAULT_AGENT_PROMPT)
                    else:
                        agent_instance = AgentClass()
                    
                    # Führe die Aufgabe aus und warte auf die finale Antwort
                    final_answer = await agent_instance.run(description)
                    
                    result_status = "completed"
                    summary = final_answer
                    
                except Exception as e:
                    log.error(f"Fehler bei der Ausführung von Task {task_id} durch Agent '{agent_name}': {e}", exc_info=True)
                    result_status = "failed"
                    summary = f"Ein interner Fehler ist im Agenten aufgetreten: {e}"

                # Aktualisiere den Task-Status mit dem Ergebnis
                await call_tool_internal("update_task_status", {
                    "task_id": task_id, "status": result_status, "result_summary": summary
                })
                log.info(f"Aufgabe '{task_id[:8]}' mit Status '{result_status}' abgeschlossen.")
                
            else:
                log.error(f"Unbekannter Agent-Typ '{agent_name}'. Markiere Aufgabe als fehlgeschlagen.")
                await call_tool_internal("update_task_status", {"task_id": task_id, "status": "failed", "result_summary": f"Unbekannter Agent-Typ: {agent_name}"})
        else:
            log.info("Keine unerledigten Aufgaben. System im Leerlauf.")
        
        await asyncio.sleep(TICK_INTERVAL_SECONDS)

# --- Startpunkt ---
if __name__ == "__main__":
    log.warning("WICHTIG: Stelle sicher, dass der MCP-Server in einem separaten Terminal läuft, bevor du dieses Skript startest!")
    try:
        asyncio.run(autonomous_loop())
    except KeyboardInterrupt:
        print("\n👋 Autonomer Modus wird beendet.")
    except Exception as e:
        log.critical(f"Ein kritischer Fehler hat den autonomen Loop beendet: {e}", exc_info=True)