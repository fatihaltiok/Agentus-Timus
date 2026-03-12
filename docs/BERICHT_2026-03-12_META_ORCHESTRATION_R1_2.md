# Bericht: Meta Orchestration R1.2

Datum: 2026-03-12

## Ziel

`meta` sollte nicht nur ein statisches Self-State-Schema sehen, sondern reale Laufzeitsignale aus dem laufenden System:

- Budgetlage
- Stabilitaetslage
- offene Self-Healing-Incidents
- Circuit Breaker
- Resource-Guard
- Quarantaene/Cooldown/known bad patterns

Der Ausbau wurde bewusst klein gehalten:

- keine breite Status-Snapshot-Kopie
- keine schwere Zusatzlogik im Dispatcher
- nur die Signale, die `meta` fuer konservativere Orchestrierung wirklich braucht

## Umgesetzte Aenderungen

### 1. Runtime-Constraints im Self-State

In [meta_self_state.py](/home/fatih-ubuntu/dev/timus/orchestration/meta_self_state.py) wurde das Modell um `MetaRuntimeConstraints` erweitert.

Neue Felder:

- `budget_state`
- `stability_gate_state`
- `degrade_mode`
- `open_incidents`
- `circuit_breakers_open`
- `resource_guard_state`
- `resource_guard_reason`
- `quarantined_incidents`
- `cooldown_incidents`
- `known_bad_patterns`
- `release_blocked`
- `autonomy_hold`

Diese Felder erscheinen jetzt unter `meta_self_state["runtime_constraints"]`.

### 2. Echte Runtime-Herkunft

Die Runtime-Constraints werden jetzt direkt aus den bestehenden Produktionspfaden abgeleitet:

- Budget aus [llm_budget_guard.py](/home/fatih-ubuntu/dev/timus/orchestration/llm_budget_guard.py)
- Self-Healing/Incidents/Runtime-State aus [task_queue.py](/home/fatih-ubuntu/dev/timus/orchestration/task_queue.py)
- Stability-Gate aus [self_stabilization_gate.py](/home/fatih-ubuntu/dev/timus/orchestration/self_stabilization_gate.py)

Es wurde **kein** zweites paralleles Statusmodell eingefuehrt.

### 3. Tool-State wird laufzeitbewusst

`meta` sieht jetzt nicht mehr nur statische Tool-Verfuegbarkeit.

Abhaengig von Budget- und Stability-Lage werden relevante Tools als:

- `ready`
- `degraded`
- `blocked`

modelliert, insbesondere:

- `delegate_to_agent`
- `browser_workflow_plan`
- `research_pipeline`
- `document_exports`

### 4. Limits und Risiken werden mit Runtime angereichert

`known_limits` und `active_risks` spiegeln jetzt nicht mehr nur Architekturgrenzen, sondern auch Live-Zustaende:

- `budget_guard_*`
- `stability_gate_*`
- `resource_guard_active`
- `self_healing_incidents_open`

Neue Risiko-Signale:

- `budget_pressure`
- `budget_blocked`
- `stability_guard_active`
- `stability_gate_blocked`
- `resource_guard_active`

## Testbarkeit

Damit Unit- und Contract-Tests nicht von echter Queue-/Budgetlage abhaengen, akzeptiert `build_meta_self_state(...)` jetzt optional Runtime-Overrides.

Dadurch bleiben Tests:

- deterministisch
- schnell
- klar isoliert

## Verifikation

Ausgefuehrt:

- `python -m py_compile orchestration/meta_self_state.py main_dispatcher.py agent/agents/meta.py tests/test_meta_self_state.py tests/test_meta_self_state_contracts.py tests/test_meta_handoff.py`
- `pytest -q tests/test_meta_handoff.py tests/test_meta_self_state.py tests/test_meta_self_state_contracts.py tests/test_meta_orchestration.py`
- `python -m crosshair check tests/test_meta_self_state_contracts.py --analysis_kind=deal`
- `lean lean/CiSpecs.lean`
- `python scripts/run_production_gates.py`

Ergebnis:

- gezielte Meta-Tests: gruen
- CrossHair: gruen
- Lean: gruen
- Production Gates: `READY`

## Wirkung

`meta` hat jetzt erstmals ein Self-State, das nicht nur aus Prompt-/Rezeptwissen besteht, sondern echte Laufzeitlage widerspiegelt.

Das verbessert vor allem:

- konservative Orchestrierungsentscheidungen unter Budgetdruck
- Browser-/Webflow-Zurueckhaltung bei Self-Stabilization-Warnungen
- Nachvollziehbarkeit, warum `meta` spezialisierte Ketten vorsichtiger oder enger fuehrt

## Noch offen

`R1.2` liefert echte Runtime-Sicht, aber noch keine freie Umplanung.

Als naechste sinnvolle Schritte bleiben:

- `R3`: breitere strukturierte Handoffs in weitere Spezialagenten und Tools
- `R2`: Alternativrezepte + freie Re-Planung zwischen mehreren Rezepten
- `R4`: staerkere adaptive Outcome-Nutzung ueber mehrere Sessions/Faelle hinweg
