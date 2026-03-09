# Release Notes 2026-03-09: Production Program v4.6

## Ziel

Diese Änderung bündelt die Produktionshärtung von Timus in einem sichtbaren Release-Stand für GitHub, README, Runtime und Canvas.

## Kernänderungen

### 1. Production Readiness / Gates

- Production Gates vereinheitlicht und auf grün gezogen
- Security-Funde (`bandit`) systematisch reduziert und abgearbeitet
- Dependency-/Vulnerability-Gates (`pip_audit`) auf gepinnte Requirements gehärtet
- `py_compile`-, Security- und Smoke-Gates als feste Freigabeschranke eingeführt

### 2. Runtime-, Release- und Canary-Gates

- E2E-Regressionsmatrix eingeführt und erweitert
- Release-/Canary-Gate für Kernflows eingeführt
- Runtime-Anbindung der Gates in den Scorecard-/Autonomiepfad
- zusätzlicher Ops-/Budget-Gate-Pfad, der Promotion/Hold/Rollback nun ebenfalls steuern kann

### 3. Kosten- und API-Kontrolle

- zentrales LLM-Usage-Tracking für Agenten und Dispatcher
- Budget-Grenzen mit `warn`, `soft_limit`, `hard_limit`
- Status-Snapshot um Kosten, Budget und Provider-Health erweitert
- neue Canvas-Sicht `API & Kostenkontrolle`
  - aktiver Provider
  - zugehörige API-Env
  - Provider-State / HTTP / Latenz
  - Requests und Kosten pro Provider
  - Gesamtbudgetzustand

### 4. Feedback und Lernen

- Telegram-Feedback kompakt und robust gemacht
- implizites Runtime-Feedback ergänzt
  - Dispatcher lernt jetzt aus echten Agent-Run-Outcomes
  - Visual-Agent lernt jetzt aus echten Browser-/Recovery-Outcomes
- Feedback wirkt damit nicht mehr nur über explizite Nutzer-Buttons

### 5. Visual- und Browser-Härtung

- Dispatcher-Routing für Browser-Workflows von direktem Visual-Fan-Out auf `meta -> visual` gehoben
- Browser-Workflow-Planung für Booking/Login/Formular-Fälle eingeführt
- Visual-Agent nutzt diesen Ablaufplan jetzt direkt in Ausführung und Loop-Recovery
- strukturierte Navigation und Recovery-Hinweise sind dadurch für komplexe Webseiten präziser

### 6. Stabilität / Betrieb

- Restart-/Supervisor-/Statuspfade gehärtet
- Shutdown-/Restart-Verhalten des MCP-Pfads verbessert
- Qdrant-Konflikt im Dispatcher-Laufzeitpfad beseitigt
- Chroma/PostHog-Telemetrie-Rauschen beim Start reduziert
- bekannte Dispatcher-Test-Hänger im pytest-Pfad behoben

## Wichtige betroffene Dateien

### Runtime / Gates

- [production_gates.py](/home/fatih-ubuntu/dev/timus/orchestration/production_gates.py)
- [e2e_regression_matrix.py](/home/fatih-ubuntu/dev/timus/orchestration/e2e_regression_matrix.py)
- [e2e_release_gate.py](/home/fatih-ubuntu/dev/timus/orchestration/e2e_release_gate.py)
- [ops_release_gate.py](/home/fatih-ubuntu/dev/timus/orchestration/ops_release_gate.py)
- [autonomy_scorecard.py](/home/fatih-ubuntu/dev/timus/orchestration/autonomy_scorecard.py)
- [autonomous_runner.py](/home/fatih-ubuntu/dev/timus/orchestration/autonomous_runner.py)

### Usage / Kosten / Observability

- [llm_usage.py](/home/fatih-ubuntu/dev/timus/utils/llm_usage.py)
- [llm_budget_guard.py](/home/fatih-ubuntu/dev/timus/orchestration/llm_budget_guard.py)
- [self_improvement_engine.py](/home/fatih-ubuntu/dev/timus/orchestration/self_improvement_engine.py)
- [ops_observability.py](/home/fatih-ubuntu/dev/timus/orchestration/ops_observability.py)
- [status_snapshot.py](/home/fatih-ubuntu/dev/timus/gateway/status_snapshot.py)

### Lernen / Agenten

- [feedback_engine.py](/home/fatih-ubuntu/dev/timus/orchestration/feedback_engine.py)
- [main_dispatcher.py](/home/fatih-ubuntu/dev/timus/main_dispatcher.py)
- [visual.py](/home/fatih-ubuntu/dev/timus/agent/agents/visual.py)
- [browser_workflow_plan.py](/home/fatih-ubuntu/dev/timus/orchestration/browser_workflow_plan.py)
- [orchestration_policy.py](/home/fatih-ubuntu/dev/timus/orchestration/orchestration_policy.py)

### Canvas / UI / API

- [mcp_server.py](/home/fatih-ubuntu/dev/timus/server/mcp_server.py)
- [canvas_ui.py](/home/fatih-ubuntu/dev/timus/server/canvas_ui.py)
- [canvas_store.py](/home/fatih-ubuntu/dev/timus/orchestration/canvas_store.py)

### Security / Infrastruktur

- [stable_hash.py](/home/fatih-ubuntu/dev/timus/utils/stable_hash.py)
- [memory_system.py](/home/fatih-ubuntu/dev/timus/memory/memory_system.py)
- [requirements.txt](/home/fatih-ubuntu/dev/timus/requirements.txt)
- [requirements-ci.txt](/home/fatih-ubuntu/dev/timus/requirements-ci.txt)

## GitHub-relevanter Zustand

Dieser Stand soll im Repo klar sichtbar sein:

- README beschreibt jetzt explizit den produktionsnahen Zustand
- diese Release Notes listen die Produktionsänderungen gebündelt auf
- der Canvas zeigt die Kosten-/API-Kontrolle sichtbar im UI
- die Runtime liefert einen strukturierten Snapshot unter `/status/snapshot`

## Verifikation

Wesentliche Nachweise:

- `python scripts/run_production_gates.py`
  - `READY | total=4 passed=4 failed=0 skipped=0 blocking_failed=0`
- gezielte `pytest`-Suiten für:
  - Feedback
  - Visual-Härtung
  - Ops-Gate
  - Scorecard-Control
  - Status-Snapshot
  - Canvas-UI
- `CrossHair`-Contracts grün
- `Lean`-Checks grün

## Ergebnis in einem Satz

Timus ist jetzt deutlich näher an einem **kontrollierten, beobachtbaren, budgetierten und runtime-gehärteten autonomen Agentensystem**, dessen Produktionszustand sowohl im Code als auch im GitHub- und Canvas-Auftritt sichtbar gemacht wurde.
