# Bericht: Meta Orchestration R2

Datum: 2026-03-12

## Ziel

`meta` sollte nicht mehr nur ein einzelnes Rezept sequentiell ausfuehren, sondern bei geeigneten Task-Typen zwischen mehreren moeglichen Rezeptpfaden umschalten koennen.

Der Ausbau war bewusst klein geschnitten:

- Alternativrezepte fuer erste Task-Typen
- Weitergabe dieser Alternativen im Dispatcher-zu-`meta`-Handoff
- initiale Rezeptwahl anhand von Self-State und Runtime-Signalen
- Rezeptwechsel nach gescheiterter Pflicht-Stage und gescheiterter Recovery

## Umgesetzte Aenderungen

### 1. Alternativrezepte im Orchestrierungsmodell

Datei:
- [meta_orchestration.py](/home/fatih-ubuntu/dev/timus/orchestration/meta_orchestration.py)

Neu:
- `youtube_research_only`
- `system_shell_probe_first`

Zusaetzlich:
- explizite Agentenketten pro Rezept
- Helper fuer Primaerrezept und Alternativrezepte

Damit kann die Meta-Klassifikation jetzt nicht nur ein empfohlenes Rezept, sondern auch moegliche konservative Ausweichpfade liefern.

### 2. Policy und Dispatcher-Handoff

Dateien:
- [orchestration_policy.py](/home/fatih-ubuntu/dev/timus/orchestration/orchestration_policy.py)
- [main_dispatcher.py](/home/fatih-ubuntu/dev/timus/main_dispatcher.py)

Neu:
- `alternative_recipes` wird von der Policy weitergereicht
- der Dispatcher rendert `alternative_recipes_json` in den `# META ORCHESTRATION HANDOFF`

Damit ist die Alternativlogik nicht nur intern im Modell vorhanden, sondern kommt wirklich bei `meta` an.

### 3. Initiale Rezeptwahl aus Self-State

Datei:
- [meta.py](/home/fatih-ubuntu/dev/timus/agent/agents/meta.py)

Neu:
- `_select_initial_recipe_payload(...)`

Verhalten:
- bei `youtube_content_extraction` kann `meta` direkt auf `youtube_research_only` wechseln, wenn Browser-/Stabilitaetssignale dagegen sprechen
- bei `system_diagnosis` kann `meta` direkt auf `system_shell_probe_first` wechseln, wenn die Runtime-Lage einen konservativeren Einstieg verlangt

### 4. Rezeptwechsel nach Stage-Fehler

Datei:
- [meta.py](/home/fatih-ubuntu/dev/timus/agent/agents/meta.py)

Neu:
- `_choose_alternative_recipe_payload(...)`
- Rekursion in `_execute_meta_recipe_handoff(...)` fuer kontrollierten Rezeptwechsel

Verhalten:
- wenn eine Pflicht-Stage fehlschlaegt
- und eine definierte Recovery ebenfalls nicht sauber greift
- kann `meta` jetzt auf ein alternatives Rezept umschalten, statt nur mit Fehler zu enden

Das ist der erste echte Schritt in Richtung freierer Re-Planung ueber mehrere Rezeptpfade hinweg.

## Testabdeckung

Dateien:
- [test_meta_orchestration.py](/home/fatih-ubuntu/dev/timus/tests/test_meta_orchestration.py)
- [test_meta_handoff.py](/home/fatih-ubuntu/dev/timus/tests/test_meta_handoff.py)
- [test_meta_recipe_execution.py](/home/fatih-ubuntu/dev/timus/tests/test_meta_recipe_execution.py)
- [test_meta_self_state.py](/home/fatih-ubuntu/dev/timus/tests/test_meta_self_state.py)
- [test_meta_self_state_contracts.py](/home/fatih-ubuntu/dev/timus/tests/test_meta_self_state_contracts.py)
- [test_meta_orchestration_contracts.py](/home/fatih-ubuntu/dev/timus/tests/test_meta_orchestration_contracts.py)

Neu bzw. erweitert:
- Handoff enthaelt `alternative_recipes_json`
- Klassifikation liefert Alternativrezepte fuer YouTube und Systemdiagnose
- initiale Alternativwahl aus Runtime-/Self-State
- Rezeptwechsel nach Fehlerpfad

## Verifikation

Gelaufen:

```bash
python -m py_compile orchestration/meta_orchestration.py main_dispatcher.py agent/agents/meta.py tests/test_meta_orchestration.py tests/test_meta_handoff.py tests/test_meta_recipe_execution.py
pytest -q tests/test_meta_orchestration.py tests/test_meta_handoff.py tests/test_meta_recipe_execution.py tests/test_meta_self_state.py tests/test_meta_self_state_contracts.py tests/test_meta_orchestration_contracts.py
python -m crosshair check tests/test_meta_self_state_contracts.py tests/test_meta_orchestration_contracts.py --analysis_kind=deal
lean lean/CiSpecs.lean
python scripts/run_production_gates.py
```

Ergebnis:
- `23 passed`
- CrossHair: erfolgreich
- Lean: erfolgreich
- `production_gates`: `READY`

## Einordnung

`meta` ist mit diesem Schnitt kein voll freier Planner, aber deutlich naeher an kontrollierter Re-Planung:

- mehrere moegliche Rezepte sind modelliert
- der Dispatcher reicht diese bewusst an `meta` weiter
- `meta` kann initial konservativer einsteigen
- `meta` kann bei gescheitertem Pflichtpfad auf ein anderes Rezept umschalten

## Noch offen

Der naechste logische Ausbaupunkt ist:

- freie Rezeptwahl nicht nur aus festen Alternativlisten, sondern anhand staerkerer Outcome-Historie
- breitere Alternativrezepte fuer weitere Task-Typen
- gezieltere Re-Planung mitten im Rezept, nicht nur beim Rezeptstart oder nach hartem Stage-Fehler
