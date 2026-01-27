# main_dispatcher.py (VERSION v3.2)
"""
Verbesserter Dispatcher mit Developer Agent v2 und ReasoningAgent Support.

v3.2 ÄNDERUNGEN (2026-01-27):
- Developer Agent v2 integriert (mit context_files Support)
- Intelligente Kontext-Dateien für bessere Code-Generierung
- Multi-Tool Support (9 Tools statt 1)
- Code-Validierung (AST, Style, Security)
- Fehler-Recovery Strategien

v3.1 ÄNDERUNGEN:
- ReasoningAgent hinzugefügt (Nemotron)
- Reasoning-Keywords für schnelle Erkennung
- Dispatcher-Prompt erweitert

AGENTEN-ÜBERSICHT:
- executor: Schnelle einfache Tasks (gpt-4o-mini)
- research: Tiefenrecherche (deepseek-reasoner)
- reasoning: Komplexe Analyse, Debugging, Architektur (Nemotron)
- creative: Bilder, kreative Texte (gpt-5.2)
- development: Code schreiben v2 (mercury-coder + context_files)
- meta: Planung, Orchestrierung (claude-sonnet)
- visual: UI-Steuerung (claude-sonnet)
"""

import os
import sys
import asyncio
import textwrap
import logging
from pathlib import Path
from typing import Optional

import httpx
from openai import OpenAI
from dotenv import load_dotenv

# --- Modulpfad-Korrektur ---
try:
    current_file_path = Path(__file__).resolve()
    project_root = current_file_path.parent
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))
except NameError:
    project_root = Path.cwd()
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))

# --- Imports ---
from agent.timus_consolidated import (
    ExecutorAgent,
    CreativeAgent,
    MetaAgent,
    DeepResearchAgent,
    ReasoningAgent  # NEU v3.1
)

# Developer Agent v2 (verbessert mit context_files Support)
from agent.developer_agent_v2 import DeveloperAgentV2

# QUICK FIX: Importiere den präzisen VisualAgent (mit SoM + Mouse Feedback)
from agent.visual_agent import run_visual_task as run_visual_task_precise

# --- Initialisierung ---
load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
logging.basicConfig(
    level=logging.INFO, 
    format='%(asctime)s | %(levelname)-7s | %(name)-20s | %(message)s'
)
log = logging.getLogger("MainDispatcher")

# --- System-Prompt (AKTUALISIERT v3.1) ---
DISPATCHER_PROMPT = """
Du bist der zentrale Dispatcher für Timus. Analysiere die INTENTION des Nutzers und wähle den richtigen Spezialisten.

### DIE AGENTEN

1. **reasoning**: Der DENKER & ANALYST (NEU - Nemotron)
   - Zuständigkeit: Komplexe Analyse, Multi-Step Reasoning, Debugging, Architektur-Entscheidungen
   - Wähle 'reasoning' bei:
     - "Warum funktioniert X nicht?" (Debugging)
     - "Vergleiche A vs B" (Trade-off Analyse)
     - "Was ist die beste Lösung für..." (Architektur)
     - "Erkläre Schritt für Schritt..." (Multi-Step)
     - "Pro und Contra von..." (Abwägung)
     - "Analysiere diesen Code/Fehler/Problem"
     - Komplexe technische Fragen die Nachdenken erfordern
     - "asyncio vs threading" - Vergleichsfragen!

2. **research**: Der FORSCHER
   - Zuständigkeit: Tiefenrecherche, Faktensammlung, Quellenanalyse
   - Wähle 'research' bei:
     - "Recherchiere aktuelle Entwicklungen zu X"
     - "Was gibt es Neues zu..."
     - "Sammle Fakten über Z"
     - Anfragen die EXTERNE Informationen/Quellen brauchen

3. **executor**: Der HELFER für einfache Aufgaben
   - Zuständigkeit: Schnelle Websuche, einfache Fragen, Zusammenfassungen
   - Wähle 'executor' bei:
     - "Wie spät ist es?"
     - "Was ist die Hauptstadt von..."
     - "Fasse diesen Text zusammen"
     - Einfache, schnelle Anfragen OHNE komplexe Analyse

4. **meta**: Der ARCHITEKT für Workflows
   - Zuständigkeit: Mehrstufige Aufgaben koordinieren, Workflows planen
   - Wähle 'meta' bei:
     - "Erstelle einen Plan für..."
     - "Zuerst X, dann Y, dann Z"
     - Komplexe mehrstufige Aufgaben

5. **visual**: Der OPERATOR (Maus & Tastatur)
   - Zuständigkeit: Computer steuern, Apps öffnen, UI-Automation
   - Wähle 'visual' bei:
     - "Öffne Firefox"
     - "Klicke auf..."
     - "Starte Programm X"

6. **development**: Der CODER
   - Zuständigkeit: Code schreiben, Skripte erstellen
   - Wähle 'development' bei:
     - "Schreibe ein Python-Skript"
     - "Erstelle eine Funktion für..."

7. **creative**: Der KÜNSTLER
   - Zuständigkeit: Bilder, Texte, kreative Inhalte
   - Wähle 'creative' bei:
     - "Male ein Bild von..."
     - "Schreibe ein Gedicht"

### WICHTIGE REGELN

1. Bei VERGLEICHSFRAGEN (A vs B, was ist besser, Unterschied zwischen) → 'reasoning'
2. Bei WARUM-FRAGEN (Debugging, Root-Cause) → 'reasoning'
3. Bei ARCHITEKTUR-FRAGEN (welche Technologie, Design-Entscheidungen) → 'reasoning'
4. Bei RECHERCHE nach externen Fakten/News → 'research'
5. Bei EINFACHEN Fragen ohne Analyse → 'executor'

Antworte NUR mit einem Wort: 'reasoning', 'research', 'executor', 'meta', 'visual', 'development' oder 'creative'.
"""

# --- Mapping (AKTUALISIERT v3.2 - Developer Agent v2) ---
AGENT_CLASS_MAP = {
    # Primäre Agenten
    "reasoning": ReasoningAgent,    # NEU v3.1
    "research": DeepResearchAgent,
    "executor": ExecutorAgent,
    "visual": "SPECIAL_VISUAL",     # QUICK FIX: Spezielle Behandlung
    "meta": MetaAgent,
    "development": DeveloperAgentV2,  # AKTUALISIERT v3.2: Developer Agent v2
    "creative": CreativeAgent,

    # Aliase
    "analyst": ReasoningAgent,      # NEU
    "debugger": ReasoningAgent,     # NEU
    "thinker": ReasoningAgent,      # NEU
    "deep_research": DeepResearchAgent,
    "researcher": DeepResearchAgent,
    "task_agent": ExecutorAgent,
    "visual_agent": "SPECIAL_VISUAL",  # QUICK FIX: Spezielle Behandlung
    "meta_agent": MetaAgent,
    "development_agent": DeveloperAgentV2,  # AKTUALISIERT v3.2
    "creative_agent": CreativeAgent,
    "architekt": MetaAgent,
    "coder": DeveloperAgentV2  # AKTUALISIERT v3.2
}

# Keywords für schnelle Erkennung (ohne LLM)
REASONING_KEYWORDS = [
    # Vergleiche
    "vs", "versus", "oder", "vergleiche", "vergleich", "unterschied zwischen",
    "was ist besser", "welches ist besser", "a oder b",
    # Debugging
    "warum", "wieso", "weshalb", "funktioniert nicht", "fehler", "bug",
    "problem mit", "geht nicht", "klappt nicht", "debugge", "debug",
    # Analyse
    "analysiere", "analyse", "erkläre schritt", "schritt für schritt",
    "pro und contra", "vor- und nachteile", "vorteile und nachteile",
    "trade-off", "tradeoff", "abwägung",
    # Architektur
    "soll ich", "sollte ich", "welche technologie", "welches framework",
    "architektur", "design entscheidung", "beste lösung", "best practice",
    # Reasoning-Trigger
    "denke nach", "überlege", "reasoning", "logik", "logisch"
]

RESEARCH_KEYWORDS = [
    "recherchiere", "recherche", "recherchier",
    "finde heraus", "fakten", "quellen",
    "tiefenrecherche", "deep research",
    "aktuelle entwicklungen", "neueste erkenntnisse",
    "sammle informationen", "informiere mich über",
    "was gibt es neues", "news zu", "nachrichten"
]

VISUAL_KEYWORDS = [
    "öffne", "starte", "klicke", "klick auf", "schließe",
    "minimiere", "maximiere", "screenshot", "bildschirm"
]

CREATIVE_KEYWORDS = [
    "male", "zeichne", "bild von", "generiere bild", "erstelle bild",
    "gedicht", "song", "lied", "geschichte schreiben", "kreativ"
]

DEVELOPMENT_KEYWORDS = [
    "schreibe code", "programmiere", "skript erstellen",
    "funktion schreiben", "klasse erstellen", "implementiere"
]

META_KEYWORDS = [
    "plane", "erstelle einen plan", "koordiniere",
    "automatisiere", "workflow", "mehrere schritte",
    "und dann", "danach", "anschließend", "als nächstes",
    "zuerst", "zum schluss", "abschließend"
]

EXECUTOR_KEYWORDS = [
    "ich heiße", "mein name", "ich bin", "ich mag",
    "was weißt du", "wer bin ich", "kennst du mich",
    "hallo", "hi ", "guten tag", "wie geht", "danke", "bitte",
    "wie spät", "uhrzeit", "datum", "wetter",
    "hauptstadt von", "was ist ein", "definiere"
]


def quick_intent_check(query: str) -> Optional[str]:
    """Schnelle Keyword-basierte Intent-Erkennung."""
    query_lower = query.lower()
    
    # REASONING zuerst prüfen (höchste Priorität für komplexe Fragen)
    for keyword in REASONING_KEYWORDS:
        if keyword in query_lower:
            return "reasoning"
    
    # META-Keywords (mehrstufige Aufgaben)
    for keyword in META_KEYWORDS:
        if keyword in query_lower:
            return "meta"
    
    # Research-Keywords
    for keyword in RESEARCH_KEYWORDS:
        if keyword in query_lower:
            return "research"
    
    # Visual-Keywords
    for keyword in VISUAL_KEYWORDS:
        if keyword in query_lower:
            return "visual"
    
    # Creative-Keywords
    for keyword in CREATIVE_KEYWORDS:
        if keyword in query_lower:
            return "creative"
    
    # Development-Keywords
    for keyword in DEVELOPMENT_KEYWORDS:
        if keyword in query_lower:
            return "development"
    
    # Executor-Keywords (einfache Fragen)
    for keyword in EXECUTOR_KEYWORDS:
        if keyword in query_lower:
            return "executor"
    
    return None  # LLM entscheiden lassen


async def get_agent_decision(user_query: str) -> str:
    """Bestimmt welcher Agent für die Anfrage zuständig ist."""
    log.info(f"🧠 Analysiere Intention: '{user_query}'")
    
    # Schnelle Keyword-Erkennung zuerst
    quick_result = quick_intent_check(user_query)
    if quick_result:
        log.info(f"✅ Schnell-Entscheidung (Keyword): {quick_result}")
        return quick_result
    
    # LLM-basierte Entscheidung
    try:
        response = await asyncio.to_thread(
            client.chat.completions.create,
            model="gpt-4o-mini",  # Schneller für Routing
            messages=[
                {"role": "system", "content": DISPATCHER_PROMPT},
                {"role": "user", "content": user_query},
            ],
            temperature=0,
            max_tokens=20
        )
        decision = response.choices[0].message.content.strip().lower().replace('.', '')
        
        # Direkter Treffer
        if decision in AGENT_CLASS_MAP:
            log.info(f"✅ Entscheidung: {decision}")
            return decision
        
        # Suche im Text
        for key in AGENT_CLASS_MAP.keys():
            if key in decision:
                log.info(f"✅ Entscheidung (extrahiert): {key}")
                return key
        
        log.warning(f"⚠️ Unsicher ({decision}). Fallback auf 'executor'.")
        return "executor"
        
    except Exception as e:
        log.error(f"❌ Dispatcher-Fehler: {e}")
        return "executor"


async def run_agent(agent_name: str, query: str, tools_description: str):
    """Instanziiert den Agenten und führt ihn aus."""
    AgentClass = AGENT_CLASS_MAP.get(agent_name)

    if not AgentClass:
        log.error(f"❌ Agent '{agent_name}' nicht gefunden.")
        return

    log.info(f"\n🚀 Starte Agent: {agent_name.upper()}")

    try:
        # QUICK FIX: Spezielle Behandlung für VisualAgent (nutzt präzisen standalone Agent)
        if AgentClass == "SPECIAL_VISUAL":
            log.info("👁️ Nutze präzisen VisualAgent v2.1 (SoM + Mouse Feedback)")
            final_answer = await run_visual_task_precise(query, max_iterations=30)

            print("\n" + "=" * 80)
            print(f"💡 FINALE ANTWORT ({agent_name.upper()}):")
            print("=" * 80)
            print(textwrap.fill(str(final_answer), width=80))
            print("=" * 80)
            return final_answer

        # Normale Agenten
        # ReasoningAgent braucht enable_thinking Parameter
        if agent_name == "reasoning":
            agent_instance = AgentClass(
                tools_description_string=tools_description,
                enable_thinking=True  # Nemotron Reasoning aktiviert
            )
        # DeveloperAgentV2 braucht dest_folder und max_steps
        elif agent_name == "development":
            agent_instance = AgentClass(
                tools_description_string=tools_description,
                dest_folder=".",  # Standard: aktuelles Verzeichnis
                max_steps=15      # Genug Steps für komplexe Tasks
            )
        else:
            agent_instance = AgentClass(tools_description_string=tools_description)

        final_answer = await agent_instance.run(query)

        print("\n" + "=" * 80)
        print(f"💡 FINALE ANTWORT ({agent_name.upper()}):")
        print("=" * 80)
        print(textwrap.fill(str(final_answer), width=80))
        print("=" * 80)
        return final_answer

    except Exception as e:
        import traceback
        log.error(f"❌ Fehler beim Ausführen des Agenten '{agent_name}': {e}")
        log.error(traceback.format_exc())
        return None


async def fetch_tool_descriptions_from_server() -> Optional[str]:
    """Holt die Tool-Liste vom Server."""
    server_url = "http://127.0.0.1:5000/get_tool_descriptions"
    
    try:
        async with httpx.AsyncClient() as http_client:
            response = await http_client.get(server_url, timeout=5.0)
            
            if response.status_code != 200:
                log.error(f"❌ Server antwortet mit Status {response.status_code}")
                return None
            
            return response.json().get("descriptions")
            
    except httpx.ConnectError:
        log.fatal(f"FATAL: Keine Verbindung zum Server ({server_url}).")
        log.fatal("Starte den MCP Server mit: python server/mcp_server.py")
        return None
    except Exception as e:
        log.error(f"❌ Fehler beim Abrufen der Tools: {e}")
        return None


async def main_loop():
    """Hauptschleife des Dispatchers."""
    print("\n" + "=" * 60)
    print("🤖 TIMUS MASTER DISPATCHER (v3.2 - Dev Agent v2) 🤖")
    print("=" * 60)
    
    tools_desc = await fetch_tool_descriptions_from_server()
    if not tools_desc:
        return
    
    print("\nBereit. Beispiele:")
    print("  • 'asyncio vs threading für 100 API-Calls?' → REASONING (Nemotron)")
    print("  • 'Recherchiere KI-Sicherheit' → RESEARCH")
    print("  • 'Öffne Firefox' → VISUAL")
    print("  • 'Wie spät ist es?' → EXECUTOR")
    print("\nTipp: 'exit' zum Beenden\n")
    
    while True:
        try:
            q = await asyncio.to_thread(input, "\n\033[32mDu> \033[0m")
            
            if not q.strip():
                continue
            
            if q.lower() in ["exit", "quit", "q"]:
                break
            
            print("   🤔 Timus denkt...")
            agent = await get_agent_decision(q.strip())
            print(f"   📌 Agent: {agent.upper()}")
            await run_agent(agent, q.strip(), tools_desc)
            
        except (KeyboardInterrupt, EOFError):
            break
        except Exception as e:
            log.error(f"Fehler: {e}")
    
    print("\n👋 Bye!")


if __name__ == "__main__":
    try:
        asyncio.run(main_loop())
    except KeyboardInterrupt:
        pass
