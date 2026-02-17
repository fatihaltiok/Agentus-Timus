# Timus - Autonomous Multi-Agent Desktop AI

Timus ist ein autonomes Multi-Agent-System fuer Desktop-Automatisierung, Web-Recherche, Code-Generierung und kreative Aufgaben. Es kombiniert 7 spezialisierte KI-Agenten mit 50+ Tools ueber einen zentralen MCP-Server.

---

## Architektur

```
Benutzer-Input
      |
      v
 main_dispatcher.py ──── Intent-Analyse (Keyword + LLM)
      |
      v
 ┌────────────────────────────────────────────────────┐
 │               AGENTEN-AUSWAHL                      │
 ├──────────┬──────────┬──────────┬───────────────────┤
 │ Executor │ Research │Reasoning │ Creative          │
 │ Developer│   Meta   │  Visual  │ Visual-Nemotron   │
 └────┬─────┴────┬─────┴────┬─────┴───────────────────┘
      │          │          │
      │    ┌─────┴──────┐   │
      │    │ Delegation │   │  <-- Agenten koennen sich
      │    │   (MCP)    │   │      gegenseitig delegieren
      │    └─────┬──────┘   │
      v          v          v
 ┌─────────────────────────────────────┐
 │     MCP-Server (Port 5000)         │
 │     JSON-RPC 2.0 | 50+ Tools      │
 ├─────────────────────────────────────┤
 │ OCR | Vision | Browser | Mouse     │
 │ Search | Files | Memory | Voice    │
 │ Creative | Developer | Delegation  │
 └─────────────────────────────────────┘
      │          │          │
      v          v          v
 ┌─────────┐ ┌────────┐ ┌──────────┐
 │ Desktop │ │ Browser│ │ APIs     │
 │PyAutoGUI│ │Playwrt │ │OpenAI ..│
 └─────────┘ └────────┘ └──────────┘
```

---

## Agenten

### ExecutorAgent
- **Modell:** gpt-5-mini (OpenAI)
- **Aufgabe:** Schnelle einfache Tasks - Dateien lesen/schreiben, Websuche, Zusammenfassungen, einfache Fragen
- **Max Iterationen:** 30

### DeepResearchAgent
- **Modell:** deepseek-reasoner (DeepSeek)
- **Aufgabe:** Tiefenrecherche mit These-Antithese-Synthese Framework, Source Quality Rating, akademische Quellenanalyse
- **Max Iterationen:** 8

### ReasoningAgent
- **Modell:** nvidia/nemotron-3-nano-30b-a3b (OpenRouter)
- **Aufgabe:** Komplexe Multi-Step-Analyse, Debugging, Architektur-Entscheidungen, Root-Cause-Analyse, Pro/Contra-Abwaegungen
- **Besonderheit:** enable_thinking-Steuerung fuer Nemotron Reasoning

### CreativeAgent
- **Modell:** gpt-5.2 (OpenAI)
- **Aufgabe:** Bildgenerierung (DALL-E), kreative Texte, Gedichte, Songs
- **Besonderheit:** Hybrid-Workflow - GPT-5.1 generiert detaillierten Prompt, Nemotron strukturiert den Tool-Call

### DeveloperAgent / DeveloperAgentV2
- **Modell:** mercury-coder-small (Inception Labs)
- **Aufgabe:** Code-Generierung, Refactoring, Skripte, Datei-Operationen
- **V2-Features:** Context-Files Support, Code-Validierung (AST, Style, Security), Multi-Tool Support, Fehler-Recovery

### MetaAgent
- **Modell:** claude-sonnet-4-5 (Anthropic)
- **Aufgabe:** Workflow-Planung, mehrstufige Aufgaben koordinieren, Agent-Orchestrierung
- **Besonderheit:** Skill-System mit automatischer Skill-Auswahl und Progressive Disclosure

### VisualAgent
- **Modell:** claude-sonnet-4-5 (Anthropic)
- **Aufgabe:** Desktop-/Browser-Automatisierung mit Screenshot-Analyse
- **3-Stufen-Praezision:**
  1. SoM (Set-of-Mark) - Grob-Lokalisierung (+-50px)
  2. Mouse Feedback Tool - Fein-Lokalisierung (+-5px)
  3. Cursor-Typ als Echtzeit-Feedback (ibeam = Textfeld, hand = klickbar)
- **Features:** ROI-Management, Loop-Recovery, Screen-Change-Gate, Strukturierte Navigation

### VisualNemotronAgent v4 (Desktop Edition)
- **Modell:** Nemotron + Qwen2-VL / GPT-4 Vision
- **Aufgabe:** Komplexe mehrstufige Desktop-Automatisierung
- **Tech:** PyAutoGUI + SoM fuer echte Maus-Klicks auf dem ganzen Desktop

---

## Agent-zu-Agent Delegation

Agenten koennen zur Laufzeit andere Agenten um Hilfe bitten — als normalen MCP-Tool-Call ueber `delegate_to_agent`. Ein MetaAgent kann z.B. den ResearchAgent fuer Recherche und den DeveloperAgent fuer Code-Generierung delegieren.

```
Beispiel: "Recherchiere KI-Sicherheit und erstelle einen Plan"

1. Dispatcher         -> MetaAgent
2. MetaAgent          -> delegate_to_agent(research, "Recherchiere KI-Sicherheit")
3.   Registry         -> Lazy-erstellt DeepResearchAgent (holt tools_description)
4.   DeepResearchAgent-> Ergebnis zurueck an MetaAgent
5. MetaAgent          -> nutzt Ergebnis fuer Plan -> Final Answer
```

**Features:**
- **Lazy-Instantiierung:** Agenten werden erst bei erster Delegation erstellt (Factory-Pattern)
- **Loop-Prevention:** Delegation-Stack verhindert zirkulaere Aufrufe (A->B->A)
- **Max Tiefe:** Maximal 3 verschachtelte Delegationen
- **Capability-Suche:** `find_agent_by_capability("vision")` findet den VisualAgent

---

## Tools (50+ Module)

### Vision und UI-Automation

| Tool | Funktionen |
|------|-----------|
| **ocr_tool** | GPU-beschleunigte OCR mit PaddleOCR (`read_text_from_screen`) |
| **som_tool** | Set-of-Mark UI-Element-Erkennung (`describe_screen_elements`, `scan_ui_elements`) |
| **visual_grounding_tool** | Text-Extraktion vom Bildschirm (`get_all_screen_text`, `list_monitors`) |
| **visual_segmentation_tool** | Screenshot-Erfassung (`get_screenshot`) |
| **visual_click_tool** | Praezises Klicken auf UI-Elemente |
| **mouse_tool** | Maus-Steuerung (`click_at`, `move_mouse`, `type_text`, `scroll`) |
| **mouse_feedback_tool** | Cursor-Typ-Feedback fuer Fein-Lokalisierung (`get_mouse_position`) |
| **screen_change_detector** | Optimierung: nur bei Bildschirm-Aenderungen analysieren |
| **hybrid_detection_tool** | Kombiniert DOM + Vision fuer beste Trefferquote |
| **screen_contract_tool** | Screenshot-Optimierung und Komprimierung |
| **annotator_tool** | Screenshot-Beschriftung mit GPT-5.2 |
| **icon_recognition_tool** | Icon-Erkennung auf dem Desktop |
| **verified_vision_tool** | Verifizierte Vision-Ausgaben |
| **cookie_banner_tool** | Cookie-Banner Erkennung und Behandlung |

### Browser und Navigation

| Tool | Funktionen |
|------|-----------|
| **browser_tool** | `open_url`, `click_by_text`, `click_by_selector`, `get_text`, `list_links`, `type_text`, `get_page_content`, `dismiss_overlays`, `browser_session_status`, `browser_save_session`, `browser_close_session`, `browser_cleanup_expired` |
| **browser_controller** | DOM-First Browser-Control mit State-Tracking und Session-ID Propagation |
| **smart_navigation_tool** | Webseiten-Analyse (`analyze_current_page`) |
| **visual_browser_tool** | Vision-basierte Browser-Steuerung |
| **application_launcher** | Desktop-Apps starten (`list_applications`, `open_application`) |

### Recherche und Information

| Tool | Funktionen |
|------|-----------|
| **search_tool** | Web-Suche via DataForSEO (Google, Bing, DuckDuckGo, Yahoo) |
| **deep_research** | v5.0 - These-Antithese-Synthese, Source Quality Rating, Multi-Runden-Recherche |
| **document_parser** | Dokumenten-Analyse und Parsing |
| **summarizer** | Text-Zusammenfassung |
| **fact_corroborator** | Fakten-Verifizierung mit Cross-Checks |
| **verification_tool** | Aktions-Verifizierung (`capture_screen_before_action`, `verify_action_result`, `check_for_errors`) |

### Entwicklung

| Tool | Funktionen |
|------|-----------|
| **developer_tool** | Code-Generierung via Inception Labs mercury-coder (`implement_feature`) |
| **inception_tool** | Health-Check fuer Inception-Service |
| **file_system_tool** | Datei-Operationen (`list_directory`, `write_file`, `read_file`, `list_agent_files`) |
| **text_finder_tool** | Text-Suche in Dateien |

### Kreativ

| Tool | Funktionen |
|------|-----------|
| **creative_tool** | Bildgenerierung mit DALL-E 3 (`generate_image`) |
| **voice_tool** | Text-to-Speech Synthese (`voice_list_voices`) |

### System und Administration

| Tool | Funktionen |
|------|-----------|
| **system_monitor_tool** | System-Auslastung (CPU, RAM, Festplatte) |
| **maintenance_tool** | Cleanup und Wartung |
| **debug_tool** | Debugging-Utilities |
| **timing_tool** | Performance-Messung |

### Memory und Wissen

| Tool | Funktionen |
|------|-----------|
| **memory_tool** | `remember`, `recall`, `get_memory_context`, `get_known_facts`, `get_memory_stats`, `find_related_memories`, `sync_memory_to_markdown` |
| **reflection_tool** | Selbst-Reflexion des Agenten |
| **reflection_engine** | Automatisierte Post-Task Analyse mit Pattern-Erkennung und Learning-Speicherung |
| **curator_tool** | Kuratierung von Inhalten |

### Planung und Koordination

| Tool | Funktionen |
|------|-----------|
| **delegation_tool** | Agent-zu-Agent Delegation (`delegate_to_agent`, `find_agent_by_capability`) |
| **planner** | Task-Planung (`add_task`, `list_available_skills`) |
| **skill_manager_tool** | Skill-Verwaltung (`list_skills`, `learn_new_skill`, `register_new_tool_in_server`, `create_tool_from_pattern`) |
| **skill_recorder** | Skill-Aufzeichnung (`get_recording_status`, `list_recordings`) |
| **report_generator** | Report-Generierung |
| **save_results** | Ergebnis-Speicherung |
| **decision_verifier** | Entscheidungs-Verifizierung |

### Vision Language Models

| Tool | Funktionen |
|------|-----------|
| **qwen_vl_tool** | Qwen2-VL Integration (lokal auf GPU) |

---

## Memory-System v2.0

Drei-Ebenen-Architektur mit Hybrid-Suche, automatisierter Reflexion und bidirektionalem Sync:

```
Memory System v2.0
|
+-- SessionMemory (Kurzzeit)
|   +-- Letzte N Nachrichten (max 20)
|   +-- Aktuelle Entitaeten (Pronomen-Aufloesung)
|   +-- Current Topic
|
+-- PersistentMemory (Langzeit - SQLite + ChromaDB + Markdown)
|   +-- Fakten mit Vertrauenswert und Quelle
|   +-- Konversations-Zusammenfassungen
|   +-- Benutzer-Profile und Praeferenzen
|   +-- Erkannte Muster und Entscheidungen
|
+-- SemanticMemoryStore (ChromaDB Vektor-Store)
|   +-- Embedding-basierte semantische Suche
|   +-- Hybrid-Suche: ChromaDB (Vektoren) + FTS5 (Keywords)
|   +-- Kategorie-Filter und Relevanz-Ranking
|
+-- MarkdownStore (Bidirektionaler Sync)
|   +-- USER.md - Benutzer-Profil (manuell editierbar)
|   +-- SOUL.md - Behavior Hooks und Persoenlichkeit
|   +-- MEMORY.md - Langzeit-Erinnerungen
|   +-- daily/ - Taegliche Logs
|
+-- ReflectionEngine (Post-Task Analyse)
    +-- Automatische Reflexion nach jeder Aufgabe
    +-- Pattern-Erkennung (was funktioniert, was nicht)
    +-- Speichert Learnings als patterns/decisions/improvements
```

**Features:**
- Automatische Fakten-Extraktion aus Konversationen
- Semantische Hybrid-Suche (ChromaDB Embeddings + FTS5 Keyword-Suche)
- Entity Resolution (er/sie/es -> konkrete Entitaet)
- Self-Model: Lernt Benutzer-Muster ueber Zeit
- Post-Task Reflexion mit automatischer Learning-Speicherung
- Bidirektionaler Sync: SQLite <-> Markdown <-> ChromaDB
- Manuell editierbare Markdown-Dateien mit automatischer Rueck-Synchronisation

### Browser-Isolation

Session-isolierte Browser-Kontexte mit persistentem State:

```
PersistentContextManager
├── Session-Pool (max 5 parallele Kontexte)
├── LRU Eviction bei Limit ("default" geschuetzt)
├── Cookie/LocalStorage Persistenz via storage_state
├── Session-Timeout Cleanup (60 min)
└── Retry-Handler
    ├── Exponential Backoff (2s, 5s, 10s)
    └── CAPTCHA/Cloudflare-Erkennung
```

```python
# Session-isoliert browsen
result = await open_url("https://example.com", session_id="user_123")
await browser_save_session("user_123")       # State speichern
await browser_close_session("user_123")      # Session schliessen
```

```bash
# Konfiguration via ENV
BROWSER_MAX_CONTEXTS=5
BROWSER_SESSION_TIMEOUT=60
BROWSER_MAX_RETRIES=3
BROWSER_RETRY_DELAYS=2,5,10
```

### Proaktiver Scheduler

Der Heartbeat-Scheduler fuehrt in konfigurierbaren Intervallen autonome Aktionen aus:

| Aktion | Intervall | Beschreibung |
|--------|-----------|--------------|
| Task-Check | Jedes Heartbeat (15 min) | Prueft `tasks.json` auf pending/in_progress |
| Self-Model Refresh | Alle 60 min | Aktualisiert Self-Model via LLM |
| Memory Sync | Alle 4 Heartbeats | SQLite -> Markdown Sync |

```bash
# Konfiguration via ENV
HEARTBEAT_ENABLED=true
HEARTBEAT_INTERVAL_MINUTES=15
HEARTBEAT_SELF_MODEL_REFRESH_INTERVAL=60
REFLECTION_ENABLED=true
```

---

## Skill-System

Timus verfuegt ueber ein duales Skill-System:

### 1. YAML-Skills (Agent-Workflows)
Skills werden in YAML+Markdown definiert und vom MetaAgent automatisch eingesetzt:

```yaml
---
name: skill-name
description: Wann dieser Skill verwendet wird
tags: [automation, web]
---
# Anweisungen
Schritt-fuer-Schritt Anleitungen fuer den Agenten
```

### 2. Python-Skills (Tool-Generierung)
Automatisch generierte Python-Tools ueber `create_tool_from_pattern`:

- **Quality-Gate:** Duplikat-Check -> Code-Generierung -> AST-Validierung -> Auto-Registrierung
- **Safeguards:** Pattern muss 3x auftreten, 1h Cooldown, Confidence >= 0.7
- **UI-Pattern Templates:** 8 vorgefertigte Templates (calendar_picker, modal_handler, form_filler, infinite_scroll, login_handler, cookie_banner, dropdown_selector, table_extraction)

**Vorhandene Skills:**
- **image_loader_skill** - Bild-Laden mit Groessen-Anpassung
- **terminal_control_skill** - Shell-Befehle mit Safety-Checks
- **skill-creator** - Meta-Skill zum Erstellen neuer Skills

Skills werden vom MetaAgent automatisch erkannt und bei passenden Tasks eingesetzt.

---

## Unterstuetzte LLM-Provider

| Provider | Modelle | Verwendung |
|----------|---------|------------|
| **OpenAI** | gpt-5, gpt-5.2, gpt-5-mini, gpt-4o | Executor, Creative |
| **Anthropic** | claude-sonnet-4-5, claude-opus-4-6 | Meta, Visual |
| **DeepSeek** | deepseek-reasoner | Deep Research |
| **Inception Labs** | mercury-coder-small | Developer |
| **NVIDIA / OpenRouter** | nemotron-3-nano-30b-a3b | Reasoning |
| **Google** | Gemini | Placeholder |

Jeder Agent kann ueber Environment-Variablen auf ein anderes Modell/Provider umkonfiguriert werden.

---

## Externe Services

| Service | Zweck |
|---------|-------|
| **DataForSEO** | Web-Suche (Google, Bing, DuckDuckGo, Yahoo) |
| **DALL-E 3** | Bildgenerierung |
| **ChromaDB** | Vector-Datenbank fuer Memory |
| **Playwright** | Browser-Automation |
| **PyAutoGUI** | Desktop-Steuerung (Maus/Tastatur) |
| **PaddleOCR** | GPU-beschleunigte Texterkennung |
| **Qwen2-VL** | Lokales Vision-Language-Modell |

---

## Installation

### Voraussetzungen

- Python 3.11+
- NVIDIA GPU mit CUDA (empfohlen fuer OCR, Vision Models)
- 16GB+ RAM

### Setup

```bash
git clone https://github.com/fatihaltiok/Agentus-Timus.git
cd Agentus-Timus
pip install -r requirements.txt

# .env erstellen (siehe .env.example)
cp .env.example .env
# API Keys eintragen
```

### Environment-Variablen

```bash
# LLM Provider Keys
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...
INCEPTION_API_KEY=...
DEEPSEEK_API_KEY=...
OPENROUTER_API_KEY=...

# Services
DATAFORSEO_USER=...
DATAFORSEO_PASS=...

# Konfiguration
VISION_MODEL=claude-sonnet-4-5-20250929
ACTIVE_MONITOR=1
USE_MOUSE_FEEDBACK=1
USE_SCREEN_CHANGE_GATE=false
AUTO_OPEN_FILES=true
```

### Starten

```bash
# 1. MCP-Server starten
python server/mcp_server.py

# 2. Dispatcher starten
python main_dispatcher.py
```

---

## Verwendung

Nach dem Start des Dispatchers koennen Aufgaben in natuerlicher Sprache eingegeben werden:

```
Du> Wie spat ist es?                          -> ExecutorAgent
Du> Recherchiere KI-Sicherheit                -> DeepResearchAgent
Du> asyncio vs threading fuer 100 API-Calls?  -> ReasoningAgent
Du> Male ein Bild von einem Hund im Park      -> CreativeAgent
Du> Schreibe ein Python-Skript fuer...        -> DeveloperAgent
Du> Erstelle einen Plan fuer...               -> MetaAgent
Du> Oeffne Firefox und gehe zu google.com     -> VisualAgent
```

Der Dispatcher erkennt automatisch den Intent und waehlt den passenden Agenten.

---

## Projektstruktur

```
timus/
├── agent/
│   ├── shared/              # Shared Utilities (MCP Client, Screenshot, Parser)
│   ├── agents/              # 7 spezialisierte Agenten
│   ├── agent_registry.py    # Agent-Registry mit Factory-Pattern + Delegation
│   ├── base_agent.py        # BaseAgent mit Multi-Provider Support
│   ├── providers.py         # LLM Provider-Infrastruktur
│   ├── prompts.py           # System Prompts
│   ├── visual_agent.py      # Standalone Visual Agent v2.1
│   ├── developer_agent_v2.py
│   ├── visual_nemotron_agent_v4.py
│   └── timus_consolidated.py  # Re-Export Shim
├── tools/                   # 50+ Tool-Module
│   ├── ocr_tool/
│   ├── som_tool/
│   ├── browser_tool/        # Browser mit Session-Isolation + Retry
│   │   ├── persistent_context.py  # PersistentContextManager
│   │   └── retry_handler.py       # Exponential Backoff + CAPTCHA
│   ├── mouse_tool/
│   ├── search_tool/
│   ├── creative_tool/
│   ├── developer_tool/
│   ├── delegation_tool/     # Agent-zu-Agent Delegation (MCP-Tool)
│   ├── memory_tool/
│   └── ...
├── orchestration/
│   ├── scheduler.py         # Proaktiver Heartbeat-Scheduler
│   └── lane_manager.py      # Lane-basierte Task-Verwaltung
├── server/
│   └── mcp_server.py        # MCP Server (FastAPI, Port 5000)
├── skills/                  # Erlernbare Skills
│   └── templates/           # UI-Pattern Templates (8 Patterns)
├── memory/
│   ├── memory_system.py     # Memory v2.0 (Hybrid-Suche, Sync)
│   ├── reflection_engine.py # Post-Task Reflexion
│   └── markdown_store/      # USER.md, SOUL.md, MEMORY.md
├── utils/                   # Hilfsfunktionen
├── config/                  # Personality-System
├── main_dispatcher.py       # Zentral-Dispatcher
└── docs/                    # Dokumentation
```

---

## Lizenz

Timus - Autonomous Multi-Agent Desktop AI
