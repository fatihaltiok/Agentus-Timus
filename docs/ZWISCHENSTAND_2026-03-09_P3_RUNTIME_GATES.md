# Zwischenstand 2026-03-09: P3 Runtime Gates

## Kontext

Nach `P0`, `P1.1`, `P1.2`, `P1.3`, `P2.1`, `P2.2` und `P2.3` wurde der
naechste Produktionsblock auf echte End-to-End- und Runtime-Steuerung gelegt.

Diese Phase hatte drei Ziele:

1. produktionskritische Kernflows als zentrale E2E-Matrix zusammenziehen
2. daraus Release-/Canary-Entscheidungen ableiten
3. diese Entscheidungen in die laufende Scorecard-/Autonomie-Steuerung einklinken

## Abgeschlossene Phasen

### `P3.1` Zentrale E2E-Regressionsmatrix

Eingefuehrt:

- [e2e_regression_matrix.py](/home/fatih-ubuntu/dev/timus/orchestration/e2e_regression_matrix.py)
- MCP-Zugriff in [tool.py](/home/fatih-ubuntu/dev/timus/tools/self_improvement_tool/tool.py)

Abgedeckte Kernflows:

- `telegram_status`
- `email_backend`
- `restart_recovery`
- `meta_visual_browser`

Ergebnis:

- E2E-Status ist jetzt nicht mehr ueber verstreute Einzeltests sichtbar,
  sondern ueber eine zentrale Matrix mit `pass` / `warn` / `fail`
- jeder Flow traegt `blocking` und strukturierte `evidence`

### `P3.2` Release-/Canary-Gate auf Basis der E2E-Matrix

Eingefuehrt:

- [e2e_release_gate.py](/home/fatih-ubuntu/dev/timus/orchestration/e2e_release_gate.py)
- MCP-Tool `get_e2e_release_gate_status` in [tool.py](/home/fatih-ubuntu/dev/timus/tools/self_improvement_tool/tool.py)

Ergebnis:

- E2E-Matrix fuehrt jetzt zu einer klaren Runtime-Entscheidung:
  - `pass`
  - `warn`
  - `blocked`
- zusaetzlich:
  - `release_blocked`
  - `canary_blocked`
  - `canary_deferred`
  - `recommended_canary_percent`
- Telegram-taugliche Alert-Nachricht ist vorhanden

### `P3.3` Integration in die laufende Autonomie-Steuerung

Eingefuehrt:

- E2E-Gate-Integration in [autonomy_scorecard.py](/home/fatih-ubuntu/dev/timus/orchestration/autonomy_scorecard.py)
- Runtime-Sammlung im Runner in [autonomous_runner.py](/home/fatih-ubuntu/dev/timus/orchestration/autonomous_runner.py)

Ergebnis:

- Scorecard darf Canary nicht mehr blind promoten
- wenn das E2E-Gate `warn` meldet:
  - `e2e_gate_hold`
- wenn das E2E-Gate `blocked` meldet:
  - `e2e_gate_blocked`
  - Canary auf `0`
  - Promotion gestoppt
- E2E-Gate-State wird jetzt im Scorecard-Control-Runtime-State persistiert

## Neue wichtige Dateien

- [browser_workflow_eval.py](/home/fatih-ubuntu/dev/timus/orchestration/browser_workflow_eval.py)
- [e2e_regression_matrix.py](/home/fatih-ubuntu/dev/timus/orchestration/e2e_regression_matrix.py)
- [e2e_release_gate.py](/home/fatih-ubuntu/dev/timus/orchestration/e2e_release_gate.py)

## Neue/erweiterte Tests

- [test_browser_workflow_eval.py](/home/fatih-ubuntu/dev/timus/tests/test_browser_workflow_eval.py)
- [test_browser_workflow_eval_contracts.py](/home/fatih-ubuntu/dev/timus/tests/test_browser_workflow_eval_contracts.py)
- [test_e2e_regression_matrix.py](/home/fatih-ubuntu/dev/timus/tests/test_e2e_regression_matrix.py)
- [test_e2e_regression_matrix_contracts.py](/home/fatih-ubuntu/dev/timus/tests/test_e2e_regression_matrix_contracts.py)
- [test_e2e_release_gate.py](/home/fatih-ubuntu/dev/timus/tests/test_e2e_release_gate.py)
- [test_e2e_release_gate_contracts.py](/home/fatih-ubuntu/dev/timus/tests/test_e2e_release_gate_contracts.py)
- [test_m5_scorecard_control_loop.py](/home/fatih-ubuntu/dev/timus/tests/test_m5_scorecard_control_loop.py)

## Verifikation

Wiederholt erfolgreich gelaufen:

- `python -m py_compile ...`
- gezielte `pytest -q ...`
- `python -m crosshair check ... --analysis_kind=deal`
- `python -m bandit -q -ll ...`
- `lean lean/CiSpecs.lean`
- `python scripts/run_production_gates.py`

Wichtiger Stand am Ende:

- `run_production_gates.py` bleibt gruen:
  `READY | total=4 passed=4 failed=0 skipped=0 blocking_failed=0`

## Einordnung

Mit diesem Stand ist Timus nicht nur beobachtbar, sondern beginnt aktiv
betriebliche Selbstbegrenzung umzusetzen:

- E2E-Ausfaelle werden zentral erkannt
- daraus entstehen klare Release-/Canary-Entscheidungen
- diese Entscheidungen wirken auf die laufende Autonomie-Steuerung zurueck

Das ist ein deutlicher Schritt in Richtung echter Produktionsreife.

## Naechster sinnvoller Schritt

Es gibt jetzt zwei vernuenftige Richtungen:

1. **Live-Betriebsprobe**
   Die neuen E2E-/Release-Gates an einem echten Lauf verifizieren:
   - Matrix abrufen
   - Release-Gate abrufen
   - Scorecard-Control-Zustand lesen
   - pruefen, ob Runtime-State und Alerts konsistent sind

2. **`P4` Wirksamkeit von Autonomie und Feedback**
   Die naechste produktive Luecke nicht bei Gates, sondern bei
   verhaltenswirksamem Lernen und autonomer Qualitaetsverbesserung angehen.

## Empfehlung

Technisch ist jetzt zuerst die **Live-Betriebsprobe** sinnvoller.

Begruendung:

- Die neuen Gates greifen mehrere Schichten gleichzeitig an
- lokal und in Tests sind sie abgesichert
- vor weiterem Ausbau sollte einmal der echte Runtime-Pfad verifiziert werden

Danach ist `P4` die bessere naechste Entwicklungsachse.
