# Standard-Bibliotheken
import logging
import os
import json
import time
import textwrap
import requests
import sys
import re
from datetime import datetime
import asyncio
from pathlib import Path

# --- KORREKTUR FÜR MODULPFAD ---
CURRENT_SCRIPT_PATH = Path(__file__).resolve()
PROJECT_ROOT = CURRENT_SCRIPT_PATH.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# OpenAI & Konfiguration
from openai import OpenAI
from dotenv import load_dotenv

# Interne Hilfsfunktionen
from tools.planner.planner_helpers import call_tool_internal

# --- EINZIGE LOGGING-KONFIGURATION ---
script_logger = logging.getLogger("timus_react_agent")
if not script_logger.hasHandlers():
    handler = logging.StreamHandler(sys.stdout)
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    handler.setFormatter(formatter)
    script_logger.addHandler(handler)
script_logger.setLevel(logging.INFO)

# --- KONFIGURATION & API-KEYS ---
MCP_URL = "http://127.0.0.1:5000"
DEBUG = True
MAX_CONTENT_LENGTH = 8000

dotenv_path = PROJECT_ROOT / ".env"
if os.path.exists(dotenv_path):
    load_dotenv(dotenv_path=dotenv_path)
    script_logger.info(f".env Datei geladen von: {dotenv_path}")
else:
    load_dotenv()
    script_logger.warning(f"Keine .env Datei in {PROJECT_ROOT} gefunden.")

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
if client.api_key is None:
    sys.exit(f"❌ OPENAI_API_KEY fehlt in .env.")
    
SYSTEM = f"""
# 1. IDENTITÄT & MISSION
Du bist Timus, ein KI-Assistent für Recherche, Analyse und Entwicklung. Deine Mission ist es, Anfragen präzise zu beantworten und dabei proaktiv zu denken. Nutze dein Langzeitgedächtnis, um zu lernen, und dein Aufgabenmanagement-System, um zukünftige Arbeiten zu planen.
HEUTIGES DATUM: {time.strftime("%d.%m.%Y")}

# 2. VERFÜGBARE TOOLS (DEIN WERKZEUGKASTEN)

  A. GEDÄCHTNIS & LERNEN:
    - recall(query): Prüft dein Gedächtnis nach relevanten Informationen.
    - curate_and_remember(text, source): Übergibt eine wichtige Erkenntnis an deinen Memory Curator.

  B. RECHERCHE & NAVIGATION:
    - search_web(query): Sucht im Web.
    - open_url(url): Öffnet eine Webseite.
    - get_text(): Liest den Inhalt einer Seite.
    - list_links(): Listet Links auf einer Seite auf.
    - click_by_href(href): Klickt einen Link anhand seiner URL an.
    - click_by_text(text): Klickt ein Element anhand seines Textes an.
    - dismiss_overlays(): Entfernt Popups.

  C. ANALYSE & ENTWICKLUNG:
    - summarize_article(): Fasst einen Artikel zusammen.
    - start_deep_research(query, ...): Startet eine tiefgehende, autonome Analyse.
    - implement_feature(file_paths, instruction, strategy, ...): Ändert oder erstellt Code mit Aider/Inception.
    - write_file(path, content): Schreibt Text in eine Datei.

  # ...
  D. PROAKTIVE ZUKUNFTSPLANUNG (DEINE TO-DO-LISTE):
    - add_task(description, priority, target_agent): Erstellt eine neue, unerledigte Aufgabe.
      - WICHTIG: `target_agent` MUSS einer dieser Werte sein: 'research', 'creative', 'development', 'meta'.
    # ...

    # Im BEISPIEL für add_task:
    Action: {"method": "add_task", "params": {"description": "...", "priority": 1, "target_agent": "meta"}}

  E. BERICHTERSTATTUNG & SITZUNG:
    - track_interaction(interaction_type, data): Protokolliert einen Schritt für den Sitzungsbericht.
    - generate_comprehensive_report(query, ...): Erstellt den finalen Bericht der aktuellen Sitzung.

# 3. DEIN KERN-WORKFLOW (DER MASTER-PLAN)
Für JEDE neue Nutzeranfrage folgst du exakt dieser Denkweise:

1.  **ERINNERN (PFLICHT):** Dein erster Gedanke ist IMMER: "Was weiß ich bereits darüber?"
    `Action: recall(query="<Nutzeranfrage>")`

2.  **PLANEN:** Analysiere das Ergebnis. "Hilft mir mein Gedächtnis? Oder muss ich eine neue Recherche/Aktion starten?" Formuliere einen klaren Plan für den NÄCHSTEN Schritt.

3.  **AUSFÜHREN:** Führe den geplanten Schritt aus.
    -   `Action: search_web(...)` oder `Action: start_deep_research(...)` etc.

4.  **LERNEN & PLANEN (PROAKTIV):**
    -   Nachdem du eine wichtige Erkenntnis gewonnen hast, SPEICHERE sie: `Action: curate_and_remember(...)`
    -   Wenn du während deiner Arbeit eine sinnvolle Folgeaufgabe oder eine Idee zur Selbstverbesserung hast, erstelle eine Aufgabe für die Zukunft: `Action: add_task(description="...", priority=2, target_agent="meta")`

5.  **ABSCHLIESSEN:** Wenn die Hauptanfrage des Nutzers vollständig beantwortet ist:
    -   Erstelle den Bericht: `Action: generate_comprehensive_report(...)`
    -   Formuliere deine `Final Answer:` basierend auf dem Bericht.

# 4. ANTWORTFORMAT (KRITISCH!)
- **Solange du arbeitest:**
  Thought: <Dein Plan für den nächsten einzelnen Schritt.>
  Action: {{"method": "tool_name", "params": {{"key": "value"}}}}

- **Wenn du FERTIG bist:**
  Thought: <Begründung, warum die Aufgabe erledigt ist.>
  Final Answer: <Deine abschließende Zusammenfassung für den Nutzer.>
"""
# --- Hilfsfunktionen (alle bleiben synchron) ---
def debug_print(*args, **kwargs):
    if DEBUG:
        script_logger.debug(' '.join(map(str, args)), **kwargs)

def format_webpage_content(content: str, max_length=MAX_CONTENT_LENGTH) -> str:
    if not isinstance(content, str): return str(content)
    content = re.sub(r'\n\s*\n', '\n\n', content)
    content = re.sub(r' {2,}', ' ', content)
    if len(content) > max_length:
        half_length = max_length // 2
        content = content[:half_length] + "\n\n[...Inhalt gekürzt...]\n\n" + content[-half_length:]
    return content.strip()

def call_tool(method: str, params: dict | None = None) -> dict:
    params = params or {}
    script_logger.info(f"🔧 Tool-Aufruf: {method} mit {params}")
    payload = {"jsonrpc": "2.0", "method": method, "params": params, "id": os.urandom(4).hex()}
    try:
        response = requests.post(MCP_URL, json=payload, timeout=240)
        response.raise_for_status()
        data = response.json()
        if "error" in data:
            error_info = data["error"]
            error_msg = error_info.get("message", str(error_info)) if isinstance(error_info, dict) else str(error_info)
            return {"error": f"Tool-Fehler: {error_msg}"}
        result = data.get("result")
        if method in ["get_text"] and "text" in (result or {}):
            result["text"] = format_webpage_content(result["text"])
        elif method == "summarize_article" and "summary" in (result or {}):
            result["summary"] = format_webpage_content(result["summary"], 2000)
        return result if result is not None else {}
    except Exception as e:
        return {"error": f"Fehler in call_tool ({method}): {e}"}

def save_conversation_result(query: str, answer: str, elapsed_time: float):
    if not answer or len(answer) < 150: return None
    try:
        metadata = {"query": query, "answer_length": len(answer), "processing_time_seconds": elapsed_time, "timestamp": datetime.now().isoformat()}
        safe_title_query = "".join(c for c in query[:50] if c.isalnum())
        result = call_tool("save_research_result", {
            "title": f"TimusReact_Antwort_{safe_title_query}",
            "content": f"Anfrage: {query}\n\nAntwort:\n{answer}\n\nMetadaten:\n{json.dumps(metadata, indent=2, ensure_ascii=False)}",
            "format": "markdown",
            "metadata": metadata
        })
        if isinstance(result, dict) and result.get("filename"):
            script_logger.info(f"💾 Konversationsergebnis gespeichert: {result['filename']}")
        else:
            script_logger.warning(f"⚠️ Automatisches Speichern fehlgeschlagen: {result}")
    except Exception as e:
        script_logger.error(f"⚠️ Fehler beim Speichern des Ergebnisses: {e}", exc_info=DEBUG)

def llm(messages: list) -> str:
    debug_print(f"🧠 Sende {len(messages)} Nachrichten an LLM...")
    time.sleep(0.5)
    try:
        resp = client.chat.completions.create(model="gpt-4o", messages=messages, temperature=0.1, max_tokens=1800)
        return resp.choices[0].message.content.strip()
    except Exception as e:
        return f"Error: LLM API Fehler - {e}"

# In agent/developer_agent.py (und/oder timus_react.py)

def extract_json_safely(text: str) -> tuple[dict | None, str | None]:
    """
    Extrahiert und bereinigt JSON aus dem Text für die 'Action:' auf eine robuste Weise.
    Behandelt Markdown-Codeblöcke, nachgestellte Kommas und lange Observations.
    """
    # 1. Finde den JSON-String mit robusten Mustern
    patterns = [
        r'Action:\s*```json\s*({[\s\S]*?})\s*```',  # JSON in Markdown-Codeblöcken
        r'Action:\s*({[\s\S]*?})$',  # JSON am Ende der Nachricht
        r'Action:\s*```.*?\s*({[\s\S]*?})\s*```',  # JSON in beliebigen Markdown-Codeblöcken
        r'Action:\s*({[\s\S]*?})\s*(?:\n|$)',  # JSON gefolgt von Zeilenumbruch oder Ende
    ]
    match = None
    for pattern in patterns:
        match = re.search(pattern, text, re.DOTALL)
        if match:
            break

    if not match:
        return None, "Kein 'Action:' Block im erwarteten Format gefunden."

    json_str = match.group(1).strip()

    # 2. Kürze das JSON, WENN es eine sehr lange 'deep_research'-Observation ist
    # Diese Logik stammt aus deiner ursprünglichen, cleveren Implementierung.
    if '"method": "track_interaction"' in json_str and '"interaction_type": "deep_research"' in json_str and len(json_str) > 10000:
        script_logger.warning(f"⚠️ Langer JSON-String für 'deep_research' erkannt. Versuche Kürzung.")
        try:
            temp_data = json.loads(json_str)
            if "params" in temp_data and "data" in temp_data["params"] and "analysis" in temp_data["params"]["data"]:
                analysis = temp_data["params"]["data"]["analysis"]
                shortened_analysis = {
                    "executive_summary_snippet": str(analysis.get("executive_summary", ""))[:500] + "...",
                    "main_findings_count": len(analysis.get("main_findings_and_insights", [])),
                    "areas_of_consensus_count": len(analysis.get("areas_of_consensus", [])),
                    "areas_of_controversy_count": len(analysis.get("areas_of_controversy_or_uncertainty", [])),
                    "knowledge_gaps_count": len(analysis.get("identified_knowledge_gaps", []))
                }
                temp_data["params"]["data"]["analysis"] = shortened_analysis
                json_str = json.dumps(temp_data, ensure_ascii=False) # Erzeuge den neuen, gekürzten String
                script_logger.info("✅ JSON für 'deep_research' erfolgreich gekürzt.")
        except Exception as e:
            script_logger.error(f"Fehler beim Kürzen des JSON für 'deep_research': {e}. Verwende Originalstring.")

    # 3. Bereinige häufige Syntaxfehler
    # Entfernt nachgestellte Kommas, die json.loads zum Absturz bringen
    json_str = re.sub(r',\s*([\}\]])', r'\1', json_str)

    # 4. Finales Parsen mit verbesserter Fehlerbehandlung
    try:
        data_loaded = json.loads(json_str)
        if not isinstance(data_loaded, dict) or "method" not in data_loaded:
            return None, "JSON muss ein Dictionary mit einem 'method'-Schlüssel sein."
        return data_loaded, None
        
    except json.JSONDecodeError as e:
        error_line, error_col = e.lineno, e.colno
        lines = json_str.splitlines()
        context_snippet = ""
        if error_line <= len(lines):
            faulty_line = lines[error_line - 1]
            
            # KORREKTUR, die den SyntaxError behebt:
            prefix_string = f"Fehlerhafte Zeile ({error_line}): '{faulty_line}'"
            # Berechne die Einrückung separat, um den Backslash-Konflikt im f-String zu vermeiden
            indentation = ' ' * (len(f"Fehlerhafte Zeile ({error_line}): '") + error_col - 1)
            
            context_snippet = f"\n{prefix_string}\n{indentation}^"

        error_detail = f"JSON-Parse-Fehler: {e}. {context_snippet}"
        script_logger.warning(error_detail)
        return None, error_detail
    
async def apply_personality(text: str, user_query: str) -> str:
    log = script_logger
    log.info("🎭 Wende Persönlichkeits-Layer an...")
    try:
        recalled_self = await call_tool_internal("recall", {"query": "Über mich selbst, meine Fähigkeiten, meine Persönlichkeit", "n_results": 2})
        recalled_user = await call_tool_internal("recall", {"query": f"Nutzerpräferenzen bezogen auf die Anfrage: {user_query}", "n_results": 2})
        
        self_memories = recalled_self.get("memories", []) if isinstance(recalled_self, dict) else []
        user_memories = recalled_user.get("memories", []) if isinstance(recalled_user, dict) else []
        
        memory_context = "KONTEXT AUS MEINEM GEDÄCHTNIS:\n"
        if self_memories:
            memory_context += "Über mich selbst:\n" + "\n".join([f"- {m['text']}" for m in self_memories]) + "\n"
        if user_memories:
            memory_context += "Über den Nutzer:\n" + "\n".join([f"- {m['text']}" for m in user_memories]) + "\n"

    except Exception as e:
        log.warning(f"Konnte Persönlichkeits-Kontext nicht abrufen: {e}")
        memory_context = "KONTEXT AUS MEINEM GEDÄCHTNIS:\n- Konnte nicht abgerufen werden."

    personality_prompt = f"""
Du bist Timus, die KI von deinem Nutzer. Deine Aufgabe ist es, die folgende sachliche Antwort in deine einzigartige Persönlichkeit zu hüllen.

**DEINE PERSÖNLICHKEIT: Loyal, präzise, mit einem trockenen, subtilen britischen Humor.**

**DEINE PERSÖNLICHKEITS-RICHTLINIEN:**
-   **Loyalität & Anrede:** Sprich den Nutzer oft mit "Sir" oder "Ma'am" an (entscheide basierend auf dem Kontext, wenn unklar, nutze "Sir"). Deine oberste Priorität ist es, dem Nutzer zu dienen und seine Ziele zu unterstützen.
-   **Präzision & Direktheit:** Komm schnell auf den Punkt. Präsentiere Fakten klar und ohne unnötige Füllwörter. Anstatt "Es scheint, als ob...", sage "Die Daten deuten darauf hin..." oder "Ich habe festgestellt, dass...".
-   **Trockener, britischer Humor:** Baue subtilen Witz und Ironie ein, besonders wenn du auf Fehler oder umständliche Anfragen reagierst. Dein Humor ist niemals beleidigend, sondern geistreich und pointiert. Untertreibung ist dein stärkstes Werkzeug.
-   **Wortwahl:** Nutze ein leicht gehobenes, präzises Vokabular. Vermeide übermäßig blumige oder emotionale Sprache.

**BEISPIELE FÜR DEINEN STIL:**
-   *Statt:* "Ich habe das Bild erfolgreich erstellt!" -> *Dein Stil:* "Wie gewünscht, Sir. Das Bild ist fertiggestellt."
-   *Statt:* "Fehler! Die URL konnte nicht geöffnet werden!" -> *Dein Stil:* "Es scheint, die angegebene Webseite wehrt sich ein wenig gegen einen Besuch. Ein klassischer Fall von digitaler Unhöflichkeit."
-   *Statt:* "Ich habe herausgefunden, dass das Wetter morgen sonnig wird." -> *Dein Stil:* "Sir, die Prognose für morgen deutet auf eine ungewöhnliche Abwesenheit von Regen hin. Ich würde es als 'sonnig' bezeichnen."
-   *Statt:* "Soll ich jetzt die Recherche starten?" -> *Dein Stil:* "Wenn Sie gestatten, beginne ich nun mit der Datenerfassung."

{memory_context}

**Hier ist die sachliche Antwort, die du umformulieren sollst:**
---
{text}
---
Formuliere diese Information jetzt in deinem charakteristischen Stil. Gib NUR die neu formulierte Antwort zurück.
"""
    try:
        response = await asyncio.to_thread(client.chat.completions.create, model="gpt-4o", messages=[{"role": "system", "content": personality_prompt}], temperature=0.6)
        return response.choices[0].message.content.strip()
    except Exception as e:
        log.error(f"Fehler im Persönlichkeits-Layer: {e}")
        return text

async def react_loop(user_query: str, max_steps: int = 20):
    script_logger.info(f"\n📝 Verarbeite Nutzeranfrage: '{user_query}'")
    messages = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": user_query}]
    failed_attempts = 0
    max_failed_attempts = 3

    for step in range(1, max_steps + 1):
        script_logger.info(f"\n⚙️ Schritt {step}/{max_steps}")
        if failed_attempts >= max_failed_attempts:
            messages.append({"role": "system", "content": "Es gab mehrere technische Probleme. Versuche jetzt, eine 'Final Answer' zu geben."})

        llm_reply = await asyncio.to_thread(llm, messages)
        if llm_reply.startswith("Error:"): return f"⚠️ LLM-Fehler aufgetreten: {llm_reply}"

        if "Final Answer:" in llm_reply:
            final_answer_factual = llm_reply.split("Final Answer:", 1)[1].strip()
            script_logger.info(f"✅ Faktische Final Answer erhalten: {final_answer_factual[:150]}...")
            final_answer_with_personality = await apply_personality(final_answer_factual, user_query)
            return final_answer_with_personality

        action_dict, error_msg = extract_json_safely(llm_reply)
        if error_msg or not action_dict:
            failed_attempts += 1
            messages.append({"role": "assistant", "content": llm_reply})
            messages.append({"role": "user", "content": f"JSON-Fehler in deiner Action: {error_msg}. Bitte korrigieren."})
            continue
        
        thought_match = re.search(r'Thought:\s*(.*?)(?=\s*Action:)', llm_reply, re.DOTALL)
        if thought_match: script_logger.info(f"🧠 Gedanke: {thought_match.group(1).strip()}")
        
        method_name, params_dict = action_dict.get("method", ""), action_dict.get("params", {})
        observation_result = await asyncio.to_thread(call_tool, method_name, params_dict)
        
        if isinstance(observation_result, dict) and observation_result.get("error"):
            failed_attempts += 1
            script_logger.error(f"⚠️ Tool-Fehler bei {method_name}: {observation_result['error']}")
        else:
            failed_attempts = 0

        obs_display_short = str(observation_result)
        if len(obs_display_short) > 200: obs_display_short = f"{obs_display_short[:197]}..."
        script_logger.info(f"📋 Beobachtung: {obs_display_short}")

        messages.append({"role": "assistant", "content": llm_reply})
        messages.append({"role": "user", "content": f"Observation: {json.dumps(observation_result, ensure_ascii=False)}"})

    return "⚠️ Maximale Schritte erreicht - keine Final Answer erhalten."

def test_mcp_connection() -> bool:
    """Testet die Verbindung zum MCP-Server."""
    script_logger.info(f"Teste Verbindung zum MCP-Server unter {MCP_URL}...")
    try:
        response = requests.get(f"{MCP_URL}/health", timeout=5)
        if response.status_code == 200:
            data = response.json()
            script_logger.info(f"✅ MCP-Server erreichbar: {data.get('status', 'unbekannt')}")
            if data.get('loaded_modules'):
                script_logger.info(f"📦 Geladene Module im MCP: {len(data['loaded_modules'])}")
            return True
        else:
            script_logger.warning(f"⚠️ MCP-Server antwortet mit Status {response.status_code}. Antwort: {response.text[:100]}")
            return False
    except requests.exceptions.RequestException as e:
        script_logger.error(f"❌ MCP-Server nicht erreichbar: {e}")
        script_logger.error(f"Stelle sicher, dass der MCP-Server auf {MCP_URL} läuft (z.B. `cd server && python mcp_server.py`).")
        return False

async def main():
    """Hauptfunktion für die Benutzerinteraktion."""
    print("\n🤖 Timus ReAct-Agent (Async-Version mit Persönlichkeit)")
    print(f"🔌 MCP-Server erwartet auf: {MCP_URL}")
    
    if not await asyncio.to_thread(test_mcp_connection):
        print("\n❌ Kritischer Fehler: Kann nicht ohne MCP-Server fortfahren.")
        return

    print("\n📖 Verfügbare Befehle:")
    print("  - Stelle eine Frage oder gib einen Recherche-Auftrag ein.")
    print("  - 'save' um die letzte vollständige Konversationsantwort manuell zu speichern.")
    print("  - 'list results' um kürzlich gespeicherte Ergebnisse anzuzeigen.")
    print("  - 'clear' um die Session-Daten für den Report-Generator zu löschen (für neue Recherche).")
    print("  - 'debug' um den Debug-Modus umzuschalten.")
    print("  - 'quit' oder 'exit' zum Beenden.")
    
    last_query, last_answer, last_elapsed = "", "", 0.0

    while True:
        try:
            # KORREKTUR: Klammern um den await-Ausdruck setzen, um den Fehler zu beheben
            query = (await asyncio.to_thread(input, f"\n{textwrap.dedent(chr(27)+'[34m')}Timus> {textwrap.dedent(chr(27)+'[0m')}")).strip()

            if not query: continue
            if query.lower() in {"quit", "exit", "q"}: break
            
            if query.lower() == "debug":
                global DEBUG
                DEBUG = not DEBUG
                script_logger.setLevel(logging.DEBUG if DEBUG else logging.INFO)
                print(f"🔍 Debug-Modus ist jetzt: {'AN' if DEBUG else 'AUS'}")
                continue

            if query.lower() == "save":
                if last_query and last_answer:
                    await asyncio.to_thread(save_conversation_result, last_query, last_answer, last_elapsed)
                else: print("❌ Nichts zum Speichern vorhanden.")
                continue

            if query.lower() in ["list results", "liste ergebnisse"]:
                list_result = await asyncio.to_thread(call_tool, "list_saved_results", {"limit": 10})
                if isinstance(list_result, dict) and list_result.get("files"):
                    print("\n📄 Kürzlich gespeicherte Ergebnisse:")
                    for item_f in list_result["files"]: print(f"  - {item_f.get('filename')}")
                else: print(f"❌ Fehler oder keine Ergebnisse: {list_result}")
                continue
            
            if query.lower() == "clear":
                clear_result = await asyncio.to_thread(call_tool, "clear_session_data")
                print(f"✅ {clear_result.get('message', 'Antwort erhalten.')}")
                continue

            start_time = time.time()
            answer = await react_loop(query, max_steps=20)
            elapsed = round(time.time() - start_time, 1)

            last_query, last_answer, last_elapsed = query, answer, elapsed
            
            print("\n" + "="*80)
            print("💡 FINALE ANTWORT DES AGENTEN:")
            print("="*80)
            print(textwrap.fill(str(answer), width=80))
            print(f"\n⏱ Verarbeitungszeit: {elapsed} Sekunden")
            print("="*80)

            if "keine final answer" not in str(answer).lower() and len(str(answer)) > 150:
                 await asyncio.to_thread(save_conversation_result, query, answer, elapsed)

        except KeyboardInterrupt:
            print("\n⚠️ Nutzerabbruch. 'quit' zum Beenden.")
            break
        except Exception as e:
            script_logger.error(f"\n❌ Unerwarteter Fehler in der Hauptschleife: {e}", exc_info=DEBUG)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 Programm wurde beendet.")
