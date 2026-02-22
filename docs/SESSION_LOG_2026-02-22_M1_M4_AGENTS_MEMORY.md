# Session-Log 2026-02-22 — Agenten-Meilensteine M1–M4 + Memory-Verbesserungen

**Datum:** 2026-02-22
**Schwerpunkte:** M2 Abschluss, M3 SystemAgent, M4 ShellAgent, Capability-Map Refactoring, Memory-Isolation, Nemotron-Kurator, Gesamttest, README/Doku

---

## Zusammenfassung

In dieser Session wurden vier neue Agenten-Meilensteine fertiggestellt und das Gesamtsystem auf 12 spezialisierte Agenten erweitert.

---

## M2 — CommunicationAgent (Abschluss)

- `server/canvas_ui.py`: `"communication"` in `AGENTS`-Array hinzugefügt (war in vorheriger Session vergessen worden)
- Tests T2.1–T2.6 + IT-A/B/C: alle bestanden
- Commit: `feat(agents): M2 CommunicationAgent`

---

## M3 — SystemAgent

**Phase 3.1 — tools/system_tool/tool.py (neu)**

5 read-only System-Monitoring-Tools:
- `read_log(log_name, lines)` — liest bekannte Logs (timus, debug, shell, system)
- `search_log(log_name, pattern, lines)` — grep-ähnliche Suche in Logs
- `get_processes(sort_by, limit)` — Top-Prozesse via psutil
- `get_system_stats()` — CPU, RAM, Disk, Load-Average
- `get_service_status(service_name)` — systemctl Status + letzte Journalctl-Zeilen

**Phase 3.2 — agent/agents/system.py (neu)**
- `SystemAgent(BaseAgent)` mit `SYSTEM_PROMPT_TEMPLATE`, max_iterations=12

**Phase 3.3 — Integration**
- `providers.py`: system → qwen/qwen3.5-plus-02-15 (OpenRouter)
- `main_dispatcher.py`: AGENT_CLASS_MAP + DISPATCHER_PROMPT erweitert
- `server/mcp_server.py`: `"tools.system_tool.tool"` in TOOL_MODULES
- `server/canvas_ui.py`: `"system"` in AGENTS

Tests T3.1–T3.7 + IT-D/E/F: alle bestanden
Commit: `feat(agents): M3 SystemAgent`

**Modell-Update:**
- System-Agent war initial auf gpt-4o — user sagte "veraltet"
- Gewechselt zu `qwen/qwen3.5-plus-02-15` (OpenRouter, 2026-02-15)
- Commit: `fix(agents): system-Agent auf Qwen3.5 Plus (OpenRouter) aktualisiert`

---

## M4 — ShellAgent

**Phase 4.1 — tools/shell_tool/tool.py (neu)**

5-Schicht-Sicherheits-Policy:
1. **Blacklist** — Regex-Pattern für `rm -rf`, `dd if=`, Fork-Bombs, `shutdown`, `curl|bash`, Wildcard-rm
2. **Whitelist-Modus** — `SHELL_WHITELIST_MODE=1` erlaubt nur explizit gelistete Befehle
3. **Timeout** — 30s Default, konfigurierbar via `SHELL_TIMEOUT`
4. **Audit-Log** — `logs/shell_audit.log` — jeder Befehl wird protokolliert
5. **Dry-Run** — `add_cron()` nur simuliert standardmäßig (`dry_run=True`)

Tools:
- `run_command(command, timeout, dry_run)` — einzelner Shell-Befehl
- `run_script(script, timeout, dry_run)` — mehrzeiliges Skript (temp-Datei)
- `list_cron(user)` — Cron-Jobs auflisten
- `add_cron(expression, command, dry_run)` — Cron-Eintrag hinzufügen
- `read_audit_log(lines)` — Audit-Log lesen

**Phase 4.2 — agent/agents/shell.py (neu)**
- `ShellAgent(BaseAgent)` mit `SHELL_PROMPT_TEMPLATE`, max_iterations=10

**Phase 4.3 — Integration**
- `providers.py`: shell → claude-sonnet-4-6 (Anthropic)
- `main_dispatcher.py`: AGENT_CLASS_MAP + DISPATCHER_PROMPT (Aliasse: terminal, bash)
- `server/mcp_server.py`: `"tools.shell_tool.tool"` in TOOL_MODULES
- `server/canvas_ui.py`: `"shell"` in AGENTS

Tests T4.1–T4.13: alle bestanden
Commit: `feat(agents): M4 ShellAgent`

---

## Capability-Map Refactoring

**Problem:** Alle Agenten mit `None` bekamen alle 80+ Tools in ihrem Prompt — ineffizient, verwirrend.

**Lösung:** `AGENT_CAPABILITY_MAP` in `base_agent.py` — jeder Agent bekommt nur seine relevanten Capability-Tags:

| Agent | Tags | Tools |
|-------|------|-------|
| shell | ["shell"] | 5 |
| system | ["system", "monitoring"] | 14 |
| communication | 7 Tags | 34 |
| development | 9 Tags | 39 |
| data | 12 Tags | 42 |
| document | 12 Tags | 41 |
| visual | 21 Tags | 43 |
| creative | 9 Tags | 44 |
| reasoning | 12 Tags | 46 |
| research | 12 Tags | 48 |
| executor | 17 Tags | 60 |
| meta | 21 Tags | 68 (Orchestrator) |

Der `DynamicToolMixin` filtert die Tool-Registry anhand der Tags — Agenten sehen nur ihre relevanten Tools.

Commit: `refactor(agents): präzise Tool-Capability-Maps für alle 12 Agenten`

---

## Memory-System Verbesserungen

### Nemotron als Kurator-Modell

**Problem:** `curator_tool` nutzte gpt-4o — user sagte "veraltet, Nemotron ist besser für strukturierte Entscheidungen".

**Änderungen in `tools/curator_tool/tool.py`:**
- OpenAI-Client → OpenRouter-Client (`base_url="https://openrouter.ai/api/v1"`)
- `_CURATOR_MODEL = os.getenv("CURATOR_MODEL", "nvidia/nemotron-3-nano-30b-a3b")`
- `response_format` entfernt (Nemotron unterstützt es ggf. nicht)
- Regex-Fallback für JSON-Extraktion: `re.search(r'\{.*\}', raw, re.DOTALL)`
- Neuer Parameter `agent_id` — wird an `remember` weitergegeben

### Agent-Isolation in ChromaDB

**Problem:** Alle 12 Agenten schrieben in denselben ChromaDB-Pool ohne Unterscheidung.

**Änderungen in `tools/memory_tool/tool.py`:**
- `remember_long_term(text, source, agent_id="")`: `agent_id` in ChromaDB-Metadaten
- `recall_long_term(query, n_results, agent_filter="")`: optionaler `where`-Filter
- MCP `remember(text, source, agent_id="")`: neuer Parameter
- MCP `recall(query, n_results, session_id, agent_filter="")`: neuer Parameter

Rückwärtskompatibel: ohne `agent_filter` werden alle Memories zurückgegeben.

Commit: `feat(memory): Agent-Isolation + Nemotron als Kurator-Modell`

---

## Gesamttest (GT-1 bis GT-6)

| Test | Beschreibung | Ergebnis |
|------|-------------|---------|
| GT-1 | Tool Registry (80+ Tools, alle Module laden) | ✅ |
| GT-2 | Alle 12 Agenten instanziierbar | ✅ |
| GT-3 | Canvas SSE Events (agent_status, thinking) | ✅ |
| GT-4 | Provider-Konfiguration (alle 12 Agenten) | ✅ |
| GT-5 | Dispatcher-Routing (12 Agenten erkennbar) | ✅ |
| GT-6 | Memory-Isolation + Nemotron-Kurator | ✅ |

---

## Commits dieser Session

1. `feat(agents): M2 CommunicationAgent`
2. `feat(agents): M3 SystemAgent`
3. `fix(agents): system-Agent auf Qwen3.5 Plus (OpenRouter) aktualisiert`
4. `feat(agents): M4 ShellAgent`
5. `refactor(agents): präzise Tool-Capability-Maps für alle 12 Agenten`
6. `feat(memory): Agent-Isolation + Nemotron als Kurator-Modell`
7. `docs: README und Projektstruktur für M1–M4 + Memory aktualisiert`

---

## Stand nach dieser Session

- **12 spezialisierte Agenten** vollständig implementiert und getestet
- **Capability-Map** präzise: jeder Agent sieht nur seine relevanten Tools
- **Memory** mit Agent-Isolation und Nemotron-Kurator
- **Canvas v2** mit 12 LEDs, SSE, Chat, Upload
- **Gesamttest** GT-1 bis GT-6: alle bestanden
