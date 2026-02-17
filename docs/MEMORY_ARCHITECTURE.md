# Memory Architecture Freeze (Milestone 0)

Stand: 2026-02-17
Owner: Timus Core

## Ziel
Ein dynamisches, persistentes Gedaechtnis mit:
- Kurzzeitkontext (Working Memory)
- Langzeitkontext (episodisch + semantisch)
- Relevanz-basiertem Abruf statt statischer Speicherung

## Ist-Analyse (Code-Realitaet)

### Laufzeitpfad (Agent -> Tooling)
1. `main_dispatcher.py` routed den Query auf einen Agenten.
2. `agent/base_agent.py` ruft Tools via MCP JSON-RPC auf.
3. `server/mcp_server.py` laedt Tool-Module in `registry_v2`.
4. Memory-Tools kommen aus `tools/memory_tool/tool.py`.

### Beobachtete Konflikte
- Es existieren zwei Memory-Implementierungen:
  - `memory/memory_system.py` (reicher Kern inkl. Hybrid Search, Markdown Sync, Self-Model)
  - `tools/memory_tool/tool.py` (eigener MemoryManager + MCP Endpunkte)
- Reflection nutzt den Kernpfad (`memory/reflection_engine.py` -> `memory/memory_system.py`),
  waehrend Agent-Toolcalls ueber MCP den Toolpfad nutzen (`tools/memory_tool/tool.py`).
- Folge: doppelte Ownership und inkonsistente Semantik (Session-Kontext, Recall-Signal, Persistenzfluss).

## Freeze-Entscheidung (verbindlich)

### Single Source of Truth
`memory/memory_system.py` ist der **kanonische Memory-Kern**.

### Rollenaufteilung
- `memory/memory_system.py`
  - Domain-Logik, Persistenzmodell, Relevanzlogik, Kontextbau, Hybrid-Retrieval.
- `tools/memory_tool/tool.py`
  - MCP-Adapter/Transportschicht fuer Tool-Aufrufe.
  - Keine neue, davon abweichende Memory-Domainlogik.
- `memory/reflection_engine.py`
  - schreibt Learnings in den kanonischen Kern.
- `agent/base_agent.py`
  - konsumiert Memory ueber MCP-Tools (`recall`, `remember`, etc.).

## Architektur-Regeln ab Milestone 0

1. Neue Memory-Features nur im Kern (`memory/memory_system.py`) entwickeln.
2. `tools/memory_tool/tool.py` darf nur adaptieren/validieren, nicht semantisch divergieren.
3. Abrufpfade fuer User-Recall muessen den gleichen Datenraum nutzen wie Reflection-Writes.
4. Session-Logging muss deterministisch vom System erfolgen (nicht von LLM-Toolwahl abhaengig).

## Naechster Meilenstein (Milestone 1)

Deterministisches Interaction-Logging:
- Jede User/Assistant-Interaktion wird zentral persistiert.
- Memory-Schreiben entkoppelt von Agent-Tool-Entscheidungen.
- Einheitliche Session-ID und Event-Timeline als Grundlage fuer dynamische Relevanz.

## Milestone 1 Umsetzungsstand

Umgesetzt am 2026-02-17:
- Neue persistente Event-Tabelle `interaction_events` im kanonischen Kern.
- Dispatcher schreibt pro Runde deterministisch in den Kern (unabhaengig von Tool-Wahl).
- Status-Heuristik (`completed`/`error`/`cancelled`) wird mitgespeichert.
- Session-ID aus Dispatcher-Runde wird explizit als Event-Schluessel persistiert.

Code-Referenzen:
- `memory/memory_system.py`: `interaction_events` Schema + `store_interaction_event()` + `log_interaction_event()`
- `main_dispatcher.py`: `_log_interaction_deterministic()` zentral in `run_agent(...)` (inkl. Aufrufe aus Voice/Hybrid Entry-Points)

## Milestone 2 Umsetzungsstand

Umgesetzt am 2026-02-17:
- Working-Memory-Layer mit hartem Budget (`max_chars`, `max_related`, `max_recent_events`).
- Prompt-Injektion vor dem ersten LLM-Call im BaseAgent.
- Graceful Fallback bei fehlendem Memory-System.

Code-Referenzen:
- `memory/memory_system.py`: `build_working_memory_context(...)`
- `agent/base_agent.py`: `_build_working_memory_context(...)` + `_inject_working_memory_into_task(...)`

## Milestone 3 Umsetzungsstand

Umgesetzt am 2026-02-17:
- Dynamische Relevanzbewertung für Kurzzeit-Events und Langzeit-Memory.
- Zeitlicher Decay (Half-Life) für recency-sensitive Scores.
- Adaptive Budget-Verteilung je nach Query-Typ (temporal vs. profilbezogen).

Code-Referenzen:
- `memory/memory_system.py`: `_score_interaction_event(...)`, `_score_related_memory(...)`, `_adapt_working_memory_targets(...)`

## Milestone 4 Umsetzungsstand

Umgesetzt am 2026-02-17:
- End-to-End deterministisches Logging in `run_agent(...)` (nicht nur CLI-main loop).
- Runtime-Telemetrie pro Agent-Run als Event-Metadaten persistiert.
- Working-Memory-Build-Stats im kanonischen Memory-Kern verfügbar.
- Runtime-Memory-Snapshot pro Event (Dialogzustand + Session-Blick) in Metadaten.
- Recall-Meta und Session-ID in Agent-Telemetrie aufgenommen.

Code-Referenzen:
- `main_dispatcher.py`: `run_agent(...)` + `_log_interaction_deterministic(...)`
- `agent/base_agent.py`: `get_runtime_telemetry(...)`
- `memory/memory_system.py`: `get_last_working_memory_stats(...)` + `get_runtime_memory_snapshot(...)`

## Milestone 5 Umsetzungsstand

Umgesetzt am 2026-02-17:
- Quality-Gate Tests für deterministisches Dispatcher-Logging in kritischen Pfaden.
- Regressionstest für Metadata-Merge im zentralen Interaction-Logger.
- Regressionstest für Working-Memory Runtime-Stats (inkl. Budgetgrenze bei Status `ok`).
- Erweiterte Gates für dynamische Relevanz-Flags (`focus_terms_count`, `prefer_unresolved`).
- Snapshot-Gates: `memory_snapshot` wird in Event-Metadaten erwartet und validiert.

Code-Referenzen:
- `tests/test_milestone5_quality_gates.py`
- `tests/test_milestone6_e2e_readiness.py`

## Milestone 6 Umsetzungsstand

Umgesetzt am 2026-02-17:
- E2E Readiness-Tests für persistentes Logging im Standard- und Fehlerpfad.
- Ausführbarer Rollout-Schnellcheck (`verify_milestone6.py`) für Go/No-Go.
- Operatives Runbook mit Pass-Kriterien und Start-Konfiguration.

Code-Referenzen:
- `tests/test_milestone6_e2e_readiness.py`
- `verify_milestone6.py`
- `docs/MILESTONE6_RUNBOOK.md`

## Abnahme fuer Milestone 0

- [x] Memory-Ownership entschieden und dokumentiert.
- [x] Laufzeitpfade und Konflikte explizit beschrieben.
- [x] Verbindliche Rollen/Regeln fuer Folge-Meilensteine festgelegt.
