# Bericht 2026-03-09: P5.1 bis P5.4

## Ziel

Die Produktionshaertung nach `P0` bis `P4` wurde in vier weitere Schnitte gezogen:

- `P5.1` Live-E2E-Haertung unter realistischeren Randfaellen
- `P5.2` Feedback-/Autonomie-Lernen wirksamer machen
- `P5.3` Visual-Agent fuer komplexe Webseiten weiter haerten
- `P5.4` Ops-/Kosten-Eskalation bis in die Runtime-Gates ziehen

## Ergebnis

Der aktuelle Stand ist nach diesen Phasen weiter `READY`:

- `python scripts/run_production_gates.py`
- Ergebnis: `READY | total=4 passed=4 failed=0 skipped=0 blocking_failed=0`

## P5.1 Live-E2E-Haertung

Erweiterungen:

- [status_snapshot.py](/home/fatih-ubuntu/dev/timus/gateway/status_snapshot.py)
  liest jetzt Restart-Artefakte mit Alter/Status und erweitert Service-Zustaende um `sub_state`, `main_pid`, `uptime_seconds`.
- [e2e_regression_matrix.py](/home/fatih-ubuntu/dev/timus/orchestration/e2e_regression_matrix.py)
  unterscheidet jetzt sauber:
  - Startup-Grace nach frischem Restart
  - stale Restart-Statusdateien
  - browser blindness bzw. unvollstaendige Browser-Eval-Ergebnisse

Wirkung:

- frische Restarts werden nicht mehr zu frueh als stabil gruen missverstanden
- degradierte Browser-Eval-Sicht fuehrt jetzt zu `warn` statt false positive `pass`
- haengende Restart-Artefakte erzeugen sichtbar Drift

## P5.2 Runtime-Feedback / implizites Lernen

Erweiterungen:

- [feedback_engine.py](/home/fatih-ubuntu/dev/timus/orchestration/feedback_engine.py)
  hat jetzt `record_runtime_outcome(...)` fuer gedämpftes implizites Feedback aus echten Outcomes.
- [main_dispatcher.py](/home/fatih-ubuntu/dev/timus/main_dispatcher.py)
  schreibt nach jedem Agent-Run ein Runtime-Signal auf `dispatcher_agent`.
- [visual.py](/home/fatih-ubuntu/dev/timus/agent/agents/visual.py)
  schreibt Runtime-Signale auf `visual_strategy`, z. B. fuer `browser_flow` oder `datepicker`.

Wirkung:

- Lernen haengt nicht mehr nur an Telegram-Thumbs
- Dispatcher- und Visual-Entscheidungen bekommen echte Erfolg-/Fehlschlag-Evidenz
- das Signal bleibt konservativ, weil Runtime-Feedback mit kleinerem Delta gespeichert wird

## P5.3 Visual-Haertung

Erweiterungen:

- [visual.py](/home/fatih-ubuntu/dev/timus/agent/agents/visual.py)
  baut fuer Browser-Aufgaben jetzt direkt einen expliziten Schrittplan auf Basis von
  [browser_workflow_plan.py](/home/fatih-ubuntu/dev/timus/orchestration/browser_workflow_plan.py).
- derselbe Plan fliesst in die Initialanweisung und in Loop-Recovery-Hinweise ein

Wirkung:

- Browser-/Booking-/Login-/Formular-Aufgaben laufen nicht mehr nur ueber generische Bildsuche
- bei `scan_ui_elements`-Loops bekommt der Agent jetzt den Hinweis, zum naechsten verifizierbaren Plan-Schritt zurueckzugehen
- der Visual-Agent denkt dadurch fuer komplexe Webseiten geordneter und weniger rein lokal

## P5.4 Ops-/Kosten-Eskalation

Erweiterungen:

- neues Gate in [ops_release_gate.py](/home/fatih-ubuntu/dev/timus/orchestration/ops_release_gate.py)
  fuer operative und budgetbezogene Eskalation
- [status_snapshot.py](/home/fatih-ubuntu/dev/timus/gateway/status_snapshot.py)
  zeigt jetzt zusaetzlich `ops_gate`
- [autonomy_scorecard.py](/home/fatih-ubuntu/dev/timus/orchestration/autonomy_scorecard.py)
  kennt jetzt `scorecard_ops_gate_state`
- [autonomous_runner.py](/home/fatih-ubuntu/dev/timus/orchestration/autonomous_runner.py)
  sammelt das Ops-Gate live ein und reicht es in die Scorecard-Control weiter

Wirkung:

- kritische Ops-/Budget-Lagen koennen jetzt Canary und Promotion blockieren
- warnende Ops-/Budget-Lagen fuehren zu Hold statt blindem Weiterschalten
- Ops-/Kosten-Lage ist damit auf derselben Steuerungsebene wie das E2E-Gate angekommen

## Tests und Verifikation

Gezielt gelaufen:

- `python -m py_compile orchestration/feedback_engine.py main_dispatcher.py agent/agents/visual.py orchestration/ops_release_gate.py orchestration/autonomy_scorecard.py orchestration/autonomous_runner.py gateway/status_snapshot.py tests/test_m16_feedback.py tests/test_m16_integration.py tests/test_visual_improvements.py tests/test_ops_release_gate.py tests/test_ops_release_gate_contracts.py tests/test_ops_observability.py tests/test_m5_scorecard_control_loop.py`
- `pytest -q tests/test_telegram_status_snapshot.py tests/test_e2e_regression_matrix.py tests/test_e2e_release_gate.py tests/test_e2e_regression_matrix_contracts.py tests/test_e2e_release_gate_contracts.py`
- `pytest -q tests/test_m16_feedback.py tests/test_visual_improvements.py tests/test_m16_integration.py tests/test_ops_release_gate.py tests/test_ops_observability.py tests/test_m5_scorecard_control_loop.py -k 'record_runtime_outcome or dispatcher_runtime_feedback_updates_selected_agent or visual_runtime_feedback or browser_plan_context or loop_recovery_hint or ops_release_gate or ops_gate or e2e_gate or preferred_recovery_strategy or create_navigation_plan or exposes_control_runtime or collect_ops_gate'`
- `python -m crosshair check tests/test_m16_feedback_contracts.py --analysis_kind=deal`
- `python -m crosshair check tests/test_ops_release_gate_contracts.py --analysis_kind=deal`
- `lean lean/CiSpecs.lean`
- `python scripts/run_production_gates.py`

Relevante Ergebnisse:

- neue gezielte P5-Tests: gruen
- `CrossHair`: gruen
- `Lean`: gruen
- Production Gates: `READY`

## Neue/erweiterte Testdateien

- [test_ops_release_gate.py](/home/fatih-ubuntu/dev/timus/tests/test_ops_release_gate.py)
- [test_ops_release_gate_contracts.py](/home/fatih-ubuntu/dev/timus/tests/test_ops_release_gate_contracts.py)
- [test_m16_feedback.py](/home/fatih-ubuntu/dev/timus/tests/test_m16_feedback.py)
- [test_m16_integration.py](/home/fatih-ubuntu/dev/timus/tests/test_m16_integration.py)
- [test_visual_improvements.py](/home/fatih-ubuntu/dev/timus/tests/test_visual_improvements.py)
- [test_m5_scorecard_control_loop.py](/home/fatih-ubuntu/dev/timus/tests/test_m5_scorecard_control_loop.py)
- [test_ops_observability.py](/home/fatih-ubuntu/dev/timus/tests/test_ops_observability.py)

## Naechster sinnvoller Schritt

Nach `P5.1` bis `P5.4` sind die naechsten Kandidaten keine breiten Infrastruktur-Schnitte mehr, sondern echte Betriebsproben:

- Live-E2E-Randfaelle fuer Telegram, E-Mail und `meta -> visual`
- gezielte Last-/Recovery-Szenarien fuer Restart waehrend laufender Requests
- anschliessend erneute Zwischenbilanz des Produktionsprogramms
