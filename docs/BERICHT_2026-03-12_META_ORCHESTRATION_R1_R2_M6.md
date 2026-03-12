# Bericht: Meta Orchestration Ausbau R1/R2/M6

Datum: 12.03.2026

## Ziel

Dieser Ausbaublock hatte vier konkrete Ziele:

1. breitere strukturierte Handoffs
2. session-uebergreifendes Outcome-Lernen
3. breitere Meta-Evals
4. freiere Re-Planung ueber mehrere moegliche Rezeptpfade hinweg

## Umgesetzte Bausteine

### 1. Self-State fuer `meta`

`meta` besitzt jetzt ein maschinenlesbares Selbstmodell in
[meta_self_state.py](/home/fatih-ubuntu/dev/timus/orchestration/meta_self_state.py).

Enthalten sind:
- Rolle und Spezialisierungen
- verfuegbare Werkzeuge und Grenzen
- Laufzeitsignale wie Budgetzustand, Stability-Gate, Degrade-Mode
- offene Incidents, Breaker, Quarantaene und bekannte schlechte Muster

Der Dispatcher gibt diesen Zustand im Meta-Handoff weiter, und
`meta` liest ihn als echtes Laufzeitobjekt ein.

### 2. Breitere strukturierte Handoffs

Die strukturierte Delegation wurde ueber `visual` und `research` hinaus erweitert.

Zentraler Parser:
- [delegation_handoff.py](/home/fatih-ubuntu/dev/timus/agent/shared/delegation_handoff.py)

Spezialisten mit Handoff-Nutzung:
- [visual.py](/home/fatih-ubuntu/dev/timus/agent/agents/visual.py)
- [research.py](/home/fatih-ubuntu/dev/timus/agent/agents/research.py)
- [document.py](/home/fatih-ubuntu/dev/timus/agent/agents/document.py)
- [system.py](/home/fatih-ubuntu/dev/timus/agent/agents/system.py)
- [shell.py](/home/fatih-ubuntu/dev/timus/agent/agents/shell.py)
- [communication.py](/home/fatih-ubuntu/dev/timus/agent/agents/communication.py)

Die Handoffs tragen jetzt je nach Fall:
- `goal`
- `expected_output`
- `success_signal`
- `constraints`
- `handoff_data`
- Stage-/Kontextdaten aus vorherigen Schritten

### 3. Session-uebergreifendes Outcome-Lernen

Die Outcome-Signale fuer `meta` wurden verbreitert:
- `meta_task_type`
- `meta_recipe`
- `meta_agent_chain`
- `meta_site_recipe`

Wichtige Stellen:
- [meta_orchestration.py](/home/fatih-ubuntu/dev/timus/orchestration/meta_orchestration.py)
- [main_dispatcher.py](/home/fatih-ubuntu/dev/timus/main_dispatcher.py)
- [meta.py](/home/fatih-ubuntu/dev/timus/agent/agents/meta.py)

Neu ist insbesondere:
- Lernsnapshots im Meta-Handoff
- Alternative-Rezept-Scores pro Site/Task
- Outcome-Erfassung des **tatsaechlich ausgefuehrten** Rezepts
- konservative Rezeptwahl anhand von Evidenz statt nur Prompt-Bias

### 4. Alternativrezepte und freiere Re-Planung

`meta` kennt jetzt mehrere moegliche Rezepte pro Aufgabenklasse und kann:
- schon vor Start das konservativere Rezept waehlen
- nach Stage-Fehlern auf ein Alternativrezept umschalten
- nach Recovery neue Validierungsstufen einschieben

Wichtige Rezept-Erweiterungen:
- `youtube_search_then_visual`
- `youtube_research_only`
- `web_visual_research_summary`
- `web_research_only`
- `system_shell_probe_first`

Wichtige Stellen:
- [meta_orchestration.py](/home/fatih-ubuntu/dev/timus/orchestration/meta_orchestration.py)
- [orchestration_policy.py](/home/fatih-ubuntu/dev/timus/orchestration/orchestration_policy.py)
- [main_dispatcher.py](/home/fatih-ubuntu/dev/timus/main_dispatcher.py)
- [meta.py](/home/fatih-ubuntu/dev/timus/agent/agents/meta.py)

### 5. Breitere Meta-Evals

Die Eval-Suite misst Meta-Entscheidungen jetzt breiter:
- YouTube-Inhaltsextraktion
- X-Thread-/Web-Summary
- Booking-Suche
- Systemdiagnose
- Re-Plan-Faelle mit blockiertem Browser oder schwachen Lernsignalen

Wichtige Dateien:
- [meta_orchestration_eval.py](/home/fatih-ubuntu/dev/timus/orchestration/meta_orchestration_eval.py)
- [test_meta_orchestration_eval.py](/home/fatih-ubuntu/dev/timus/tests/test_meta_orchestration_eval.py)
- [test_meta_orchestration_eval_contracts.py](/home/fatih-ubuntu/dev/timus/tests/test_meta_orchestration_eval_contracts.py)
- [test_meta_orchestration_eval_hypothesis.py](/home/fatih-ubuntu/dev/timus/tests/test_meta_orchestration_eval_hypothesis.py)

## Verifikation

Gruen:
- `pytest -q tests/test_meta_orchestration.py tests/test_meta_handoff.py tests/test_meta_recipe_execution.py tests/test_meta_orchestration_eval.py tests/test_meta_orchestration_eval_contracts.py tests/test_meta_orchestration_eval_hypothesis.py`
- `python -m py_compile tests/test_meta_orchestration_eval_contracts.py tests/test_meta_orchestration_eval_hypothesis.py`
- `python -m crosshair check tests/test_meta_orchestration_contracts.py --analysis_kind=deal`
- `python -m crosshair check tests/test_meta_recipe_execution_contracts.py --analysis_kind=deal`
- `lean lean/CiSpecs.lean`
- `python scripts/run_production_gates.py`

Restpunkt:
- `python -m crosshair check tests/test_meta_orchestration_eval_contracts.py --analysis_kind=deal`
  ist funktional nicht fehlgeschlagen, aber in einem 30s-Lauf weiter zu traege. Deshalb wurde die
  Hypothesis-Schicht aus der Contract-Datei herausgezogen und separat nach
  [test_meta_orchestration_eval_hypothesis.py](/home/fatih-ubuntu/dev/timus/tests/test_meta_orchestration_eval_hypothesis.py)
  verschoben. Der Eval-Contract selbst bleibt noch schwer fuer CrossHair.

## Aktueller Stand von `meta`

`meta` ist jetzt kein blosses Prompt-Routing mehr, sondern ein zustandsbewusster Orchestrator mit:
- Self-State
- strukturiertem Dispatcher-Handoff
- Rezepten und Alternativrezepten
- Stage-Ausfuehrung
- Recovery-Handoffs
- adaptiver Validierungs-/Weiterplanungslogik
- session-uebergreifenden Outcome-Signalen
- breiterer Eval-Abdeckung

## Offene naechste Schritte

Die wichtigsten naechsten sinnvollen Punkte sind:
- Self-State noch tiefer mit Tool-/Policy-/Limit-Signalen anreichern
- Alternativrezepte fuer weitere Klassen wie `document`, `communication` und komplexere Webflows
- Outcome-Lernen staerker von konservativem Bias in echte adaptive Rezeptpraeferenzen ziehen
- Live-End-to-End-Faelle mit `meta` gegen reale Browser-/Research-Aufgaben messen
