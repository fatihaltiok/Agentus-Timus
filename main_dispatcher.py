# main_dispatcher.py (VERSION v3.3)
"""
Verbesserter Dispatcher mit Developer Agent v2 und ReasoningAgent Support.

v3.3 ÄNDERUNGEN (2026-02):
- Lane-Manager Integration (Default serial, explicit parallel)
- Session-basierte Tool-Isolation
- Queue-Status Ueberwachung

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
- executor: Schnelle einfache Tasks (gpt-5-mini)
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
import uuid
from pathlib import Path
from typing import Optional

import httpx
from openai import OpenAI
from dotenv import load_dotenv
from utils.openai_compat import prepare_openai_params

from orchestration.lane_manager import lane_manager, LaneStatus
from tools.tool_registry_v2 import registry_v2

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
    ReasoningAgent,  # NEU v3.1
)

# Developer Agent v2 (verbessert mit context_files Support)
from agent.developer_agent_v2 import DeveloperAgentV2

# QUICK FIX: Importiere den präzisen VisualAgent (mit SoM + Mouse Feedback)
from agent.visual_agent import run_visual_task as run_visual_task_precise

# NEU: VisionExecutorAgent mit Qwen-VL für präzise Koordinaten
try:
    from agent.vision_executor_agent import run_vision_task

    VISION_QWEN_AVAILABLE = True
except ImportError:
    VISION_QWEN_AVAILABLE = False
    log.warning("⚠️ VisionExecutorAgent nicht verfügbar")

# VisualNemotronAgent v4 - Desktop Edition mit echten Maus-Tools
try:
    from agent.visual_nemotron_agent_v4 import run_desktop_task

    VISUAL_NEMOTRON_V4_AVAILABLE = True
except ImportError as e:
    VISUAL_NEMOTRON_V4_AVAILABLE = False

# --- Initialisierung ---
load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(name)-20s | %(message)s",
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

6. **vision_qwen**: Der PRÄZISE OPERATOR (Qwen2-VL lokal)
   - Zuständigkeit: Web-Automation mit PIXEL-GENAUEN Koordinaten
   - Wähle 'vision_qwen' bei einfachen Web-Automation Tasks

7. **visual_nemotron**: Der STRUKTURIERTE VISION AGENT (NEU - Nemotron + Qwen-VL)
   - Zuständigkeit: Komplexe Web-Automation mit Multi-Step Planung
   - Wähle 'visual_nemotron' bei:
     - "Starte Browser, gehe zu grok.com, akzeptiere Cookies, starte Chat"
     - "Mehrstufige Web-Automation mit Cookie-Bannern und Formularen"
     - "Suche auf Google, klicke Ergebnis, extrahiere Text"
     - Tasks die STRUKTURIERTE JSON-Aktionen + Vision brauchen
   - VORTEILE:
     - Nemotron generiert strikte JSON-Aktionen
     - Qwen2-VL (8-bit 7B) für Vision
     - Automatische Fallbacks (GPT-4 Vision bei OOM)
     - Robuste Fehlerbehandlung bei Seiten-Navigation

8. **development**: Der CODER
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
    "reasoning": ReasoningAgent,  # NEU v3.1
    "research": DeepResearchAgent,
    "executor": ExecutorAgent,
    "visual": "SPECIAL_VISION_QWEN",  # Nutzt Qwen-VL (statt altem Executor)
    "vision_qwen": "SPECIAL_VISION_QWEN",  # Qwen-VL basierter Vision Agent
    "visual_nemotron": "SPECIAL_VISUAL_NEMOTRON",  # NEU: Nemotron + Qwen-VL
    "meta": MetaAgent,
    "development": DeveloperAgentV2,  # AKTUALISIERT v3.2: Developer Agent v2
    "creative": CreativeAgent,
    # Aliase
    "analyst": ReasoningAgent,  # NEU
    "debugger": ReasoningAgent,  # NEU
    "thinker": ReasoningAgent,  # NEU
    "deep_research": DeepResearchAgent,
    "researcher": DeepResearchAgent,
    "vision": "SPECIAL_VISION_QWEN",  # Alias für vision_qwen
    "qwen": "SPECIAL_VISION_QWEN",  # Kurzform
    "visual_nemotron": "SPECIAL_VISUAL_NEMOTRON",
    "nemotron_vision": "SPECIAL_VISUAL_NEMOTRON",
    "web_automation": "SPECIAL_VISUAL_NEMOTRON",
    "task_agent": ExecutorAgent,
    "visual_agent": "SPECIAL_VISUAL",  # QUICK FIX: Spezielle Behandlung
    "meta_agent": MetaAgent,
    "development_agent": DeveloperAgentV2,  # AKTUALISIERT v3.2
    "creative_agent": CreativeAgent,
    "architekt": MetaAgent,
    "coder": DeveloperAgentV2,  # AKTUALISIERT v3.2
}

# Keywords für schnelle Erkennung (ohne LLM)
REASONING_KEYWORDS = [
    # Vergleiche
    "vs",
    "versus",
    "oder",
    "vergleiche",
    "vergleich",
    "unterschied zwischen",
    "was ist besser",
    "welches ist besser",
    "a oder b",
    # Debugging
    "warum",
    "wieso",
    "weshalb",
    "funktioniert nicht",
    "fehler",
    "bug",
    "problem mit",
    "geht nicht",
    "klappt nicht",
    "debugge",
    "debug",
    # Analyse
    "analysiere",
    "analyse",
    "erkläre schritt",
    "schritt für schritt",
    "pro und contra",
    "vor- und nachteile",
    "vorteile und nachteile",
    "trade-off",
    "tradeoff",
    "abwägung",
    # Architektur
    "soll ich",
    "sollte ich",
    "welche technologie",
    "welches framework",
    "architektur",
    "design entscheidung",
    "beste lösung",
    "best practice",
    # Reasoning-Trigger
    "denke nach",
    "überlege",
    "reasoning",
    "logik",
    "logisch",
]

RESEARCH_KEYWORDS = [
    "recherchiere",
    "recherche",
    "recherchier",
    "finde heraus",
    "fakten",
    "quellen",
    "tiefenrecherche",
    "deep research",
    "aktuelle entwicklungen",
    "neueste erkenntnisse",
    "sammle informationen",
    "informiere mich über",
    "was gibt es neues",
    "news zu",
    "nachrichten",
]

VISUAL_KEYWORDS = [
    "öffne",
    "starte",
    "klicke",
    "klick auf",
    "schließe",
    "minimiere",
    "maximiere",
    "screenshot",
    "bildschirm",
]

# NEU: Keywords für VisualNemotronAgent (Multi-Step Web-Automation)
VISUAL_NEMOTRON_KEYWORDS = [
    # Multi-Step Sequenzen
    "und dann",
    "dann",
    "danach",
    "anschließend",
    "zuerst",
    "zuerst...dann",
    "schritt für schritt",
    # Web-Automation mit Cookies/Formularen
    "cookie",
    "cookies akzeptieren",
    "cookie banner",
    "formular",
    "login",
    "anmelden",
    "eingeben und absenden",
    "suche nach...und klicke",
    "gehe zu...und dann",
    # Komplexe Navigation
    "starte browser",
    "browser starten",
    "gehe zu webseite",
    "öffne webseite",
    "navigiere zu",
    "chat starten",
    "unterhaltung",
    "nachricht senden",
    "warte auf antwort",
]

CREATIVE_KEYWORDS = [
    "male",
    "zeichne",
    "bild von",
    "generiere bild",
    "erstelle bild",
    "gedicht",
    "song",
    "lied",
    "geschichte schreiben",
    "kreativ",
]

DEVELOPMENT_KEYWORDS = [
    "schreibe code",
    "programmiere",
    "skript erstellen",
    "funktion schreiben",
    "klasse erstellen",
    "implementiere",
]

META_KEYWORDS = [
    "plane",
    "erstelle einen plan",
    "koordiniere",
    "automatisiere",
    "workflow",
    "mehrere schritte",
    "und dann",
    "danach",
    "anschließend",
    "als nächstes",
    "zuerst",
    "zum schluss",
    "abschließend",
]

EXECUTOR_KEYWORDS = [
    "ich heiße",
    "mein name",
    "ich bin",
    "ich mag",
    "was weißt du",
    "wer bin ich",
    "kennst du mich",
    "hallo",
    "hi ",
    "guten tag",
    "wie geht",
    "danke",
    "bitte",
    "wie spät",
    "uhrzeit",
    "datum",
    "wetter",
    "hauptstadt von",
    "was ist ein",
    "definiere",
]


def _structure_task(task: str, url: str) -> str:
    """
    Wandelt komplexe natürlichsprachige Anfragen in strukturierte Tasks um.

    Beispiele:
    - "starte browser und gehe zu amazon.de und schau nach grafikkarten"
      → "1. Navigiere zu amazon.de\n2. Akzeptiere Cookies falls vorhanden\n3. Suche nach 'grafikkarten'\n4. Extrahiere Ergebnisse"
    """
    import re

    task_lower = task.lower()
    structured_steps = []
    step_num = 1

    # Extrahiere Aktionen aus dem Task
    actions_map = {
        r"\b(?:starte|öffne)\s+(?:den\s+)?browser\b": "browser_start",
        r"\bgehe\s+(?:zu|auf)\b": "navigate",
        r"\bschau\s+(?:nach|auf)\b": "search",
        r"\bsuche\s+(?:nach)?\b": "search",
        r"\bfinde\b": "search",
        r"\bzeige\s+(?:mir)?\b": "extract",
        r"\bextrahiere\b": "extract",
        r"\bklicke\s+(?:auf)?\b": "click",
        r"\bfülle\s+(?:aus)?\b": "fill",
        r"\bgib\s+(?:ein)?\b": "type",
        r"\b(?:akzeptiere|schließe)\s+(?:cookies?|banner)\b": "handle_cookies",
        r"\bwarte\b": "wait",
        r"\bund\s+dann\b": "next_step",
        r"\bdanach\b": "next_step",
        r"\banschließend\b": "next_step",
    }

    # Analysiere den Task
    found_actions = []
    for pattern, action_type in actions_map.items():
        matches = list(re.finditer(pattern, task_lower))
        for match in matches:
            found_actions.append((match.start(), action_type, match.group()))

    # Sortiere nach Position
    found_actions.sort(key=lambda x: x[0])

    # Wenn keine spezifischen Aktionen gefunden, nutze generischen Plan
    if not found_actions:
        return f"1. Navigiere zu {url}\n2. Analysiere Seite\n3. Führe aus: {task}"

    # Baue strukturierten Task
    # Immer als erstes: Navigation
    if url:
        domain = url.replace("https://", "").replace("http://", "").split("/")[0]
        structured_steps.append(f"{step_num}. Navigiere zu {domain}")
        step_num += 1
        structured_steps.append(
            f"{step_num}. Warte auf Seitenladung und akzeptiere Cookies falls nötig"
        )
        step_num += 1

    # Füge gefundene Aktionen hinzu
    for _, action_type, original in found_actions:
        if action_type == "search":
            # Extrahiere Suchbegriff (alles nach "suche nach" oder "schau nach")
            search_terms = re.findall(
                r"(?:suche nach|schau nach|finde)\s+([\w\s]+?)(?:\s+und|\s+auf|\s+von|\s+bei|$)",
                task_lower,
            )
            if search_terms:
                term = search_terms[0].strip()
                structured_steps.append(
                    f"{step_num}. Suche nach '{term}' in das Suchfeld"
                )
                step_num += 1
                structured_steps.append(f"{step_num}. Drücke Enter um Suche zu starten")
                step_num += 1
                structured_steps.append(f"{step_num}. Warte auf Ergebnisse")
                step_num += 1

        elif action_type == "extract" or action_type == "click":
            # Extrahiere Ziel
            targets = re.findall(
                r"(?:zeige|extrahiere|klicke auf)\s+([\w\s]+?)(?:\s+und|\s+dann|$)",
                task_lower,
            )
            if targets:
                target = targets[0].strip()
                if "erste" in target or "ersten" in target or "top" in target:
                    structured_steps.append(
                        f"{step_num}. Extrahiere die ersten 3 Ergebnisse"
                    )
                else:
                    structured_steps.append(f"{step_num}. Interagiere mit: {target}")
                step_num += 1

    # Abschluss
    structured_steps.append(f"{step_num}. Beende Task und berichte Ergebnisse")

    return "\n".join(structured_steps)


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

    # VisualNemotron-Keywords (Multi-Step Web-Automation)
    for keyword in VISUAL_NEMOTRON_KEYWORDS:
        if keyword in query_lower:
            return "visual_nemotron"

    # Visual-Keywords (einfache UI-Tasks)
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
        model = os.getenv("DISPATCHER_MODEL", "gpt-5-mini-2025-08-07")

        # Nutze Compatibility Helper für automatische API-Anpassung
        api_params = prepare_openai_params(
            {
                "model": model,
                "messages": [
                    {"role": "system", "content": DISPATCHER_PROMPT},
                    {"role": "user", "content": user_query},
                ],
                "temperature": 0,
                "max_tokens": 20,
            }
        )

        response = await asyncio.to_thread(client.chat.completions.create, **api_params)
        decision = response.choices[0].message.content.strip().lower().replace(".", "")

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


async def run_agent(
    agent_name: str, query: str, tools_description: str, session_id: str = None
):
    """Instanziiert den Agenten und führt ihn aus."""
    from utils.audit_logger import AuditLogger
    from utils.policy_gate import check_query_policy, audit_tool_call

    audit = AuditLogger()
    audit.log_start(query, agent_name)
    audit_tool_call("dispatcher_start", {"agent": agent_name, "query": query[:100]})

    effective_session_id = session_id or str(uuid.uuid4())[:8]

    lane_manager.set_registry(registry_v2)
    lane = await lane_manager.get_or_create_lane(effective_session_id)
    log.info(f"Lane {effective_session_id} status: {lane.status.value}")

    AgentClass = AGENT_CLASS_MAP.get(agent_name)

    if not AgentClass:
        log.error(f"❌ Agent '{agent_name}' nicht gefunden.")
        audit.log_end("Agent nicht gefunden", "error")
        return

    # Policy Gate: Destruktive Anfragen pruefen
    safe, warning = check_query_policy(query)
    if not safe:
        log.warning(f"[policy] {warning}")
        print(f"\n⚠️  {warning}")
        try:
            confirm = await asyncio.to_thread(input, "Fortfahren? (ja/nein): ")
            if confirm.strip().lower() not in ["ja", "j", "yes", "y"]:
                audit.log_end(f"Abgebrochen: {warning}", "cancelled")
                return f"Abgebrochen: {warning}"
        except Exception:
            pass  # Non-interactive: weitermachen

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
            audit.log_end(str(final_answer)[:200], "completed")
            return final_answer

        # NEU: Spezielle Behandlung für Vision Qwen Agent - NUTZT MCP-TOOL!
        if AgentClass == "SPECIAL_VISION_QWEN":
            log.info("🎯 Nutze Qwen-VL via MCP-Server Tool (kein neuer Prozess!)")
            log.info("   Vorteile: Nutzt bereits geladenes Modell, kein Doppel-Laden")

            # ═══════════════════════════════════════════════════════════════════
            # NEU: Meta-Agent Planung vor Visual-Ausführung
            # ═══════════════════════════════════════════════════════════════════
            log.info("🧠 Meta-Agent: Erstelle strukturierten Plan...")

            try:
                meta_agent = MetaAgent(tools_description)
                visual_plan = await meta_agent.create_visual_plan(query)

                log.info(f"✅ Plan erstellt: {visual_plan.get('goal', 'N/A')}")
                log.info(f"   URL: {visual_plan.get('url', 'N/A')}")
                log.info(f"   Schritte: {len(visual_plan.get('steps', []))}")

                # Zeige Plan in UI
                print("\n" + "─" * 60)
                print("📋 META-AGENT PLAN:")
                print("─" * 60)
                for step in visual_plan.get('steps', []):
                    print(f"  {step.get('step_number')}. {step.get('action').upper()}: {step.get('description')}")
                    if step.get('verification'):
                        print(f"     ✓ Verify: {step.get('verification')}")
                print("─" * 60)

                # Nutze geplante URL falls vorhanden
                url = visual_plan.get('url')
                task = visual_plan.get('goal', query)

            except Exception as e:
                log.warning(f"⚠️ Meta-Agent Planung fehlgeschlagen: {e}, nutze Fallback")
                # Fallback: Manuelle URL-Extraktion
                import re
                url_match = re.search(r"https?://[^\s]+", query)
                domain_match = re.search(r"([a-zA-Z0-9.-]+\.(de|com|org|net|io))", query)
                url = url_match.group(0) if url_match else (
                    f"https://{domain_match.group(1)}" if domain_match else "https://www.google.com"
                )
                task = query
                visual_plan = None

            if not url:
                log.warning("⚠️ Keine URL gefunden, verwende google.com als Default")
                url = "https://www.google.com"

            log.info(f"   URL: {url}")
            log.info(f"   Task: {task[:50]}{'...' if len(task) > 50 else ''}")

            # ═══════════════════════════════════════════════════════════════════
            # Erweitere Task um Plan-Kontext (falls Plan vorhanden)
            # ═══════════════════════════════════════════════════════════════════
            enhanced_task = task
            if visual_plan and visual_plan.get('steps'):
                import json
                plan_context = f"""
FOLGE DIESEM PLAN SCHLITT FÜR SCHLITT:
"""
                for step in visual_plan.get('steps', []):
                    plan_context += f"""
Schritt {step.get('step_number')}: {step.get('action').upper()}
- Beschreibung: {step.get('description')}
- Überprüfung: {step.get('verification')}
- Fallback: {step.get('fallback')}
"""
                plan_context += f"""
ZIEL: {visual_plan.get('goal')}
ERFOLGSKRITERIEN: {', '.join(visual_plan.get('success_criteria', []))}
"""
                enhanced_task = task + plan_context
                log.info(f"   Task erweitert mit Plan-Kontext ({len(plan_context)} chars)")

            # WICHTIG: Nutze MCP-Tool statt neuen Prozess!
            try:
                import httpx

                async with httpx.AsyncClient() as client:
                    response = await client.post(
                        "http://localhost:5000",
                        json={
                            "jsonrpc": "2.0",
                            "method": "qwen_web_automation",
                            "params": {
                                "url": url,
                                "task": enhanced_task,
                                "headless": False,
                                "max_iterations": 15,
                                "wait_between_actions": 2.0,
                            },
                            "id": 1,
                        },
                        timeout=300.0,  # 5 Minuten Timeout für komplexe Tasks
                    )
                    result = response.json()

                    if "result" in result:
                        r = result["result"]
                        success = r.get("success", False)
                        steps = r.get("steps", [])
                        final_url = r.get("final_url", "")

                        final_answer = f"""🎯 Vision Qwen Automation Ergebnis (via MCP):

Status: {"✅ ERFOLGREICH" if success else "❌ NICHT VOLLSTÄNDIG"}
URL: {final_url}
Schritte: {len(steps)}

Durchgeführte Aktionen:
"""
                        for i, step in enumerate(steps, 1):
                            actions_str = ", ".join(
                                [
                                    f"{a.get('action')}({a.get('x', '')},{a.get('y', '')})"
                                    if a.get("x")
                                    else a.get("action")
                                    for a in step.get("actions", [])
                                ]
                            )
                            final_answer += f"  {i}. {actions_str[:60]}{'...' if len(actions_str) > 60 else ''}\n"

                        print("\n" + "=" * 80)
                        print(f"💡 FINALE ANTWORT ({agent_name.upper()}):")
                        print("=" * 80)
                        print(final_answer)
                        print("=" * 80)
                        audit.log_end(str(final_answer)[:200], "completed")
                        return final_answer
                    else:
                        error_msg = result.get("error", {}).get(
                            "message", "Unbekannter Fehler"
                        )
                        log.error(f"❌ MCP Tool Fehler: {error_msg}")
                        audit.log_end(error_msg, "error")
                        return f"Fehler: {error_msg}"

            except Exception as e:
                log.error(f"❌ Fehler beim MCP-Tool Aufruf: {e}")
                audit.log_end(str(e), "error")
                return f"Fehler: {e}"

        # VisualNemotronAgent v4 für Desktop-Automatisierung (mit echten Maus-Tools)
        if AgentClass == "SPECIAL_VISUAL_NEMOTRON":
            if not VISUAL_NEMOTRON_V4_AVAILABLE:
                log.error("❌ VisualNemotronAgent v4 nicht verfügbar")
                audit.log_end("VisualNemotronAgent v4 nicht verfügbar", "error")
                return "Fehler: VisualNemotronAgent v4 nicht verfügbar"

            log.info("🎯 Nutze VisualNemotronAgent v4 (Desktop Edition)")
            log.info("   Features: PyAutoGUI | SoM UI-Scan | Echte Maus-Klicks")

            # Extrahiere URL und Task
            import re

            url = None
            task = query

            url_match = re.search(r"https?://[^\s]+", query)
            if url_match:
                url = url_match.group(0)
                task = query.replace(url, "").strip()
            else:
                domain_match = re.search(
                    r"([a-zA-Z0-9.-]+\.(de|com|org|net|io|ai))", query
                )
                if domain_match:
                    url = f"https://{domain_match.group(1)}"
                    task = query.replace(domain_match.group(1), "").strip()

            if not url:
                log.warning("⚠️ Keine URL gefunden, verwende google.com als Default")
                url = "https://www.google.com"

            structured_task = _structure_task(task, url)

            log.info(f"   URL: {url}")
            log.info(
                f"   Task: {structured_task[:80]}{'...' if len(structured_task) > 80 else ''}"
            )

            try:
                log.info("   🚀 Starte v4 (Desktop Edition mit PyAutoGUI)")
                result = await run_desktop_task(
                    task=structured_task, url=url if url else None, max_steps=15
                )
                version = "v4"

                success = result.get("success", False)
                steps_executed = result.get("steps_executed", result.get("steps", 0))
                steps_planned = result.get("total_steps_planned", 0)
                unique_states = result.get("unique_states", 0)
                error = result.get("error")

                final_answer = f"""🎯 Visual Nemotron Automation {version} Ergebnis:

Status: {"✅ ERFOLGREICH" if success else "❌ FEHLER" if error else "⚠️ UNVOLLSTÄNDIG"}
Schritte: {steps_executed} ausgeführt{f" ({steps_planned} geplant)" if steps_planned else ""}
Unique States: {unique_states if unique_states else "N/A"} (Loop-Erkennung)
"""
                if error:
                    final_answer += f"\nFehler: {error}\n"

                # Zeige durchgeführte Aktionen
                results = result.get("results", result.get("history", []))
                if results:
                    final_answer += "\nDurchgeführte Aktionen:\n"
                    for r in results[:10]:  # Max 10 Schritte anzeigen
                        if isinstance(r, dict):
                            act = r.get("action", {})
                            if isinstance(act, dict):
                                act_type = act.get("action", "unknown")
                                target = (
                                    act.get("target", {}).get("description", "")
                                    if isinstance(act.get("target"), dict)
                                    else ""
                                )
                            else:
                                act_type = str(act)
                                target = ""
                            status = "✅" if r.get("success") else "❌"
                            final_answer += f"  {status} {act_type} → {target[:30]}\n"

                print("\n" + "=" * 80)
                print(f"💡 FINALE ANTWORT ({agent_name.upper()}):")
                print("=" * 80)
                print(final_answer)
                print("=" * 80)
                audit.log_end(str(final_answer)[:200], "completed")
                return final_answer

            except Exception as e:
                log.error(f"❌ VisualNemotronAgent Fehler: {e}")
                import traceback

                log.error(traceback.format_exc())
                audit.log_end(str(e), "error")
                return f"Fehler bei Visual Automation: {e}"

        # Normale Agenten
        # ReasoningAgent braucht enable_thinking Parameter
        if agent_name == "reasoning":
            agent_instance = AgentClass(
                tools_description_string=tools_description,
                enable_thinking=True,  # Nemotron Reasoning aktiviert
            )
        # DeveloperAgentV2 braucht dest_folder und max_steps
        elif agent_name == "development":
            agent_instance = AgentClass(
                tools_description_string=tools_description,
                dest_folder=".",  # Standard: aktuelles Verzeichnis
                max_steps=15,  # Genug Steps für komplexe Tasks
            )
        else:
            agent_instance = AgentClass(tools_description_string=tools_description)

        final_answer = await agent_instance.run(query)

        print("\n" + "=" * 80)
        print(f"💡 FINALE ANTWORT ({agent_name.upper()}):")
        print("=" * 80)
        print(textwrap.fill(str(final_answer), width=80))
        print("=" * 80)
        audit.log_end(str(final_answer)[:200], "completed")
        return final_answer

    except Exception as e:
        import traceback

        log.error(f"❌ Fehler beim Ausführen des Agenten '{agent_name}': {e}")
        log.error(traceback.format_exc())
        audit.log_end(str(e), "error")
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
