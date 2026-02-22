# Tagesbericht — 2026-02-22

**Projekt:** Timus — Autonomous Multi-Agent Desktop AI
**Entwickler:** Fatih Altiok · Offenbach · Raum Frankfurt
**Repo:** `github.com/fatihaltiok/Agentus-Timus` · Branch: `main`
**Letzter Commit:** `0249c89` — `docs: README + Session-Log für M1–M4 + Memory aktualisiert`

---

## 1. Gesamtstatus des Projekts

| Kategorie | Stand |
|-----------|-------|
| Agenten | **12** vollständig implementiert (M1–M4 abgeschlossen) |
| Tools | **60+ Module** im MCP-Server registriert |
| Canvas | v2 — 12 LEDs, SSE, Chat, Upload, Tool-Sidebar |
| Memory | v2.1 — Nemotron-Kurator + Agent-Isolation |
| Gesamttest | GT-1 bis GT-6 — alle bestanden ✅ |
| CI | GitHub Actions — Gate 1/2/3 aktiv |
| Deployment | systemd: `timus-mcp.service` + `timus-dispatcher.service` |
| Terminal-Client | `timus_terminal.py` — parallel zum systemd-Service |

---

## 2. Was wurde heute implementiert

### Session 1 (Morgen/Mittag) — Canvas v2 + GitHub/LinkedIn

- Canvas v2 vollständig überarbeitet
- GitHub-Profil + LinkedIn-Abschnitt in README ergänzt
- Commits: Canvas v2, Terminal-Client, Profil

### Session 2 (Nachmittag) — M2 Abschluss + M3 + M4 + Memory

#### M2 — CommunicationAgent (Abschluss)
- `server/canvas_ui.py`: `"communication"` in `AGENTS`-Array ergänzt (war vergessen)
- Tests T2.1–T2.6 + IT-A/B/C: alle bestanden

#### M3 — SystemAgent (neu)
- `tools/system_tool/tool.py`: 5 read-only Tools
  - `read_log(log_name, lines)` — bekannte Logs lesen (timus/debug/shell/system)
  - `search_log(log_name, pattern, lines)` — grep-ähnliche Suche
  - `get_processes(sort_by, limit)` — Top-Prozesse via psutil
  - `get_system_stats()` — CPU, RAM, Disk, Load-Average
  - `get_service_status(service_name)` — systemctl + journalctl
- `agent/agents/system.py`: `SystemAgent(BaseAgent)`, max_iterations=12
- `agent/prompts.py`: `SYSTEM_PROMPT_TEMPLATE`
- `agent/providers.py`: system → `qwen/qwen3.5-plus-02-15` (OpenRouter)
- `main_dispatcher.py`: Aliasse `system`, `sysmon`, `log`
- `server/mcp_server.py`: `"tools.system_tool.tool"` in TOOL_MODULES
- `server/canvas_ui.py`: `"system"` in AGENTS

#### M4 — ShellAgent (neu)
- `tools/shell_tool/tool.py`: 5 Tools mit 5-Schicht-Policy
  - `run_command(command, timeout, dry_run)` — einzelner Befehl
  - `run_script(script, timeout, dry_run)` — mehrzeiliges Skript
  - `list_cron(user)` — Cron-Jobs auflisten
  - `add_cron(expression, command, dry_run=True)` — Cron-Eintrag
  - `read_audit_log(lines)` — Audit-Log lesen
- **5-Schicht-Policy:**
  1. Blacklist — `rm -rf`, `dd if=`, Fork-Bombs, `curl|bash`, `shutdown`, Wildcard-rm
  2. Whitelist-Modus — `SHELL_WHITELIST_MODE=1`
  3. Timeout — 30s Default (`SHELL_TIMEOUT`)
  4. Audit-Log — `logs/shell_audit.log`
  5. Dry-Run — `add_cron` standardmäßig nur Simulation
- `agent/agents/shell.py`: `ShellAgent(BaseAgent)`, max_iterations=10
- `agent/prompts.py`: `SHELL_PROMPT_TEMPLATE`
- `agent/providers.py`: shell → `claude-sonnet-4-6` (Anthropic)
- `main_dispatcher.py`: Aliasse `shell`, `terminal`, `bash`
- `server/mcp_server.py`: `"tools.shell_tool.tool"` in TOOL_MODULES
- `server/canvas_ui.py`: `"shell"` in AGENTS

#### Capability-Map Refactoring
- `agent/base_agent.py` — `AGENT_CAPABILITY_MAP` komplett überarbeitet
- Alle `None`-Einträge durch spezifische Tag-Listen ersetzt
- Jeder Agent sieht nur seine relevanten Tools:

```python
AGENT_CAPABILITY_MAP = {
    "executor":      ["search","web","file","filesystem","results","memory","voice","speech",
                      "document","pdf","txt","summarize","tasks","planning","automation","analysis","data"],
    "research":      ["search","web","deep_research","document","report","summarize","memory",
                      "analysis","fact_check","verification","file","results"],
    "reasoning":     ["search","web","document","report","memory","code","development",
                      "analysis","fact_check","verification","file","results"],
    "creative":      ["creative","image","document","txt","pdf","voice","speech","file","results","memory"],
    "meta":          ["meta","orchestration","planning","automation","tasks","memory","reflection",
                      "curation","skills","analysis","verification","fact_check","search","web",
                      "document","report","summarize","results","file","filesystem","system"],
    "visual":        ["browser","dom","navigation","interaction","mouse","feedback","vision","ocr",
                      "grounding","ui","ui_detection","screen","som","detection","segmentation",
                      "annotation","template_matching","opencv","verification","fallback","automation",
                      "application","adaptive","timing","memory","results"],
    "development":   ["code","development","inception","file","filesystem","search","web","memory","results","analysis","debug"],
    "data":          ["data","file","filesystem","document","pdf","xlsx","csv","analysis","fact_check","results","report","memory"],
    "document":      ["document","pdf","docx","xlsx","csv","txt","file","filesystem","results","report","memory","analysis"],
    "communication": ["document","txt","docx","file","filesystem","results","memory"],
    "system":        ["system","monitoring"],
    "shell":         ["shell"],
}
```

Tool-Anzahl nach Refactoring:
- shell: 5 | system: 14 | communication: 34 | development: 39 | data: 42 | document: 41
- visual: 43 | creative: 44 | reasoning: 46 | research: 48 | executor: 60 | meta: 68

#### Memory-Verbesserungen

**Nemotron als Kurator (`tools/curator_tool/tool.py`):**
- Vorher: gpt-4o (OpenAI)
- Jetzt: `nvidia/nemotron-3-nano-30b-a3b` via OpenRouter
- `_CURATOR_MODEL = os.getenv("CURATOR_MODEL", "nvidia/nemotron-3-nano-30b-a3b")`
- Client: `OpenAI(api_key=OPENROUTER_API_KEY, base_url="https://openrouter.ai/api/v1")`
- `response_format` entfernt (Nemotron unterstützt es nicht immer)
- Regex-Fallback: `re.search(r'\{.*\}', raw, re.DOTALL)` für JSON-Extraktion
- Neuer Parameter `agent_id` → wird an `remember` weitergegeben

**Agent-Isolation (`tools/memory_tool/tool.py`):**
- `remember_long_term(text, source, agent_id="")`: agent_id in ChromaDB-Metadaten
- `recall_long_term(query, n_results, agent_filter="")`: optionaler `where`-Filter
- MCP `remember(text, source, agent_id="")`: neuer Parameter
- MCP `recall(query, n_results, session_id, agent_filter="")`: neuer Parameter
- Rückwärtskompatibel: ohne `agent_filter` → alle Memories zurück

---

## 3. Commits des Tages (in Reihenfolge)

```
0249c89  docs: README + Session-Log für M1–M4 + Memory aktualisiert
e8a5129  feat(memory): Agent-Isolation + Nemotron als Kurator-Modell
c7423fe  refactor(agents): präzise Tool-Capability-Maps für alle 12 Agenten
dd0610a  feat(agents): M4 ShellAgent — Bash-Befehle mit mehrstufigem Policy-Layer
349329a  fix(agents): system-Agent auf Qwen3.5 Plus (OpenRouter) aktualisiert
4cb12b6  feat(agents): M3 SystemAgent — Log-Analyse, Prozesse, Systemmonitor
d79306d  feat(agents): M2 CommunicationAgent — E-Mail, Brief, LinkedIn-Posts
2e2a773  feat(M1): data + document Agenten — Meilenstein 1 abgeschlossen
08c778f  docs: Agent-Erweiterungsplan — M1–M4 + Gesamttest
32d8ee6  feat(documents): Timus kann PDF, DOCX, XLSX, CSV und TXT erstellen
ecbdfa4  feat(telegram): Bild-Fix + Datei senden/empfangen
3b32383  feat(prompts): Executor kennt HOME-Pfad und Dateisystem-Konventionen
77ea989  feat(filesystem): Vollständiger Dateisystem-Zugriff für Timus
c23d6b5  feat(canvas): Tool-Aktivitätsanzeige in der Sidebar (SSE-basiert)
7c213e7  docs: Session-Log 2026-02-22 (Canvas v2 + GitHub/LinkedIn Profil)
```

---

## 4. Vollständige Agenten-Übersicht (Stand: 2026-02-22)

| # | Agent-Typ | Klasse | Modell | Provider | Max-Iter | ENV-Vars |
|---|-----------|--------|--------|----------|----------|---------|
| 1 | executor | ExecutorAgent | gpt-5-mini | OpenAI | 30 | `FAST_MODEL`, `FAST_MODEL_PROVIDER` |
| 2 | research | DeepResearchAgent | deepseek-reasoner | DeepSeek | 8 | `RESEARCH_MODEL`, `RESEARCH_MODEL_PROVIDER` |
| 3 | reasoning | ReasoningAgent | nvidia/nemotron-3-nano-30b-a3b | OpenRouter | 15 | `REASONING_MODEL`, `REASONING_MODEL_PROVIDER` |
| 4 | creative | CreativeAgent | gpt-5.2 | OpenAI | 10 | `CREATIVE_MODEL`, `CREATIVE_MODEL_PROVIDER` |
| 5 | developer | DeveloperAgent | mercury-coder-small | Inception | 15 | `CODE_MODEL`, `CODE_MODEL_PROVIDER` |
| 6 | meta | MetaAgent | claude-sonnet-4-5-20250929 | Anthropic | 20 | `PLANNING_MODEL`, `PLANNING_MODEL_PROVIDER` |
| 7 | visual | VisualAgent | claude-sonnet-4-5-20250929 | Anthropic | 25 | `VISION_MODEL`, `VISION_MODEL_PROVIDER` |
| 8 | data | DataAgent | gpt-4o | OpenAI | 15 | `DATA_MODEL`, `DATA_MODEL_PROVIDER` |
| 9 | document | DocumentAgent | claude-sonnet-4-5-20250929 | Anthropic | 12 | `DOCUMENT_MODEL`, `DOCUMENT_MODEL_PROVIDER` |
| 10 | communication | CommunicationAgent | claude-sonnet-4-5-20250929 | Anthropic | 12 | `COMMUNICATION_MODEL`, `COMMUNICATION_MODEL_PROVIDER` |
| 11 | system | SystemAgent | qwen/qwen3.5-plus-02-15 | OpenRouter | 12 | `SYSTEM_MODEL`, `SYSTEM_MODEL_PROVIDER` |
| 12 | shell | ShellAgent | claude-sonnet-4-6 | Anthropic | 10 | `SHELL_MODEL`, `SHELL_MODEL_PROVIDER` |

---

## 5. TOOL_MODULES im MCP-Server (60+ Module, Stand mcp_server.py Zeile 157–223)

```python
TOOL_MODULES = [
    "tools.browser_tool.tool",
    "tools.summarizer.tool",
    "tools.planner.tool",
    "tools.search_tool.tool",
    "tools.tasks.tasks",
    "tools.save_results.tool",
    "tools.deep_research.tool",
    "tools.decision_verifier.tool",
    "tools.document_parser.tool",
    "tools.fact_corroborator.tool",
    "tools.report_generator.tool",
    "tools.creative_tool.tool",
    "tools.memory_tool.tool",
    "tools.maintenance_tool.tool",
    "tools.developer_tool.tool",
    "tools.file_system_tool.tool",
    "tools.document_creator.tool",          # M1
    "tools.data_tool.tool",                 # M1
    "tools.meta_tool.tool",
    "tools.reflection_tool.tool",
    "tools.init_skill_tool.tool",
    "tools.skill_manager_tool.tool",
    "tools.skill_manager_tool.reload_tool",
    "tools.curator_tool.tool",              # Nemotron-Kurator
    "tools.system_monitor_tool.tool",
    "tools.ocr_tool.tool",
    "tools.visual_grounding_tool.tool",
    "tools.mouse_tool.tool",
    "tools.visual_segmentation_tool.tool",
    "tools.debug_tool.tool",
    "tools.debug_screenshot_tool.tool",
    "tools.inception_tool.tool",
    "tools.icon_recognition_tool.tool",
    "tools.engines.object_detection_engine",
    "tools.annotator_tool.tool",
    "tools.application_launcher.tool",
    "tools.visual_browser_tool.tool",
    "tools.text_finder_tool.tool",
    "tools.smart_navigation_tool.tool",
    "tools.som_tool.tool",
    "tools.verification_tool.tool",
    "tools.verified_vision_tool.tool",
    "tools.qwen_vl_tool.tool",
    "tools.voice_tool.tool",
    "tools.skill_recorder.tool",
    "tools.mouse_feedback_tool.tool",
    "tools.hybrid_detection_tool.tool",
    "tools.visual_agent_tool.tool",
    "tools.cookie_banner_tool.tool",
    "tools.delegation_tool.tool",
    "tools.screen_change_detector.tool",
    "tools.screen_contract_tool.tool",
    "tools.opencv_template_matcher_tool.tool",
    "tools.browser_controller.tool",
    "tools.json_nemotron_tool.json_nemotron_tool",
    "tools.florence2_tool.tool",
    "tools.system_tool.tool",               # M3
    "tools.shell_tool.tool",               # M4
]
```

---

## 6. Wichtige Dateipfade

| Datei | Zweck |
|-------|-------|
| `agent/base_agent.py` | BaseAgent + AGENT_CAPABILITY_MAP |
| `agent/providers.py` | AgentModelConfig (alle 12 Agenten) |
| `agent/prompts.py` | System-Prompts (inkl. SYSTEM_PROMPT_TEMPLATE, SHELL_PROMPT_TEMPLATE) |
| `agent/dynamic_tool_mixin.py` | DynamicToolMixin — filtert Tools nach Capability-Tags |
| `agent/agents/*.py` | 12 Agent-Klassen |
| `tools/system_tool/tool.py` | 5 read-only System-Monitoring-Tools (M3) |
| `tools/shell_tool/tool.py` | 5 Shell-Tools + Blacklist + Audit-Log (M4) |
| `tools/curator_tool/tool.py` | Nemotron Memory-Kurator |
| `tools/memory_tool/tool.py` | Memory v2.1 (agent_id, agent_filter) |
| `server/mcp_server.py` | MCP-Server + TOOL_MODULES + _KNOWN_AGENTS |
| `server/canvas_ui.py` | Canvas Web-UI v2 (12 LEDs) |
| `main_dispatcher.py` | Dispatcher + AGENT_CLASS_MAP + DISPATCHER_PROMPT |
| `memory/markdown_store/USER.md` | Nutzer-Profil |
| `memory/markdown_store/SOUL.md` | Timus Persönlichkeit + Behavior Hooks |
| `memory/markdown_store/MEMORY.md` | Langzeit-Erinnerungen |
| `logs/shell_audit.log` | Audit-Log aller ShellAgent-Befehle |
| `docs/AGENT_EXPANSION_PLAN.md` | Plan für M1–M4 |
| `docs/SESSION_LOG_2026-02-22_M1_M4_AGENTS_MEMORY.md` | Session-Log dieser Session |

---

## 7. ENV-Variablen (vollständige Liste)

```bash
# LLM Provider Keys
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...
INCEPTION_API_KEY=...
DEEPSEEK_API_KEY=...
OPENROUTER_API_KEY=...         # für Qwen3.5-Plus, Nemotron, Reasoning

# Services
DATAFORSEO_USER=...
DATAFORSEO_PASS=...
TELEGRAM_BOT_TOKEN=...
TELEGRAM_ALLOWED_IDS=...

# Agenten-Modelle (alle mit Default-Fallback)
FAST_MODEL=gpt-5-mini
RESEARCH_MODEL=deepseek-reasoner
REASONING_MODEL=nvidia/nemotron-3-nano-30b-a3b
REASONING_MODEL_PROVIDER=openrouter
CREATIVE_MODEL=gpt-5.2
CODE_MODEL=mercury-coder-small
PLANNING_MODEL=claude-sonnet-4-5-20250929
VISION_MODEL=claude-sonnet-4-5-20250929
DATA_MODEL=gpt-4o
DOCUMENT_MODEL=claude-sonnet-4-5-20250929
COMMUNICATION_MODEL=claude-sonnet-4-5-20250929
SYSTEM_MODEL=qwen/qwen3.5-plus-02-15
SYSTEM_MODEL_PROVIDER=openrouter
SHELL_MODEL=claude-sonnet-4-6
SHELL_MODEL_PROVIDER=anthropic

# Memory-Kurator
CURATOR_MODEL=nvidia/nemotron-3-nano-30b-a3b  # via OPENROUTER_API_KEY

# Shell-Agent Policy
SHELL_WHITELIST_MODE=0         # 1 = nur Whitelist-Befehle
SHELL_TIMEOUT=30               # Sekunden

# Vision + Florence-2
FLORENCE2_ENABLED=true
FLORENCE2_MODEL=microsoft/Florence-2-large-ft
OPENROUTER_VISION_MODEL=qwen/qwen3.5-plus-02-15
LOCAL_LLM_URL=                 # optional
LOCAL_LLM_MODEL=
HF_TOKEN=hf_...

# System-Konfiguration
ACTIVE_MONITOR=1
USE_MOUSE_FEEDBACK=1
AUTO_OPEN_FILES=true
TIMUS_LIVE_STATUS=true

# Heartbeat / Autonomie
HEARTBEAT_ENABLED=true
HEARTBEAT_INTERVAL_MINUTES=15
MONITOR_ENABLED=true
```

---

## 8. Systemarchitektur (Kurzübersicht)

```
[User-Input] (CLI / Telegram / Canvas-Chat / Terminal-Client)
     ↓
main_dispatcher.py
  ├── Query-Sanitizing
  ├── Intent-Analyse (Keyword + LLM)
  ├── Policy-Gate
  └── AGENT_CLASS_MAP → Agent-Auswahl
         ↓
agent/base_agent.py  (DynamicToolMixin → filtert via AGENT_CAPABILITY_MAP)
  ├── Working-Memory-Injektion
  ├── Recall-Fast-Path
  └── Tool-Loop (max_iterations)
         ↓
MCP-Server :5000 (FastAPI + JSON-RPC)
  ├── 60+ Tools (TOOL_MODULES)
  ├── SSE Events (agent_status, tool_start, tool_done, thinking)
  └── Canvas Web-UI (/canvas/ui)
         ↓
Memory-System v2.1
  ├── SessionMemory (RAM, letzte 20 Nachrichten)
  ├── SQLite (Fakten, Zusammenfassungen)
  ├── ChromaDB (Embeddings + agent_id-Isolation)
  └── MarkdownStore (USER.md, SOUL.md, MEMORY.md)
```

---

## 9. Gesamttest-Ergebnisse (GT-1 bis GT-6)

| Test | Prüft | Ergebnis |
|------|-------|---------|
| GT-1 | Tool-Registry lädt alle TOOL_MODULES ohne Fehler | ✅ |
| GT-2 | Alle 12 Agenten instanziierbar, Modell-Config korrekt | ✅ |
| GT-3 | Canvas SSE — `agent_status` + `thinking` Events vorhanden | ✅ |
| GT-4 | Provider-Config für alle 12 Agenten (ENV-Override-fähig) | ✅ |
| GT-5 | Dispatcher-Routing — alle 12 Agenten erreichbar | ✅ |
| GT-6 | Memory-Isolation (agent_id in ChromaDB) + Nemotron-Aufruf | ✅ |

---

## 10. Bekannte Punkte / Offene Themen

| Thema | Status | Notiz |
|-------|--------|-------|
| `.env` überschreibt research/dev Modelle | Bekannt, gewollt | gpt-4o aus .env statt deepseek-reasoner / mercury-coder-small |
| Meta-Agent sieht `system` Tools | Gewollt | Meta ist Orchestrator — braucht Log-Übersicht |
| Shell-Tools nur für ShellAgent | Korrekt | `"shell"` Capability nur in ShellAgent-Map |
| Nemotron JSON-Fallback | Aktiv | `re.search(r'\{.*\}', raw, re.DOTALL)` für Markdown-Wrapping |
| ChromaDB rückwärtskompatibel | Ja | alte Entries haben kein `agent_id` → `unknown` |
| Florence-2 braucht GPU | Optional | `FLORENCE2_ENABLED=false` für CPU-Only-Betrieb |

---

## 11. Nächste mögliche Schritte

1. **M5 — VoiceAgent**: TTS/STT Integration als eigener Agent (Inworld.AI / Whisper)
2. **ShellAgent Whitelist**: Vordefinierte Whitelist für häufige sichere Befehle
3. **Memory Cleanup**: Veraltete Einträge automatisch decay-en lassen
4. **Agent-übergreifende Delegation testen**: MetaAgent → SystemAgent → ShellAgent Pipeline
5. **Capability-Map testen**: Unit-Tests für jede Agent/Tool-Kombination
6. **DataAgent Plots**: Matplotlib/Plotly Integration für CSV-Visualisierung
7. **CommunicationAgent E-Mail-Versand**: SMTP-Tool ergänzen

---

## 12. Start-Befehle (für nach dem Neustart)

```bash
# Conda-Umgebung aktivieren
conda activate timus

# Option A: Alle drei Komponenten automatisch
./start_timus_three_terminals.sh

# Option B: Manuell in 3 Terminals
# Terminal 1 — MCP-Server
python server/mcp_server.py

# Terminal 2 — Dispatcher
python main_dispatcher.py

# Terminal 3 — Canvas aufrufen
xdg-open http://localhost:5000/canvas/ui
# oder Terminal-Client
python timus_terminal.py
```

---

*Tagesbericht erstellt: 2026-02-22 | Letzter Commit: 0249c89*
