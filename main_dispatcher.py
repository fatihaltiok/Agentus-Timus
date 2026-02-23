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
- image: Bild-Analyse (qwen3.5-plus, OpenRouter)
"""

import os
import sys
import re
import asyncio
import textwrap
import logging
import uuid
from pathlib import Path
from typing import Optional, List

import httpx
from openai import OpenAI
from dotenv import load_dotenv
from utils.openai_compat import prepare_openai_params

from orchestration.lane_manager import lane_manager, LaneStatus
from tools.tool_registry_v2 import registry_v2

# Logger frueh definieren, damit Import-Fallbacks sicher loggen koennen.
log = logging.getLogger("MainDispatcher")

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

# WICHTIG: .env frueh laden, bevor Agent-Module ihre Clients/Konstanten initialisieren.
load_dotenv(dotenv_path=project_root / ".env", override=True)

# --- Imports ---
from agent.timus_consolidated import (
    ExecutorAgent,
    CreativeAgent,
    MetaAgent,
    DeepResearchAgent,
    ReasoningAgent,  # NEU v3.1
)

# M1: neue Agenten
from agent.agents.data     import DataAgent
from agent.agents.document import DocumentAgent
# M2: neue Agenten
from agent.agents.communication import CommunicationAgent
# M3: neue Agenten
from agent.agents.system import SystemAgent
# M4: neue Agenten
from agent.agents.shell import ShellAgent
# M5: Bild-Analyse
from agent.agents.image import ImageAgent

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
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(name)-20s | %(message)s",
)


def _emit_dispatcher_status(agent_name: str, phase: str, detail: str = "") -> None:
    """Kompakte Live-Statusanzeige fuer Dispatcher/Spezialpfade."""
    enabled = os.getenv("TIMUS_LIVE_STATUS", "true").lower() in {"1", "true", "yes", "on"}
    if not enabled:
        return
    detail_txt = f" | {detail}" if detail else ""
    print(f"   ⏱️ Status | Agent {agent_name.upper()} | {phase.upper()}{detail_txt}")


def _sanitize_user_query(query: str) -> str:
    """Entfernt Steuerzeichen aus User-Input (z.B. ^V / \\x16)."""
    cleaned = re.sub(r"[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]", " ", str(query or ""))
    return re.sub(r"\s+", " ", cleaned).strip()

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

9. **data**: Der DATENANALYST
   - Zuständigkeit: CSV/XLSX/JSON einlesen, Statistiken berechnen, Tabellen/Berichte erstellen
   - Wähle 'data' bei:
     - "Analysiere diese CSV-Datei"
     - "Berechne die Summe / den Durchschnitt"
     - "Was sind meine größten Ausgaben?"
     - "Erstelle eine Statistik aus den Daten"
     - "Werte diese Excel-Tabelle aus"
     - Wenn eine Datei (CSV, XLSX, JSON) ausgewertet werden soll

11. **communication**: Der KOMMUNIKATIONS-SPEZIALIST
    - Zustaendigkeit: E-Mails, Briefe, LinkedIn-Posts, Anschreiben, Follow-ups
    - Wähle 'communication' bei:
      - "Schreib eine E-Mail an..."
      - "Formuliere eine Anfrage / ein Anschreiben"
      - "Erstelle einen LinkedIn-Post"
      - "Schreib ein Follow-up"
      - "Wie antworte ich auf..."
      - "Verfasse einen Brief"
      - Wenn ein kommunikativer Text in bestimmtem Ton gewuenscht wird

10. **document**: Der DOKUMENTEN-SPEZIALIST
    - Zuständigkeit: Professionelle Dokumente erstellen (Angebote, Berichte, Briefe, Lebensläufe)
    - Wähle 'document' bei:
      - "Erstelle ein Angebot für..."
      - "Schreib einen Bericht über..."
      - "Erstelle ein Protokoll"
      - "Mach einen Lebenslauf / eine Bewerbung"
      - "Erstelle ein PDF / Word-Dokument"
      - Wenn ein strukturiertes, professionelles Dokument gewünscht wird

12. **system**: Der SYSTEM-MONITOR
    - Zustaendigkeit: Log-Analyse, Prozesse, CPU/RAM, systemd-Services — NUR LESEN
    - Wähle 'system' bei:
      - "Was ist im Timus-Log?"
      - "Zeig mir alle Errors der letzten 24 Stunden"
      - "Wie viel CPU/RAM verbraucht der Server?"
      - "Ist der timus.service aktiv?"
      - "Welche Python-Prozesse laufen?"
      - "Was ist gestern Nacht abgestuerzt?"
      - "Diagnose", "Systemstatus", "Log pruefen", "Service-Status"
      - NICHT bei: "starte den Service" (→ shell), "repariere den Code" (→ development)

13. **shell**: Der SHELL-OPERATOR
    - Zustaendigkeit: Bash-Befehle ausfuehren, Skripte starten, Cron-Jobs verwalten
    - Wähle 'shell' ТОЛЬКО bei EXPLIZITEN Ausfuehrungs-Anfragen:
      - "Fuehre diesen Befehl aus: ..."
      - "Starte das Skript results/backup.py"
      - "Lege einen Cron-Job an der taeglich um 08:00 laeuft"
      - "Fuehre im Terminal aus..."
      - "Zeig mir die Cron-Jobs"
      - "Starte den timus-Service neu" (mit systemctl)
    - NICHT bei: "Lies die Datei" (→ executor), "Was laeuft?" (→ system),
                 "Schreib ein Skript" (→ development)
    - WICHTIG: shell ist der maechtigste Agent — nur bei klarer Ausfuehrungs-Intention

14. **image**: Der BILD-ANALYST
    - Zustaendigkeit: Hochgeladene Bilder analysieren und beschreiben
    - Wähle 'image' bei:
      - "Analysiere die hochgeladene Datei: ...jpg/jpeg/png/webp..."
      - "Was zeigt dieses Bild?"
      - "Beschreibe das Foto"
      - "Was steht auf dem Screenshot?"
      - Wenn der Nutzer explizit ein VORHANDENES Bild analysieren will
      - NICHT bei Speicherpfaden wie "speichere als /pfad/datei.png" — das ist kein vorhandenes Bild

### WICHTIGE REGELN

1. Bei VERGLEICHSFRAGEN (A vs B, was ist besser, Unterschied zwischen) → 'reasoning'
2. Bei WARUM-FRAGEN (Debugging, Root-Cause) → 'reasoning'
3. Bei ARCHITEKTUR-FRAGEN (welche Technologie, Design-Entscheidungen) → 'reasoning'
4. Bei RECHERCHE nach externen Fakten/News → 'research'
5. Bei EINFACHEN Fragen ohne Analyse → 'executor'
6. Bei BILDPFADEN nur 'image' wenn das Bild ANALYSIERT werden soll, NICHT bei Speicher-/Ausgabepfaden

Antworte NUR mit einem Wort: 'reasoning', 'research', 'executor', 'meta', 'visual', 'development', 'creative', 'data', 'document', 'communication', 'system', 'shell' oder 'image'.
"""

# --- Mapping (AKTUALISIERT v3.2 - Developer Agent v2) ---
AGENT_CLASS_MAP = {
    # Primäre Agenten
    "reasoning": ReasoningAgent,  # NEU v3.1
    "research": DeepResearchAgent,
    "executor": ExecutorAgent,
    "visual": "SPECIAL_VISUAL_NEMOTRON",  # Florence-2 + Nemotron
    "vision_qwen": "SPECIAL_VISUAL_NEMOTRON",  # Florence-2 + Nemotron (ehem. Qwen-VL)
    "visual_nemotron": "SPECIAL_VISUAL_NEMOTRON",  # Florence-2 + Nemotron
    "meta": MetaAgent,
    "development": DeveloperAgentV2,  # AKTUALISIERT v3.2: Developer Agent v2
    "creative": CreativeAgent,
    # M1: neue Agenten
    "data":     DataAgent,
    "document": DocumentAgent,
    # M2: neue Agenten
    "communication": CommunicationAgent,
    "email":         CommunicationAgent,  # Alias
    "komm":          CommunicationAgent,  # Alias
    # M3: neue Agenten
    "system":        SystemAgent,
    "sysmon":        SystemAgent,         # Alias
    "log":           SystemAgent,         # Alias
    # M4: neue Agenten
    "shell":         ShellAgent,
    "terminal":      ShellAgent,          # Alias
    "bash":          ShellAgent,          # Alias
    # M5: Bild-Analyse
    "image":         ImageAgent,
    "bild":          ImageAgent,          # Alias
    "foto":          ImageAgent,          # Alias
    # Aliase
    "analyst": ReasoningAgent,  # NEU
    "debugger": ReasoningAgent,  # NEU
    "thinker": ReasoningAgent,  # NEU
    "deep_research": DeepResearchAgent,
    "researcher": DeepResearchAgent,
    "vision": "SPECIAL_VISUAL_NEMOTRON",  # Florence-2 + Nemotron
    "qwen": "SPECIAL_VISUAL_NEMOTRON",  # ehem. Qwen-VL, jetzt Florence-2
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
    # Compound-Intents: Recherche + Bild / mehrstufig
    "coverbild",
    "cover bild",
    "und erstelle",
    "dann erstelle",
    "bild dazu",
    "illustration dazu",
    "infos und",
    "informationen und",
    "recherchiere und",
    "hole mir informationen",
    "hole informationen",
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
    "vorhin",
    "erinnerst du dich",
    "was haben wir",
    "was suchte ich",
    "was haben wir gesucht",
    "was habe ich",
    "was suche ich",
    "eben gesucht",
]


def _structure_task(task: str, url: str) -> List[str]:
    """
    Wandelt komplexe natürlichsprachige Anfragen in eine geordnete Schritt-Liste um.

    Rückgabe: List[str] — jeder Eintrag ist ein eigenständiger, ausführbarer Schritt.

    Beispiel:
    - "suche hotels in stockholm für 3.3.2026 2 personen"
      → ["Navigiere zu booking.com",
         "Cookies akzeptieren falls Banner sichtbar",
         "Klicke auf Suchfeld und gib ein: 'hotels in stockholm'",
         "Drücke Enter",
         "Setze Datum: 3.3.2026",
         "Setze Personen: 2",
         "Beende Task und berichte Ergebnisse"]
    """
    import re

    task_lower = task.lower()
    steps: List[str] = []

    # 1. Navigation + Cookies (immer zuerst)
    if url:
        domain = url.replace("https://", "").replace("http://", "").split("/")[0]
        steps.append(f"Navigiere zu {domain}")
        steps.append(
            "Akzeptiere Cookies NUR falls ein Cookie-Banner sichtbar ist — sonst direkt weiter"
        )

    # 2. Zielort aus Suchbegriff extrahieren (NUR den Ort, keine Datums-/Personendetails)
    search_match = re.search(
        r"(?:suche(?:\s+nach)?|schau(?:\s+nach)?|finde)\s+(?:hotels?\s+in\s+)?(.+?)"
        r"(?:\s+(?:für\s+den|für|am|vom|ab|und\s+dann|dann|anschließend)|\s+\d{1,2}[./]|$)",
        task_lower,
    )
    if search_match:
        start, end = search_match.span(1)
        destination = task[start:end].strip().rstrip(",")

        # Schritt A: NUR ins Suchfeld tippen (Zielort)
        steps.append(
            f"Klicke auf das Suchfeld 'Wohin reisen Sie?' (Destinations-Eingabefeld oben auf der Seite) "
            f"und tippe NUR: '{destination}'"
        )
        # Schritt B: Autocomplete-Vorschlag wählen ODER Enter drücken
        steps.append(
            f"Wähle den ersten Vorschlag '{destination}' aus der Autocomplete-/Dropdown-Liste "
            f"(falls kein Dropdown: drücke Enter)"
        )
        steps.append("Warte 2 Sekunden bis die Seite reagiert hat")

    # 3. Datum — Anreise und Abreise als GETRENNTE Schritte
    date_matches = re.findall(r'\d{1,2}[./]\d{1,2}[./]\d{2,4}', task)
    if len(date_matches) >= 2:
        steps.append(
            f"Klicke auf das Anreisedatum-Feld und wähle den {date_matches[0]} im Kalender "
            f"(Klick auf den richtigen Tag im Monats-Kalender)"
        )
        steps.append(
            f"Klicke auf das Abreisedatum-Feld (oder wähle direkt im geöffneten Kalender) "
            f"und wähle den {date_matches[1]}"
        )
    elif len(date_matches) == 1:
        steps.append(
            f"Klicke auf das Datum-Feld und wähle den {date_matches[0]} im Kalender"
        )

    # 4. Personen-/Gästeanzahl
    persons_match = re.search(
        r'(\d+)\s*(?:person(?:en)?|erwachsene?|gäste?|reisende?)',
        task_lower,
    )
    if persons_match:
        steps.append(
            f"Klicke auf das Gäste-Feld (zeigt '2 Erwachsene · X Kinder · X Zimmer') "
            f"und setze die Anzahl auf {persons_match.group(1)} Erwachsene"
        )

    # 5. Suche starten (immer als letzter Pflichtschritt nach Datum/Gäste)
    if search_match:
        steps.append(
            "Klicke auf den blauen Suche-Button um die Hotelsuche zu starten"
        )
        steps.append("Warte 3 Sekunden auf die Suchergebnisse")

    # 6. Explizite Klick/Extraktions-Anweisung
    click_match = re.search(
        r"(?:klicke\s+auf|extrahiere|zeige\s+(?:mir)?)\s+(.+?)(?:\s+(?:und|dann)|$)",
        task_lower,
    )
    if click_match:
        start, end = click_match.span(1)
        steps.append(f"Interagiere mit: {task[start:end].strip()}")

    # Fallback: wenn fast nichts erkannt, originalen Task direkt übergeben
    if len(steps) <= 2:
        steps.append(f"Führe aus: {task}")

    # Abschluss
    steps.append("Beende Task und berichte Ergebnisse")

    return steps


_IMAGE_EXTENSIONS = re.compile(r"\.(jpg|jpeg|png|webp|gif|bmp|tiff?|avif)\b", re.IGNORECASE)


def quick_intent_check(query: str) -> Optional[str]:
    """Schnelle Keyword-basierte Intent-Erkennung."""
    query_lower = query.lower()

    # BILD-Dateien — höchste Priorität (nur wenn Datei tatsächlich existiert)
    for _img_match in _IMAGE_EXTENSIONS.finditer(query):
        _path_start = query.rfind(" ", 0, _img_match.start())
        _path_start = _path_start + 1 if _path_start >= 0 else 0
        _candidate = query[_path_start:_img_match.end()].strip("\"'(),[]")
        if os.path.isfile(_candidate):
            return "image"

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
        raw_content = ""
        if response.choices and hasattr(response.choices[0], "message"):
            content = response.choices[0].message.content
            if isinstance(content, str):
                raw_content = content
            elif isinstance(content, list):
                # Defensive: Einige APIs liefern segmentierte Content-Listen
                parts = []
                for item in content:
                    if isinstance(item, dict) and isinstance(item.get("text"), str):
                        parts.append(item["text"])
                    elif hasattr(item, "text") and isinstance(getattr(item, "text"), str):
                        parts.append(getattr(item, "text"))
                raw_content = "".join(parts)

        decision = raw_content.strip().lower().replace(".", "")
        if not decision:
            log.warning(
                "⚠️ Leere Dispatcher-Antwort. Fallback auf 'executor'. "
                f"(raw_len={len(raw_content)}, raw_preview={repr(raw_content[:120])})"
            )
            return "executor"

        # Direkter Treffer
        if decision in AGENT_CLASS_MAP:
            log.info(f"✅ Entscheidung: {decision}")
            return decision

        # Suche im Text
        for key in AGENT_CLASS_MAP.keys():
            if key in decision:
                log.info(f"✅ Entscheidung (extrahiert): {key}")
                return key

        log.warning(
            f"⚠️ Unsicher ({decision}). Fallback auf 'executor'. "
            f"(raw_len={len(raw_content)}, raw_preview={repr(raw_content[:160])})"
        )
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

    raw_query = "" if query is None else str(query)
    query = _sanitize_user_query(raw_query)
    if not query:
        return None

    audit = AuditLogger()
    audit.log_start(query, agent_name)
    audit_tool_call("dispatcher_start", {"agent": agent_name, "query": query[:100]})

    effective_session_id = session_id or str(uuid.uuid4())[:8]
    final_output: Optional[str] = None
    runtime_metadata: dict = {
        "source": "run_agent",
        "agent": agent_name,
        "query_sanitized": query != raw_query,
    }

    def _ret(value, extra_metadata: Optional[dict] = None):
        nonlocal final_output, runtime_metadata
        final_output = None if value is None else str(value)
        if isinstance(extra_metadata, dict):
            runtime_metadata.update(extra_metadata)
        return value

    lane_manager.set_registry(registry_v2)
    lane = await lane_manager.get_or_create_lane(effective_session_id)
    log.info(f"Lane {effective_session_id} status: {lane.status.value}")
    _log_canvas_agent_event(
        session_id=effective_session_id,
        agent_name=agent_name,
        status="running",
        message=query[:200],
        payload={"phase": "start"},
    )

    AgentClass = AGENT_CLASS_MAP.get(agent_name)

    if not AgentClass:
        log.error(f"❌ Agent '{agent_name}' nicht gefunden.")
        audit.log_end("Agent nicht gefunden", "error")
        result = _ret(None, {"error": "agent_not_found"})
        _log_interaction_deterministic(
            user_input=query,
            assistant_output=final_output,
            agent_name=agent_name,
            session_id=effective_session_id,
            metadata=runtime_metadata,
        )
        _log_canvas_agent_event(
            session_id=effective_session_id,
            agent_name=agent_name,
            status="error",
            message="Agent nicht gefunden",
            payload={"reason": "agent_not_found"},
        )
        return result

    # Policy Gate: Destruktive Anfragen pruefen
    safe, warning = check_query_policy(query)
    if not safe:
        log.warning(f"[policy] {warning}")
        print(f"\n⚠️  {warning}")
        try:
            confirm = await asyncio.to_thread(input, "Fortfahren? (ja/nein): ")
            if confirm.strip().lower() not in ["ja", "j", "yes", "y"]:
                audit.log_end(f"Abgebrochen: {warning}", "cancelled")
                result = _ret(
                    f"Abgebrochen: {warning}",
                    {"cancelled_by_policy": True},
                )
                _log_interaction_deterministic(
                    user_input=query,
                    assistant_output=final_output,
                    agent_name=agent_name,
                    session_id=effective_session_id,
                    metadata=runtime_metadata,
                )
                _log_canvas_agent_event(
                    session_id=effective_session_id,
                    agent_name=agent_name,
                    status="cancelled",
                    message=str(final_output or "")[:200],
                    payload={"reason": "policy_cancelled"},
                )
                return result
        except Exception:
            pass  # Non-interactive: weitermachen

    log.info(f"\n🚀 Starte Agent: {agent_name.upper()}")
    _emit_dispatcher_status(agent_name, "start", "Initialisiere Agent")

    try:
        # QUICK FIX: Spezielle Behandlung für VisualAgent (nutzt präzisen standalone Agent)
        if AgentClass == "SPECIAL_VISUAL":
            log.info("👁️ Nutze präzisen VisualAgent v2.1 (SoM + Mouse Feedback)")
            _emit_dispatcher_status(agent_name, "visual_active", "Standalone VisualAgent")
            final_answer = await run_visual_task_precise(query, max_iterations=30)

            print("\n" + "=" * 80)
            print(f"💡 FINALE ANTWORT ({agent_name.upper()}):")
            print("=" * 80)
            print(textwrap.fill(str(final_answer), width=80))
            print("=" * 80)
            audit.log_end(str(final_answer)[:200], "completed")
            return _ret(final_answer, {"execution_path": "special_visual"})

        # VisualNemotronAgent v4 für Desktop-Automatisierung (mit echten Maus-Tools)
        if AgentClass == "SPECIAL_VISUAL_NEMOTRON":
            if not VISUAL_NEMOTRON_V4_AVAILABLE:
                log.error("❌ VisualNemotronAgent v4 nicht verfügbar")
                audit.log_end("VisualNemotronAgent v4 nicht verfügbar", "error")
                return _ret(
                    "Fehler: VisualNemotronAgent v4 nicht verfügbar",
                    {"execution_path": "special_visual_nemotron", "error": "agent_unavailable"},
                )

            log.info("🎯 Nutze VisualNemotronAgent v4 (Desktop Edition)")
            log.info("   Features: PyAutoGUI | SoM UI-Scan | Echte Maus-Klicks")
            _emit_dispatcher_status(agent_name, "visual_active", "VisualNemotron v4")

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

            task_list = _structure_task(task, url)

            log.info(f"   URL: {url}")
            log.info(f"   Plan ({len(task_list)} Schritte):")
            for i, s in enumerate(task_list):
                log.info(f"      {i+1}. {s}")

            try:
                log.info("   🚀 Starte v4 (Desktop Edition mit PyAutoGUI)")
                result = await run_desktop_task(
                    task_list=task_list, url=url if url else None, max_steps=15
                )
                version = "v4"

                success = result.get("success", False)
                steps_executed = result.get("steps_executed", result.get("steps", 0))
                steps_planned = result.get("total_steps_planned", 0)
                unique_states = result.get("unique_states", 0)
                error = result.get("error")

                # Plan-Ergebnis oder Freitext-Ergebnis
                completed_steps = result.get("completed_steps", [])
                failed_steps = result.get("failed_steps", [])

                final_answer = f"""🎯 Visual Nemotron Automation {version} Ergebnis:

Status: {"✅ ERFOLGREICH" if success else "❌ FEHLER" if error else "⚠️ UNVOLLSTÄNDIG"}
Schritte: {steps_executed} ausgeführt{f" von {steps_planned} geplant" if steps_planned else ""}
"""
                if error:
                    final_answer += f"\nFehler: {error}\n"

                # Plan-Modus: Zeige Todo-Fortschritt
                if completed_steps or failed_steps:
                    final_answer += "\nPlan-Fortschritt:\n"
                    for s in completed_steps:
                        final_answer += f"  ✅ {s[:70]}\n"
                    for s in failed_steps:
                        final_answer += f"  ❌ {s[:70]}\n"
                else:
                    # Freitext-Modus: Zeige Aktionen
                    results = result.get("results", result.get("history", []))
                    if results:
                        final_answer += "\nDurchgeführte Aktionen:\n"
                        for r in results[:10]:
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
                _emit_dispatcher_status(agent_name, "done", "VisualNemotron abgeschlossen")
                return _ret(
                    final_answer,
                    {"execution_path": "special_visual_nemotron"},
                )

            except Exception as e:
                log.error(f"❌ VisualNemotronAgent Fehler: {e}")
                import traceback

                log.error(traceback.format_exc())
                audit.log_end(str(e), "error")
                _emit_dispatcher_status(agent_name, "error", f"VisualNemotron: {str(e)[:80]}")
                return _ret(
                    f"Fehler bei Visual Automation: {e}",
                    {"execution_path": "special_visual_nemotron", "exception": str(e)[:300]},
                )

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

        try:
            setattr(agent_instance, "conversation_session_id", effective_session_id)
        except Exception:
            pass
        try:
            if hasattr(agent_instance, "set_audit_step_logger"):
                agent_instance.set_audit_step_logger(audit.log_step)
                audit.log_step(
                    action="agent_trace_hook",
                    input_data={
                        "agent": agent_name,
                        "session_id": effective_session_id,
                    },
                    output_data={"enabled": True},
                    status="ok",
                )
        except Exception as e:
            log.debug(f"Audit-Step-Hook konnte nicht gesetzt werden: {e}")

        final_answer = await agent_instance.run(query)
        _emit_dispatcher_status(agent_name, "done", "Agent-Run abgeschlossen")
        if hasattr(agent_instance, "get_runtime_telemetry"):
            try:
                runtime_metadata["agent_runtime"] = agent_instance.get_runtime_telemetry()
            except Exception as telemetry_error:
                runtime_metadata["agent_runtime_error"] = str(telemetry_error)[:200]

        print("\n" + "=" * 80)
        print(f"💡 FINALE ANTWORT ({agent_name.upper()}):")
        print("=" * 80)
        print(textwrap.fill(str(final_answer), width=80))
        print("=" * 80)
        audit.log_end(str(final_answer)[:200], "completed")
        return _ret(final_answer, {"execution_path": "standard"})

    except Exception as e:
        import traceback

        log.error(f"❌ Fehler beim Ausführen des Agenten '{agent_name}': {e}")
        log.error(traceback.format_exc())
        audit.log_end(str(e), "error")
        return _ret(
            None,
            {
                "execution_path": "run_agent_exception",
                "exception": str(e)[:300],
            },
        )
    finally:
        _log_interaction_deterministic(
            user_input=query,
            assistant_output=final_output,
            agent_name=agent_name,
            session_id=effective_session_id,
            metadata=runtime_metadata,
        )
        _log_canvas_agent_event(
            session_id=effective_session_id,
            agent_name=agent_name,
            status=_infer_interaction_status(final_output),
            message=str(final_output or "")[:240],
            payload=runtime_metadata,
        )


def _infer_interaction_status(result: Optional[str]) -> str:
    """Leitet einen einfachen Status aus dem Agent-Ergebnis ab."""
    if result is None:
        return "error"
    text = str(result).strip().lower()
    if not text:
        return "error"
    if text.startswith("abgebrochen"):
        return "cancelled"
    if text.startswith("fehler") or text.startswith("error"):
        return "error"
    return "completed"


def _log_interaction_deterministic(
    *,
    user_input: str,
    assistant_output: Optional[str],
    agent_name: str,
    session_id: str,
    metadata: Optional[dict] = None,
) -> None:
    """Persistiert jede Runde deterministisch im kanonischen Memory-Kern."""
    try:
        from memory.memory_system import memory_manager

        output = "" if assistant_output is None else str(assistant_output)
        status = _infer_interaction_status(output)
        event_metadata = {"source": "main_dispatcher", "agent": agent_name}
        if isinstance(metadata, dict):
            event_metadata.update(metadata)
        if hasattr(memory_manager, "get_runtime_memory_snapshot"):
            try:
                snapshot = memory_manager.get_runtime_memory_snapshot(session_id=session_id)
                if isinstance(snapshot, dict):
                    event_metadata["memory_snapshot"] = snapshot
            except Exception:
                pass
        memory_manager.log_interaction_event(
            user_input=user_input,
            assistant_response=output,
            agent_name=agent_name,
            status=status,
            external_session_id=session_id,
            metadata=event_metadata,
        )
        log.info(
            f"🧠 Deterministisches Logging gespeichert (session={session_id}, status={status})"
        )
    except Exception as e:
        log.warning(f"⚠️ Deterministisches Interaction-Logging fehlgeschlagen: {e}")


def _log_canvas_agent_event(
    *,
    session_id: str,
    agent_name: str,
    status: str,
    message: str = "",
    payload: Optional[dict] = None,
) -> None:
    """Schreibt Agent-Run Events in ein zugeordnetes Canvas (falls vorhanden)."""
    try:
        from orchestration.canvas_store import canvas_store

        result = canvas_store.record_agent_event(
            session_id=session_id,
            agent_name=agent_name,
            status=status,
            message=message,
            payload=payload,
        )
        if result:
            canvas_id = result.get("canvas_id", "")
            log.info(
                f"🧩 Canvas-Event gespeichert (canvas={canvas_id}, session={session_id}, status={status})"
            )
    except Exception as e:
        log.debug(f"Canvas-Logging uebersprungen: {e}")


async def fetch_tool_descriptions_from_server(
    max_wait: int = 90, retry_interval: int = 3
) -> Optional[str]:
    """
    Holt die Tool-Liste vom Server.
    Wartet bis zu max_wait Sekunden auf den MCP-Server (Retry bei ConnectError).
    Nützlich wenn Dispatcher und MCP-Server gleichzeitig starten (systemd).
    """
    server_url = "http://127.0.0.1:5000/get_tool_descriptions"
    waited = 0

    while True:
        try:
            async with httpx.AsyncClient() as http_client:
                response = await http_client.get(server_url, timeout=5.0)

            if response.status_code != 200:
                log.error(f"❌ Server antwortet mit Status {response.status_code}")
                return None

            if waited > 0:
                log.info(f"✅ MCP-Server erreichbar (nach {waited}s Wartezeit)")
            return response.json().get("descriptions")

        except httpx.ConnectError:
            if waited == 0:
                log.info(f"⏳ MCP-Server noch nicht bereit — warte bis zu {max_wait}s ...")
            waited += retry_interval
            if waited > max_wait:
                log.fatal(f"FATAL: Keine Verbindung zum Server ({server_url}) nach {max_wait}s.")
                log.fatal("Starte den MCP Server mit: python server/mcp_server.py")
                return None
            log.info(f"   ... {waited}s/{max_wait}s")
            await asyncio.sleep(retry_interval)

        except Exception as e:
            log.error(f"❌ Fehler beim Abrufen der Tools: {e}")
            return None


async def _cli_loop(tools_desc: str) -> None:
    """Interaktive CLI-Schleife (läuft parallel zum AutonomousRunner)."""
    import sys
    import signal as _signal

    # Daemon-Modus: kein TTY (z.B. systemd-Service) → warte auf SIGTERM
    if not sys.stdin.isatty():
        log.info("Daemon-Modus: CLI deaktiviert (kein TTY). Stoppe via SIGTERM.")
        stop_event = asyncio.Event()
        try:
            loop = asyncio.get_event_loop()
            loop.add_signal_handler(_signal.SIGTERM, stop_event.set)
            loop.add_signal_handler(_signal.SIGINT, stop_event.set)
        except NotImplementedError:
            pass  # Windows
        await stop_event.wait()
        return

    print("\nBereit. Beispiele:")
    print("  • 'asyncio vs threading für 100 API-Calls?' → REASONING (Nemotron)")
    print("  • 'Recherchiere KI-Sicherheit' → RESEARCH")
    print("  • 'Öffne Firefox' → VISUAL")
    print("  • 'Wie spät ist es?' → EXECUTOR")
    print("  • '/tasks' → Offene autonome Tasks anzeigen")
    print("\nTipp: 'exit' zum Beenden\n")

    conversation_session_id = f"chat_{uuid.uuid4().hex[:8]}"
    print(f"Aktive Session: {conversation_session_id}")

    while True:
        try:
            q = await asyncio.to_thread(input, "\n\033[32mDu> \033[0m")
            q_clean = _sanitize_user_query(q)
            if not q_clean:
                continue

            if q_clean.lower() in ["exit", "quit", "q"]:
                break

            if q_clean.lower() in {"/new", "new session", "neue session", "reset session"}:
                conversation_session_id = f"chat_{uuid.uuid4().hex[:8]}"
                print(f"   ♻️ Neue Session gestartet: {conversation_session_id}")
                continue

            # Task-Liste anzeigen
            if q_clean.lower() in {"/tasks", "tasks", "offene tasks"}:
                _print_tasks()
                continue

            print("   🤔 Timus denkt...")
            agent = await get_agent_decision(q_clean)
            print(f"   📌 Agent: {agent.upper()}")
            await run_agent(
                agent,
                q_clean,
                tools_desc,
                session_id=conversation_session_id,
            )

        except (KeyboardInterrupt, EOFError):
            break
        except Exception as e:
            log.error(f"Fehler: {e}")


def _print_tasks() -> None:
    """Zeigt alle Tasks aus der SQLite-Queue an."""
    try:
        from orchestration.task_queue import get_queue
        tasks = get_queue().get_all(limit=20)
        if not tasks:
            print("   Keine Tasks vorhanden.")
            return
        stats = get_queue().stats()
        print(f"\n   Queue: {stats}")
        print(f"\n   {'ID':8} {'Prio':6} {'Status':12} {'Agent':12} Beschreibung")
        print("   " + "-" * 75)
        prio_names = {0: "CRIT", 1: "HIGH", 2: "NORM", 3: "LOW"}
        icons = {"pending": "⏳", "in_progress": "🔄", "completed": "✅", "failed": "❌", "cancelled": "🚫"}
        for t in tasks:
            tid = t.get("id", "?")[:8]
            status = t.get("status", "?")
            prio = prio_names.get(t.get("priority", 2), "?")
            agent = (t.get("target_agent") or "auto")[:10]
            desc = t.get("description", "")[:42]
            icon = icons.get(status, "•")
            print(f"   {tid:8} {prio:6} {icon} {status:10} {agent:12} {desc}")
    except Exception as e:
        print(f"   Fehler beim Lesen: {e}")


async def main_loop():
    """Hauptschleife: CLI + AutonomousRunner + Telegram parallel."""
    print("\n" + "=" * 60)
    print("🤖 TIMUS MASTER DISPATCHER (v3.4 - Autonomous + Telegram) 🤖")
    print("=" * 60)

    tools_desc = await fetch_tool_descriptions_from_server()
    if not tools_desc:
        return

    # 1. Autonomous Runner (Scheduler)
    from orchestration.autonomous_runner import AutonomousRunner
    interval = int(os.getenv("HEARTBEAT_INTERVAL_MINUTES", "15"))
    runner = AutonomousRunner(interval_minutes=interval)
    await runner.start(tools_desc)
    log.info(f"🤖 AutonomousRunner aktiv (alle {interval} min)")

    # 2. Telegram Gateway (optional)
    from gateway.telegram_gateway import TelegramGateway
    tg_token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    gateway = TelegramGateway(token=tg_token, tools_desc=tools_desc)
    tg_active = await gateway.start()
    if tg_active:
        print("   📱 Telegram-Bot aktiv")
    else:
        print("   📱 Telegram inaktiv (TELEGRAM_BOT_TOKEN nicht gesetzt)")

    # 3. Webhook-Server (optional)
    from gateway.webhook_gateway import WebhookServer
    webhook = WebhookServer()
    webhook_enabled = os.getenv("WEBHOOK_ENABLED", "false").lower() in ("1", "true", "yes")
    if webhook_enabled:
        await webhook.start()
        port = os.getenv("WEBHOOK_PORT", "8765")
        print(f"   🔗 Webhook-Server aktiv auf Port {port}")
    else:
        print("   🔗 Webhook inaktiv (WEBHOOK_ENABLED=false)")

    # 4. System-Monitor
    from gateway.system_monitor import SystemMonitor
    monitor = SystemMonitor()
    await monitor.start()

    # events.json Vorlage anlegen wenn nicht vorhanden
    from gateway.event_router import init_events_config
    init_events_config()

    try:
        await _cli_loop(tools_desc)
    finally:
        await runner.stop()
        await gateway.stop()
        await webhook.stop()
        await monitor.stop()

    print("\n👋 Bye!")


if __name__ == "__main__":
    try:
        asyncio.run(main_loop())
    except KeyboardInterrupt:
        pass
