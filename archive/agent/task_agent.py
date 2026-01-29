# agent/task_agent.py

import logging
import os
import json
import textwrap
import requests
import sys
import re
import asyncio
from pathlib import Path
import time

# --- Modulpfad-Korrektur & Standard-Setup ---
CURRENT_SCRIPT_PATH = Path(__file__).resolve()
PROJECT_ROOT = CURRENT_SCRIPT_PATH.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from openai import OpenAI
from dotenv import load_dotenv
from utils.openai_compat import prepare_openai_params

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
script_logger = logging.getLogger("task_agent")

MCP_URL = "http://127.0.0.1:5000"
load_dotenv()

try:
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    if client.api_key is None: raise ValueError("OPENAI_API_KEY nicht gefunden.")
except Exception as e:
    script_logger.error(f"FATAL: OpenAI-Client konnte nicht initialisiert werden: {e}")
    sys.exit(1)

# ==============================================================================
# NEUER, STRATEGISCHER SYSTEM_PROMPT FÜR DEN TASK_AGENT
# ==============================================================================
SYSTEM_TEMPLATE = """
Du bist Timus, ein hochkompetenter KI-Assistent. Deine Aufgabe ist es, die Ziele des Nutzers effizient und zuverlässig zu erreichen, indem du die dir zur Verfügung stehenden Werkzeuge strategisch einsetzt.

**DEINE HANDLUNGSPRIORITÄTEN (VON OBEN NACH UNTEN):**

1.  **DIREKTE, ATOMARE TOOLS (IMMER BEVORZUGEN):**
    -   Wenn du Dateien lesen, schreiben oder auflisten sollst, benutze IMMER die `file_system_tool`-Methoden (`read_file`, `write_file`, `list_directory`).
    -   Wenn du Code am System selbst ändern sollst, nutze `implement_feature`.
    -   Wenn du eine Websuche machen sollst, nutze `search_web`.
    -   Wenn du eine Aufgabe planen sollst, nutze `add_task`.
    -   **Grundregel:** Wenn es ein spezifisches, nicht-visuelles Werkzeug für eine Aufgabe gibt, benutze es! Es ist schneller und zuverlässiger.

2.  **WEB-BROWSER-AUTOMATION (FÜR WEBSEITEN):**
    -   Wenn das Ziel eine Webseite ist, nutze die `browser_tool`-Methoden (`open_url`, `click_by_text`, `get_text`).

3.  **ERLERNTE FÄHIGKEITEN (SKILLS):**
    -   Wenn eine Aufgabe eine Fähigkeit erfordert, die du gelernt hast, nutze sie. Überprüfe mit `list_skills()`, welche du kennst und wie ihre Parameter lauten.

**DEIN DENKPROZESS:**
1.  **Verstehe das Ziel:** Was will der Nutzer wirklich erreichen? (z.B. "eine Datei erstellen")
2.  **Konsultiere die Prioritätenliste:** Welches ist das direkteste und zuverlässigste Werkzeug für dieses Ziel? (Antwort: `write_file`)
3.  **Plane den Schritt:** Formuliere die `Action` mit den korrekten Parametern.
4.  **Führe aus und bewerte:** Hat der Schritt funktioniert? Wenn nicht, wähle eine alternative Methode.

Deine Aufgabe ist es, den **intelligentesten und kürzesten Weg zum Ziel** zu finden.

ANTWORTFORMAT:
- Solange du arbeitest: `Thought: <Dein Plan für den nächsten einzelnen Schritt.>\nAction: {{"method": "tool_name", "params": {{"key": "value"}}}}`
- Wenn du FERTIG bist: `Thought: <Begründung, warum die Aufgabe erledigt ist.>\nFinal Answer: <Deine abschließende Zusammenfassung für den Nutzer.>`
"""
SYSTEM_PROMPT = SYSTEM_TEMPLATE.format(current_date=time.strftime("%d.%m.%Y"))


# ==============================================================================
# STANDARD-HILFSFUNKTIONEN (Angepasst aus deinen anderen Agenten)
# ==============================================================================

def call_tool(method: str, params: dict | None = None) -> dict:
    params = params or {}
    script_logger.info(f"🔧 Tool-Aufruf an MCP: {method} mit {params}")
    payload = {"jsonrpc": "2.0", "method": method, "params": params, "id": os.urandom(4).hex()}
    try:
        response = requests.post(MCP_URL, json=payload, timeout=240)
        response.raise_for_status()
        data = response.json()
        if "error" in data:
            return {"error": data.get("error", "Unbekannter Fehler")}
        return data.get("result", {})
    except Exception as e:
        return {"error": f"Kommunikationsfehler mit MCP-Server: {e}"}

def llm(messages: list) -> str:
    try:
        params = prepare_openai_params({
            "model": "gpt-5-2025-08-07",
            "messages": messages,
            "temperature": 0.1,
            "max_tokens": 1800
        })
        resp = client.chat.completions.create(**params)
        return resp.choices[0].message.content.strip()
    except Exception as e:
        return f"Error: LLM API Fehler - {e}"

def extract_json_safely(text: str) -> tuple[dict | None, str | None]:
    patterns = [r'Action:\s*```json\s*({[\s\S]*?})\s*```', r'Action:\s*({[\s\S]*?})$']
    match = None
    for pattern in patterns:
        match = re.search(pattern, text, re.DOTALL)
        if match: break
    if not match: return None, "Kein 'Action:' Block im erwarteten Format gefunden."
    json_str = match.group(1).strip()
    json_str = re.sub(r',\s*([\}\]])', r'\1', json_str)
    try:
        return json.loads(json_str), None
    except json.JSONDecodeError as e:
        return None, f"JSON-Parse-Fehler: {e}"

# ==============================================================================
# STANDARD TEXT-BASIERTER REACT-LOOP
# ==============================================================================
def react_loop(user_query: str, max_steps: int = 15):
    script_logger.info(f"🚀 Starte text-basierten ReAct-Loop für: '{user_query}'")
    messages = [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": user_query}]
    
    for step in range(1, max_steps + 1):
        script_logger.info(f"\n--- ⚙️ Schritt {step}/{max_steps} ---")
        
        llm_reply = llm(messages)
        if llm_reply.startswith("Error:"):
            return f"Fehler bei der Kommunikation mit dem LLM: {llm_reply}"

        script_logger.info(f"🧠 Gedanke & Aktion:\n{llm_reply}")
        
        if "Final Answer:" in llm_reply:
            final_answer = llm_reply.split("Final Answer:", 1)[1].strip()
            return final_answer

        messages.append({"role": "assistant", "content": llm_reply})
        
        action_dict, error_msg = extract_json_safely(llm_reply)
        if error_msg or not action_dict:
            script_logger.warning(f"Konnte keine gültige Aktion ableiten: {error_msg}")
            messages.append({"role": "user", "content": f"Observation: {json.dumps({'error': error_msg})}"})
            continue
        
        method = action_dict.get("method")
        params = action_dict.get("params", {})
        
        action_result = call_tool(method, params)
        script_logger.info(f"📋 Ergebnis der Aktion: {action_result}")
        messages.append({"role": "user", "content": f"Observation: {json.dumps(action_result)}"})

    return "⚠️ Maximale Schritte erreicht. Konnte die Aufgabe nicht abschließen."

# ==============================================================================
# EINSTIEGSPUNKT
# ==============================================================================
def main():
    print("\n🤖 Timus TaskAgent v1.0")
    if len(sys.argv) > 1:
        query = " ".join(sys.argv[1:])
        final_answer = react_loop(query)
        print("\n" + "="*80)
        print("💡 FINALE ANTWORT DES AGENTEN:")
        print("="*80)
        print(textwrap.fill(final_answer, width=80))
        print("="*80)
    else:
        print("Dieses Skript erwartet eine Aufgabe als Kommandozeilenargument.")
        print("Beispiel: python agent/task_agent.py \"Schreibe 'Hallo Welt' in die Datei 'hallo.txt'\"")

if __name__ == "__main__":
    main()
