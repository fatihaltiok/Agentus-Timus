# M0.1 Architekturvertrag (Kompatibilitaet)

Stand: 2026-02-25

## Ziel
M0 etabliert verbindliche Kompatibilitaetsgrenzen fuer den Ausbau Richtung Autonomie 9/10.
Alle folgenden Meilensteine muessen diesen Vertrag einhalten.

## Invarianten (duerfen in M1+ nicht gebrochen werden)
1. `main_dispatcher.run_agent(agent_name, query, tools_description, session_id=None)` bleibt aufrufkompatibel.
2. `main_dispatcher.get_agent_decision(user_query)` bleibt asynchron und liefert einen Agent-Key.
3. MCP-JSON-RPC Endpunkt `POST /` bleibt kompatibel zu bestehenden Tool-Methoden.
4. `agent_registry.delegate(...)` liefert weiterhin strukturiertes Dict mit `status`.
5. `agent_registry.delegate_parallel(...)` liefert weiterhin Fan-Out/Fan-In Payload mit `results` und `summary`.
6. `TaskQueue` akzeptiert bestehende Tasks ohne neue Pflichtfelder.
7. Bestehende Env-Defaults bleiben wirksam, neue Autonomie-Features nur hinter Flags.
8. Bestehende systemd-Startpfade (`timus-mcp.service`, `timus-dispatcher.service`) bleiben unveraendert.

## Erweiterungsregeln
1. Nur additive DB-Migrationen (neue Tabellen/Spalten/Indices).
2. Keine Entfernung oder Umbenennung bestehender Tool-Namen in `tool_registry_v2`.
3. Keine verpflichtenden Imports neuer schwerer Komponenten im Hot Path ohne Flag.
4. Policy-Hardening zuerst als beobachtender Modus (`strict=false`), dann schrittweise aktivieren.

## Kritische Integrationspunkte fuer M1-M4
1. Orchestrierung: `orchestration/task_queue.py`, `orchestration/autonomous_runner.py`, `orchestration/scheduler.py`
2. Agentenkoordination: `agent/agent_registry.py`, `agent/base_agent.py`, `main_dispatcher.py`
3. Memory/Lernen: `memory/memory_system.py`, `memory/reflection_engine.py`, `memory/soul_engine.py`
4. Enforcement: `utils/policy_gate.py`, `server/mcp_server.py`

## Go/No-Go fuer jede Phase
1. Kompatibilitaetstests gruen.
2. Keine Signatur-Breaks auf den oben genannten Invarianten.
3. Feature-Flags standardmaessig deaktiviert.
4. Kurzdokumentation (Aenderung + Risiko + Rollback) liegt vor.
