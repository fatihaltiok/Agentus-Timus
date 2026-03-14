# Timus — Architektur-Übersicht

**Hinweis:** Diese Datei ist die kurze Architekturuebersicht. Die aktuelle, ausfuehrliche Systemdokumentation liegt in [TIMUS_AUSFUEHRLICHE_SYSTEMDOKUMENTATION_2026-03-14.md](/home/fatih-ubuntu/dev/timus/docs/TIMUS_AUSFUEHRLICHE_SYSTEMDOKUMENTATION_2026-03-14.md). Der kompakte Begleitbericht liegt in [BERICHT_2026-03-14_TIMUS_SYSTEMSTATUS_UND_ARCHITEKTUR.md](/home/fatih-ubuntu/dev/timus/docs/BERICHT_2026-03-14_TIMUS_SYSTEMSTATUS_UND_ARCHITEKTUR.md).

**Version:** v4.8+ (Stand 2026-03-13)
**Stack:** Python 3.11 · FastAPI · SQLite WAL · Qdrant/Chroma-orientierte Memory-Schichten · Telegram · systemd · Caddy · Android-App-Prototyp

---

## Überblick

Timus ist ein **selbst-überwachendes, selbst-heilendes, selbst-planendes Multi-Agenten-System**.
Alle Komponenten laufen lokal auf einer einzigen Maschine und kommunizieren über einen zentralen MCP-Server (JSON-RPC 2.0, Port 5000).

```
Nutzer
  │
  ├─ Telegram (@agentustimus_bot) ──┐
  ├─ Canvas Web-UI  (Port 5000/ui) ─┤
  └─ Terminal-Client (timus_terminal.py) ─┐
                                    │    │
                          ┌─────────▼────▼──────────┐
                          │     MCP-Server           │
                          │  server/mcp_server.py    │
                          │  FastAPI · JSON-RPC 2.0  │
                          │  80+ Tools registriert   │
                          └──────────┬───────────────┘
                                     │
                          ┌──────────▼───────────────┐
                          │    main_dispatcher.py    │
                          │  LLM + Keyword-Routing   │
                          │  → 13 Agenten            │
                          └──────────┬───────────────┘
                                     │
              ┌──────────────────────┼──────────────────────┐
              ▼                      ▼                      ▼
       Agent-Registry         AutonomousRunner        SoulEngine
    (13 Agenten, Tools)    (Heartbeat alle 15 Min)   (Persönlichkeit)
```

---

## Schicht-Modell

```
┌─────────────────────────────────────────────────────────┐
│  Schicht 5: Autonomie-Motoren (M1–M16)                  │
│  GoalGenerator · LongTermPlanner · SelfHealingEngine    │
│  FeedbackEngine · EmailAutonomyEngine · ToolGenerator   │
├─────────────────────────────────────────────────────────┤
│  Schicht 4: Orchestrierung                              │
│  autonomous_runner.py · CuriosityEngine · AmbientCtx   │
├─────────────────────────────────────────────────────────┤
│  Schicht 3: Agenten (13 Stück)                         │
│  Executor · Meta · Visual · Shell · Research · ...     │
├─────────────────────────────────────────────────────────┤
│  Schicht 2: Tools (80+ Module)                         │
│  Vision · Browser · Research · Memory · Shell · ...    │
├─────────────────────────────────────────────────────────┤
│  Schicht 1: Infrastruktur                               │
│  MCP-Server · SQLite WAL · ChromaDB · Telegram          │
└─────────────────────────────────────────────────────────┘
```

---

## Kernkomponenten

### MCP-Server (`server/mcp_server.py`)

- FastAPI-Anwendung auf Port 5000
- JSON-RPC 2.0 Endpunkt (`POST /`) für alle 80+ Tool-Aufrufe
- Server-Sent Events (`GET /events`) für Canvas-Echtzeit-Updates
- Lifespan-Hook: registriert alle 13 Agenten beim Start
- REST-Endpunkte: `/autonomy/*`, `/blackboard`, `/goals/tree`, `/triggers`, `/settings`

### Dispatcher (`main_dispatcher.py` v3.4)

- Eingehende Anfragen werden per **LLM + Keyword-Matching** geroutet
- Kennt alle 13 Agenten und ihre Fähigkeiten
- Gibt Autonomie-Kontext (Ziele, Blackboard, Reflexions-Erkenntnisse) als Zusatz-Prompt mit
- Fallback: ExecutorAgent bei unklarem Routing

### Agent-Registry (`agent/agent_registry.py`)

```python
# Sequenziell
result = await registry.delegate(from_agent="meta", to_agent="research", task="...")

# Parallel (Fan-Out)
result = await registry.delegate_parallel(tasks=[
    {"task_id": "t1", "agent": "research", "task": "..."},
    {"task_id": "t2", "agent": "developer", "task": "..."},
], max_parallel=3)
```

**Garantien:** Timeout (120s), exponentielles Backoff, Loop-Prevention (MAX_DEPTH=3), frische Instanz pro Task, SQLite WAL-Modus für parallele Reads.

---

## Die 13 Agenten

| Agent | Modell | Spezialgebiet |
|-------|--------|---------------|
| ExecutorAgent | claude-haiku-4-5 | Schnelle Tasks, Dateien, Websuche (60 Tools) |
| MetaAgent v2 | z-ai/glm-5 | Orchestrator — sequenziell + parallel (68 Tools) |
| DeepResearchAgent | deepseek-reasoner | Tiefenrecherche, PDF-Berichte (48 Tools) |
| ReasoningAgent | nvidia/nemotron-3-nano-30b-a3b | Multi-Step-Analyse, Debugging (46 Tools) |
| CreativeAgent | gpt-5.2 | Bildgenerierung (DALL-E), Texte (44 Tools) |
| DeveloperAgent | mercury-coder-small | Code-Generierung, AST-Validierung (39 Tools) |
| VisualAgent | claude-sonnet-4-5 | Desktop-Automatisierung, SoM (43 Tools) |
| VisualNemotronAgent v4 | Qwen3.5 Plus + Florence-2 | Komplexe Desktop-Automatisierung |
| DataAgent v2 | deepseek/deepseek-v3.2 | CSV/Excel/JSON, Statistiken (42 Tools) |
| CommunicationAgent | claude-sonnet-4-5 | E-Mails, DOCX/TXT Export (34 Tools) |
| SystemAgent | qwen/qwen3.5-plus-02-15 | Logs, Prozesse, Service-Status read-only (14 Tools) |
| ShellAgent v2 | claude-sonnet-4-6 | Shell mit 5-Schicht-Policy (5 Tools) |
| ImageAgent | qwen/qwen3.5-plus-02-15 | Bild-Analyse, Base64 → Vision (1 Tool) |

---

## Autonomie-Motoren (M1–M16)

Alle Motoren laufen im `AutonomousRunner` — Heartbeat alle 15 Minuten.

### Planung & Steuerung

| Motor | Datei | Funktion |
|-------|-------|---------|
| **M1** GoalGenerator | `orchestration/goal_generator.py` | Ziele aus Memory + Curiosity + Events generieren |
| **M2** LongTermPlanner | `orchestration/long_term_planner.py` | 3-Horizont-Planung (7d/30d/90d), Commitments |
| **M2** ReplanningEngine | `orchestration/replanning_engine.py` | Erkennt Commitment-Verletzungen, erstellt neue Pläne |
| **M5** AutonomyScorecard | `orchestration/autonomy_scorecard.py` | Score 0–100 aus 5 Pillar-Werten, Control-Loop |
| **M11** GoalQueueManager | `orchestration/goal_queue_manager.py` | Hierarchische Ziele, Sub-Goals, Meilenstein-Rollup |

### Selbst-Heilung & Sicherheit

| Motor | Datei | Funktion |
|-------|-------|---------|
| **M3** SelfHealingEngine | `orchestration/self_healing_engine.py` | Incident-Erkennung, Circuit-Breaker, systemd-Restart |
| **M6** ChangeControl | `orchestration/autonomy_change_control.py` | Change-Request-Flow + Audit-Log |
| **M7** HardeningEngine | `orchestration/autonomy_hardening_engine.py` | Rollout-Gate (green/yellow/red) |

### Kognition & Lernen

| Motor | Datei | Funktion |
|-------|-------|---------|
| **M8** SessionReflection | `orchestration/session_reflection.py` | Idle-Erkennung → LLM-Reflexion → Hook-Anpassung |
| **M9** AgentBlackboard | `memory/agent_blackboard.py` | TTL-basierter Shared Memory für alle Agenten |
| **M10** ProactiveTriggers | `orchestration/proactive_triggers.py` | Zeitgesteuerte Routinen (±14-Min-Fenster) |
| **M12** SelfImprovement | `orchestration/self_improvement_engine.py` | Tool-Erfolgsrate + Routing-Konfidenz, wöchentlich |
| **M15** AmbientContext | `orchestration/ambient_context_engine.py` | Push-Autonomie ohne User-Input (File/Goal/System-Watcher) |
| **M16** FeedbackEngine | `orchestration/feedback_engine.py` | 👍/👎/🤷 → Soul-Hook-Gewichtung, decay täglich |

### Externe Aktionen

| Motor | Datei | Funktion |
|-------|-------|---------|
| **M13** ToolGenerator | `orchestration/tool_generator_engine.py` | AST-Check → Telegram-Review → importlib-Aktivierung |
| **M14** EmailAutonomy | `orchestration/email_autonomy_engine.py` | Whitelist + Confidence-Guard, SMTP/msgraph, Telegram-Approval |

---

## Memory-System

```
Memory v2.2
│
├── SessionMemory (RAM)
│   ├── Letzte 50 Nachrichten
│   ├── Auto-Summarize alle 20 Nachrichten
│   └── Entitäten-Tracking (Pronomen-Auflösung)
│
├── PersistentMemory (SQLite + WAL)
│   ├── Fakten mit Vertrauenswert
│   ├── Konversations-Zusammenfassungen
│   └── User-Profile + Präferenzen
│
├── SemanticMemory (ChromaDB)
│   ├── Embedding-Suche (16.000 Token Kontext)
│   ├── Hybrid: ChromaDB + FTS5 (Keywords)
│   └── agent_id-Isolation (recall per Agent filterbar)
│
├── MarkdownStore (bidirektional)
│   ├── USER.md  — Nutzerpräferenzen
│   ├── SOUL.md  — Soul-Achsen + Drift-History (YAML-Frontmatter)
│   └── MEMORY.md — Projektgedächtnis
│
└── ReflectionEngine
    ├── Post-Task Analyse → Learnings speichern
    └── soul_engine.apply_drift() nach jeder Reflexion
```

---

## Soul Engine

Timus hat eine dynamische Persönlichkeit mit **5 Achsen** (Wert 5–95):

| Achse | Beschreibung |
|-------|-------------|
| `confidence` | Wie direkt/sicher Timus antwortet |
| `formality` | Förmlich vs. locker |
| `humor` | Ernsthaft vs. verspielt |
| `verbosity` | Kompakt vs. ausführlich |
| `risk_appetite` | Vorsichtig vs. experimentierfreudig |

**Drift:** 7 Signale (Fehler, Erfolg, Lob, Kritik, ...) verschieben Achsen um ±0.1 × Dämpfung.
**M16-Integration:** 👍/👎/🤷 Feedback ändert `behavior_hooks`-Gewichte → beeinflusst zukünftige Aktionen.

---

## CuriosityEngine

Proaktive Wissensdurchsuchung — läuft im Hintergrund mit **Fuzzy Sleep (3–14h zufällig)**:

```
Topic-Extraktion (SQLite 72h)
        ↓
LLM Query-Generierung (Edge-Suchanfrage 2026)
        ↓
DataForSEO Web-Suche (Top-3 Ergebnisse)
        ↓
Gatekeeper-LLM (Score 0–10 · ≥7 = senden)
        ↓
Duplikat-Check (14 Tage · max. 2/Tag)
        ↓
Telegram Push mit 👍/👎/🤷 Feedback-Buttons (M16)
```

---

## Telegram-Integration

Der Bot `@agentustimus_bot` ist das primäre Kontroll-Interface:

| Callback-Typ | Handler | Aktion |
|-------------|---------|--------|
| `fb: positive/negative/neutral` | M16 FeedbackEngine | Soul-Hook-Gewichtung |
| `type: email_approve` | M14 EmailAutonomyEngine | SMTP-Sendung ausführen |
| `type: email_reject` | M14 EmailAutonomyEngine | Anfrage verwerfen |
| `type: tool_approve` | M13 ToolGeneratorEngine | importlib-Aktivierung |
| `type: tool_reject` | M13 ToolGeneratorEngine | Tool verwerfen |

Alle Callbacks werden in `gateway/telegram_gateway.py → handle_callback_query()` dispatcht.

---

## Lean 4 Verifikation (CI-Gate)

Jeder Commit läuft durch einen Pre-Commit-Hook der **12 Mathlib-Specs** + **27 CiSpecs.lean-Theoreme** verifiziert.

```
lean/CiSpecs.lean  — 27 Theoreme (alle via `by omega`, kein Mathlib nötig)
                      Theorem 1–14:  Deep Research Invarianten
                      Theorem 15–23: M15/M16 Ambient + Feedback
                      Theorem 24–25: M14 Whitelist + Confidence
                      Theorem 26–27: M13 Code-Länge + Approval-Guard
```

Schlägt die Lean-Verifikation fehl → kein Commit möglich.

---

## Datenbanken

| Datei | Inhalt |
|-------|--------|
| `data/timus_memory.db` | session_reflections, improvement_suggestions, agent_blackboard |
| `data/task_queue.db` | tasks, goals, goal_edges, proactive_triggers, tool_analytics, feedback_events |
| `data/autonomy.db` | incidents, healing_actions, scorecard_snapshots |
| `data/curiosity.db` | curiosity_sent (Duplikat-Schutz) |
| `memory_db/` | ChromaDB — semantisches Embedding-Memory |

---

## Verzeichnisstruktur

```
timus/
├── agent/
│   ├── agents/              # 13 spezialisierte Agenten
│   ├── agent_registry.py    # delegate() + delegate_parallel()
│   ├── base_agent.py        # BaseAgent + Blackboard-Kontext-Injektion
│   └── providers.py         # 7 LLM-Provider
├── orchestration/
│   ├── autonomous_runner.py          # Heartbeat + alle Engine-Hooks
│   ├── curiosity_engine.py           # Proaktive Wissensdurchsuchung
│   ├── ambient_context_engine.py     # M15: Push-Autonomie
│   ├── feedback_engine.py            # M16: Feedback Loop
│   ├── email_autonomy_engine.py      # M14: E-Mail-Policy
│   ├── tool_generator_engine.py      # M13: Runtime-Tool-Generierung
│   ├── session_reflection.py         # M8: End-of-Session-Analyse
│   ├── goal_generator.py             # M1
│   ├── long_term_planner.py          # M2
│   ├── self_healing_engine.py        # M3
│   └── autonomy_scorecard.py         # M5
├── memory/
│   ├── memory_system.py     # 4-Ebenen Memory v2.2
│   ├── soul_engine.py       # 5 Achsen + WeightedHooks (M16)
│   ├── agent_blackboard.py  # M9: TTL Shared Memory
│   └── qdrant_provider.py   # ChromaDB Drop-in für Qdrant
├── tools/                   # 80+ Tool-Module (jeweils tool.py + __init__.py)
│   ├── email_autonomy_tool/ # M14
│   ├── tool_generator_tool/ # M13
│   ├── deep_research/       # v7.0 — ArXiv + PDF + Language-Detection
│   └── ...
├── gateway/
│   ├── telegram_gateway.py  # Bot + Callback-Dispatcher (M13/M14/M16)
│   └── system_monitor.py    # CPU/RAM/Disk-Alerts
├── server/
│   ├── mcp_server.py        # FastAPI, Port 5000, JSON-RPC 2.0
│   └── canvas_ui.py         # Web-UI v3 (3-Spalten, Cytoscape, SSE)
├── utils/
│   ├── telegram_notify.py   # send_telegram() + send_with_feedback() (M16)
│   ├── smtp_email.py        # SMTP_SSL + IMAP_SSL Backend (M14)
│   └── ...
├── lean/
│   └── CiSpecs.lean         # 27 Theoreme, CI-Gate
├── tests/                   # 300+ Tests
├── main_dispatcher.py       # Routing-Einstiegspunkt
├── timus-mcp.service        # systemd: MCP-Server
└── timus-dispatcher.service # systemd: Autonomie-Loop
```

---

## Laufzeit

```
systemd
├── timus-mcp.service         → server/mcp_server.py  (Port 5000)
└── timus-dispatcher.service  → orchestration/autonomous_runner.py
                                  + gateway/telegram_gateway.py
                                  + CuriosityEngine (Fuzzy Sleep 3–14h)
```

Beide Services starten automatisch beim Boot und werden bei Absturz von systemd neu gestartet (Teil des M3 Self-Healing).
