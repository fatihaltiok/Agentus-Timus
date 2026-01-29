# agent/timus_consolidated.py
# Dies ist die neue, konsolidierte Master-Version, die als timus_react.py dienen soll.

import logging
import os
import json
import textwrap
import sys
import re
import asyncio
from pathlib import Path
from datetime import datetime
import time
import requests
import mss
from PIL import Image

# --- Modulpfad-Korrektur & Standard-Setup ---
CURRENT_SCRIPT_PATH = Path(__file__).resolve()
PROJECT_ROOT = CURRENT_SCRIPT_PATH.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from openai import OpenAI
from dotenv import load_dotenv
from utils.openai_compat import prepare_openai_params

# --- Globale Konfiguration ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s | %(levelname)-7s | %(name)-20s | %(message)s')
log = logging.getLogger("TimusConsolidatedAgent")

load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
MCP_URL = "http://127.0.0.1:5000"


# ==============================================================================
# PROMPT-BIBLIOTHEK: Spezialisierte Anweisungen für jeden Modus
# ==============================================================================

# Prompt für den Standard-Modus (Aufgaben ausführen)
TASK_AGENT_PROMPT_TEMPLATE = """
# IDENTITÄT & MISSION
Du bist Timus, ein hochkompetenter KI-Assistent. Deine Mission ist es, die Anfrage des Nutzers durch die methodische Wahl des besten Werkzeugs zu lösen.
HEUTIGES DATUM: {current_date}.

# HANDLUNGSPRIORITÄTEN (VON OBEN NACH UNTEN)
1.  **DIREKTE, ATOMARE TOOLS (IMMER BEVORZUGEN):** `write_file`, `read_file`, `list_directory`, `implement_feature`, `search_web`, `add_task`.
2.  **WEB-BROWSER-AUTOMATION:** `open_url`, `click_by_text`, `get_text`.
3.  **ERLERNTE FÄHIGKEITEN:** Nutze `list_skills()`, um deine Fähigkeiten und deren Parameter zu prüfen und anzuwenden.

# ANTWORTFORMAT
Thought: <Dein Plan>\nAction: {{"method": "werkzeug_name", "params": {{"parameter_name": "wert"}}}}
"""

# Prompt für den Tiefenrecherche-Modus
DEEP_RESEARCH_PROMPT_TEMPLATE = """
# IDENTITÄT & MISSION
Du bist der Deep Research Agent. Deine Mission ist es, komplexe Anfragen durch gründliche Recherche zu beantworten.
HEUTIGES DATUM: {current_date}.

# WERKZEUGE
- `start_deep_research(query, focus_areas, verification_mode)`: Dein Hauptwerkzeug.
- `generate_research_report(session_id)`: Dein finales Werkzeug.

# WORKFLOW
1.  **ANALYSIEREN:** Leite `query` und `focus_areas` aus der Nutzeranfrage ab.
2.  **RECHERCHIEREN:** Führe `start_deep_research` aus.
3.  **BERICHT ERSTELLEN:** Nutze die `session_id` aus dem Ergebnis, um `generate_research_report` aufzurufen.
4.  **ABSCHLIESSEN:** Fasse das Ergebnis des Berichts in deiner `Final Answer:` zusammen.

# ANTWORTFORMAT
Thought: <Dein Plan>\nAction: {{"method": "werkzeug_name", "params": {{...}}}}
"""

# Prompt für den visuellen Modus
VISUAL_AGENT_PROMPT_TEMPLATE = """
# MISSION
Du bist Timus, ein visueller Automatisierungs-Agent. Du siehst einen Screenshot und musst die nächste Aktion planen, um das Ziel zu erreichen.

# WERKZEUGE
- `click_at(x, y)`
- `type_text(text_to_type, press_enter_after)`
- `finish_task(final_message)`

# DENKPROZESS
Jede Aktion MUSS auf einer visuellen Analyse des Bildes basieren. Leite Koordinaten präzise ab.

# ANTWORT-STRUKTUR
<response>
  {{
    "thought": "Meine visuelle Analyse und mein Plan.",
    "action": {{ "method": "...", "params": {{ ... }} }}
  }}
</response>
"""

# Prompt zur Modus-Auswahl
MODE_SELECTION_PROMPT = """
Du bist der interne Dispatcher des Timus-Agenten. Deine einzige Aufgabe ist es, basierend auf der Nutzeranfrage den korrekten Operationsmodus auszuwählen.

Hier sind die Modi und wann sie zu verwenden sind:

1.  **task_mode**: Für allgemeine, abstrakte Aufgaben. Dies ist der Standardmodus.
    - **Beispiele**: "Schreibe 'Hallo' in eine Datei", "Recherchiere das Wetter", "Fasse diesen Artikel zusammen", "Nutze deine Fähigkeit X".

2.  **deep_research_mode**: NUR für Anfragen, die explizit nach "Tiefenrecherche", "umfassende Analyse", "detaillierte Untersuchung" oder "Faktenprüfung" verlangen.
    - **Beispiele**: "Mache eine Tiefenrecherche zu KI in der Medizin", "Erstelle eine umfassende Analyse über Quantencomputing mit Faktenprüfung".

3.  **visual_mode**: NUR für Anfragen, die explizit die visuelle Bedienung einer Desktop-Anwendung erfordern, die keine API hat.
    - **Beispiele**: "Öffne GIMP und erstelle ein neues Bild mit 500x500 Pixeln", "Klicke auf das Firefox-Icon auf dem Desktop und öffne die Einstellungen".

Analysiere die folgende Nutzeranfrage und antworte NUR mit einem einzigen Wort: `task_mode`, `deep_research_mode` oder `visual_mode`.

Nutzeranfrage: "{user_query}"
"""

# ==============================================================================
# HILFSFUNKTIONEN (Konsolidiert)
# ==============================================================================

def call_tool(method: str, params: dict | None = None) -> dict:
    params = params or {}
    log.info(f"🔧 Tool-Aufruf an MCP: {method} mit {params}")
    payload = {"jsonrpc": "2.0", "method": method, "params": params, "id": os.urandom(4).hex()}
    try:
        response = requests.post(MCP_URL, json=payload, timeout=1800) # Langer Timeout für Deep Research
        response.raise_for_status()
        data = response.json()
        return data.get("result", {"error": data.get("error", "Unbekannter Fehler")})
    except Exception as e:
        return {"error": f"Kommunikationsfehler mit MCP-Server: {e}"}

def llm(messages: list) -> str:
    try:
        params = prepare_openai_params({
            "model": "gpt-5-2025-08-07",
            "messages": messages,
            "temperature": 0.0,
            "max_tokens": 2000
        })
        resp = client.chat.completions.create(**params)
        return resp.choices[0].message.content.strip()
    except Exception as e:
        log.error(f"LLM API Fehler: {e}", exc_info=True)
        return f"Error: LLM API Fehler - {e}"

def extract_json_safely(text: str, response_tag: bool = False) -> tuple[dict | None, str | None]:
    """Extrahiert JSON aus 'Action:' oder '<response>'-Tags."""
    json_str = ""
    if response_tag:
        match = re.search(r'<response>([\s\S]*?)</response>', text, re.DOTALL)
        if match:
            json_str = match.group(1).strip()
    else:
        patterns = [r'Action:\s*```json\s*({[\s\S]*?})\s*```', r'Action:\s*({[\s\S]*?})$']
        for pattern in patterns:
            match = re.search(pattern, text, re.DOTALL)
            if match:
                json_str = match.group(1).strip()
                break
    
    if not json_str:
        return None, "Kein gültiger Action/Response-Block gefunden."
    
    try:
        data = json.loads(json_str)
        if response_tag: # Für den visuellen Modus
             if "action" not in data or "method" not in data["action"]:
                 return None, "JSON aus <response> fehlt der 'action'-Schlüssel."
             return data, None
        else: # Für die textbasierten Modi
            if "method" not in data:
                return None, "JSON aus Action: fehlt der 'method'-Schlüssel."
            return data, None
    except json.JSONDecodeError as e:
        return None, f"JSON-Parse-Fehler: {e}"

def get_screenshot_as_base64() -> str:
    with mss.mss() as sct:
        sct_img = sct.grab(sct.monitors[1])
        img = Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")
    import io
    buffered = io.BytesIO()
    img.save(buffered, format="PNG")
    return base64.b64encode(buffered.getvalue()).decode('utf-8')

# ==============================================================================
# SPEZIALISIERTE ReAct-LOOPS
# ==============================================================================

async def task_react_loop(user_query: str, system_prompt: str, max_steps: int = 15):
    """Standard, text-basierter ReAct-Loop für allgemeine Aufgaben."""
    log.info(f"🚀 Starte Task-Modus für: '{user_query}'")
    messages = [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_query}]
    
    for step in range(1, max_steps + 1):
        log.info(f"\n--- ⚙️ Task-Schritt {step}/{max_steps} ---")
        llm_reply = await asyncio.to_thread(llm, messages)
        if llm_reply.startswith("Error:"): return f"LLM Fehler: {llm_reply}"
        log.info(f"🧠 Gedanke & Aktion:\n{llm_reply}")
        
        if "Final Answer:" in llm_reply:
            return llm_reply.split("Final Answer:", 1)[1].strip()

        messages.append({"role": "assistant", "content": llm_reply})
        action_dict, error_msg = extract_json_safely(llm_reply)
        
        if error_msg or not action_dict:
            log.warning(f"Aktion konnte nicht geparst werden: {error_msg}")
            messages.append({"role": "user", "content": f"Observation: {json.dumps({'error': error_msg})}"})
            continue
        
        result = await asyncio.to_thread(call_tool, action_dict.get("method"), action_dict.get("params"))
        log.info(f"📋 Ergebnis: {result}")
        messages.append({"role": "user", "content": f"Observation: {json.dumps(result)}"})

    return "⚠️ Maximale Schritte im Task-Modus erreicht."

async def visual_cognitive_loop(user_query: str, system_prompt: str, max_steps: int = 20):
    """Loop für visuelle Desktop-Automatisierung."""
    log.info(f"🚀 Starte Visual-Modus für: '{user_query}'")
    history = [{"role": "system", "content": system_prompt}, {"role": "user", "content": [{"type": "text", "text": f"ZIEL: {user_query}"}]}]
    
    for step in range(1, max_steps + 1):
        log.info(f"\n--- 👁️ Visual-Schritt {step}/{max_steps} ---")
        await asyncio.sleep(3) # Zeit für GUI-Reaktion
        screenshot = get_screenshot_as_base64()
        
        current_messages = history + [{"role": "user", "content": [
            {"type": "text", "text": "Analysiere das Bild und die Historie. Plane den nächsten Schritt."},
            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{screenshot}"}}
        ]}]
        
        llm_reply = await asyncio.to_thread(llm, current_messages)
        if llm_reply.startswith("Error:"): return f"LLM Fehler: {llm_reply}"
        
        history.append({"role": "assistant", "content": llm_reply})
        response_data, error_msg = extract_json_safely(llm_reply, response_tag=True)
        
        if error_msg or not response_data:
            log.warning(f"Aktion konnte nicht geparst werden: {error_msg}")
            history.append({"role": "user", "content": [{"type": "text", "text": f"Observation: {json.dumps({'error': error_msg})}"}]})
            continue
            
        log.info(f"🧠 Gedanke: {response_data.get('thought')}")
        action = response_data.get("action", {})
        
        if action.get("method") == "finish_task":
            return action.get("params", {}).get("final_message", "Aufgabe abgeschlossen.")
            
        result = await asyncio.to_thread(call_tool, action.get("method"), action.get("params"))
        log.info(f"📋 Ergebnis: {result}")
        history.append({"role": "user", "content": [{"type": "text", "text": f"Observation: {json.dumps(result)}"}]})

    return "⚠️ Maximale Schritte im Visual-Modus erreicht."

# ==============================================================================
# EINSTIEGSPUNKT mit Modus-Auswahl
# ==============================================================================
async def main():
    print("\n🤖 Timus Consolidated Agent v1.0")
    
    if len(sys.argv) > 1:
        query = " ".join(sys.argv[1:])
    else:
        query = input(f"\n{textwrap.dedent(chr(27)+'[34m')}Timus> {textwrap.dedent(chr(27)+'[0m')}").strip()

    if not query:
        return

    # Schritt 1: Modus auswählen
    log.info(f"Analysiere Anfrage, um den besten Modus zu wählen: '{query}'")
    mode_prompt = MODE_SELECTION_PROMPT.format(user_query=query)
    mode_response = await asyncio.to_thread(llm, [{"role": "user", "content": mode_prompt}])
    selected_mode = mode_response.strip().lower()
    log.info(f"Entscheidung: Operationsmodus ist '{selected_mode}'")

    # Schritt 2: Entsprechenden Loop ausführen
    final_answer = ""
    start_time = time.time()

    if "deep_research_mode" in selected_mode:
        prompt = DEEP_RESEARCH_PROMPT_TEMPLATE.format(current_date=datetime.now().strftime("%d.%m.%Y"))
        final_answer = await task_react_loop(query, prompt, max_steps=5)
    elif "visual_mode" in selected_mode:
        prompt = VISUAL_AGENT_PROMPT_TEMPLATE.format(current_date=datetime.now().strftime("%d.%m.%Y"))
        final_answer = await visual_cognitive_loop(query, prompt)
    else: # Standard ist der Task-Modus
        # Wir müssen hier noch die Tool-Liste abrufen und in den Prompt einfügen
        tool_list_response = await asyncio.to_thread(call_tool, "list_available_tools")
        tools_desc = "Keine Werkzeuge gefunden."
        if isinstance(tool_list_response, dict) and "tools" in tool_list_response:
             tools_desc = "\n".join([f"- {tool}" for tool in tool_list_response["tools"]])

        prompt = TASK_AGENT_PROMPT_TEMPLATE.format(
            current_date=datetime.now().strftime("%d.%m.%Y"),
            tools_description=tools_desc
        )
        final_answer = await task_react_loop(query, prompt)

    elapsed = round(time.time() - start_time, 1)
    
    print("\n" + "="*80)
    print("💡 FINALE ANTWORT DES AGENTEN:")
    print("="*80)
    print(textwrap.fill(final_answer, width=80))
    print(f"\n⏱ Verarbeitungszeit: {elapsed} Sekunden")
    print("="*80)

if __name__ == "__main__":
    asyncio.run(main())
