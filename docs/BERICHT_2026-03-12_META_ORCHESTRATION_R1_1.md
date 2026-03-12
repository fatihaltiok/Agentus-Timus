## Meta Orchestration R1.1

### Ziel
`meta` soll fuer spaetere freie Re-Planung nicht nur Promptwissen besitzen, sondern
einen expliziten, maschinenlesbaren Self-State. Dieser Zustand soll festhalten:

- welche Rolle `meta` gerade einnimmt
- welche Spezialagenten und Faehigkeiten fuer den aktuellen Fall vorgesehen sind
- welche Werkzeuge praktisch verfuegbar sind
- welche bekannten Grenzen gelten
- welche Risiken fuer den aktuellen Orchestrierungsfall aktiv sind
- welche konservative/aktive Strategiehaltung aus Outcome-Lernen folgt

### Umgesetzter Schnitt

Neu eingefuehrt wurde:

- `/home/fatih-ubuntu/dev/timus/orchestration/meta_self_state.py`

Das Modul definiert ein kompaktes Self-State-Schema fuer `meta`:

- `MetaRiskSignal`
- `MetaToolState`
- `MetaSelfState`
- `build_meta_self_state(...)`

Der Builder erzeugt aktuell einen Zustand aus:

- `task_type`
- `site_kind`
- `required_capabilities`
- `recommended_entry_agent`
- `recommended_agent_chain`
- `needs_structured_handoff`
- `learning_snapshot`

### Inhalt des Self-State

Der erzeugte `meta_self_state` enthaelt:

- `identity`
- `orchestration_role`
- `strategy_posture`
- `preferred_entry_agent`
- `task_type`
- `site_kind`
- `available_specialists`
- `required_capabilities`
- `active_tools`
- `known_limits`
- `active_risks`
- `structured_handoff_required`

Beispiele fuer abgeleitete Inhalte:

- bekannte Grenzen:
  - `bounded_replanning_only`
  - `recipe_switching_not_enabled`
  - `specialist_handoffs_partial`
  - `ui_state_depends_on_external_site`
- Risiken:
  - `multi_stage_coordination`
  - `negative_outcome_history`
  - `external_ui_variability`
- Werkzeuge:
  - `delegate_to_agent`
  - `browser_workflow_plan`
  - `research_pipeline`
  - `document_exports`
  - `system_diagnostics`

### Integration in den Dispatcher-zu-Meta-Handoff

In `/home/fatih-ubuntu/dev/timus/main_dispatcher.py` wird der Self-State jetzt
zusammen mit dem bestehenden Meta-Handoff erzeugt:

- `payload["meta_self_state"] = build_meta_self_state(...)`

Der Handoff-Block rendert diesen Zustand zusaetzlich als:

- `meta_self_state_json: {...}`

Dadurch ist der Zustand:

- im Prompt sichtbar
- in `runtime_metadata["meta_orchestration"]` enthalten
- spaeter fuer weitere Adaptive- und Re-Planing-Schritte nutzbar

### Parser-Unterstuetzung in Meta

In `/home/fatih-ubuntu/dev/timus/agent/agents/meta.py` wurde der bestehende
Meta-Handoff-Parser erweitert:

- `meta_self_state_json` wird jetzt wieder als `dict` eingelesen

Damit ist der Self-State nicht nur fuer das Dispatcher-Logging vorhanden,
sondern steht `meta` selbst maschinenlesbar im Handoff-Payload zur Verfuegung.

### Tests und Verifikation

Neue/erweiterte Tests:

- `/home/fatih-ubuntu/dev/timus/tests/test_meta_self_state.py`
- `/home/fatih-ubuntu/dev/timus/tests/test_meta_self_state_contracts.py`
- `/home/fatih-ubuntu/dev/timus/tests/test_meta_handoff.py`

Verifiziert wurde mit:

- `python -m py_compile orchestration/meta_self_state.py main_dispatcher.py agent/agents/meta.py tests/test_meta_handoff.py tests/test_meta_self_state.py tests/test_meta_self_state_contracts.py`
- `pytest -q tests/test_meta_handoff.py tests/test_meta_self_state.py tests/test_meta_self_state_contracts.py tests/test_meta_orchestration.py`
- `python -m crosshair check tests/test_meta_self_state_contracts.py --analysis_kind=deal`
- `lean lean/CiSpecs.lean`
- `python scripts/run_production_gates.py`

Ergebnis:

- zielgerichtete Meta-/Self-State-Tests: gruen
- CrossHair: gruen
- Lean: gruen
- Production Gates: `READY`

### Wirkung

`meta` hat jetzt erstmals ein explizites Selbstbild als Datenstruktur.
Das ist noch keine freie Neuplanung, aber die notwendige Grundlage dafuer.

Der Stand nach R1.1:

- `meta` kennt nun seine Rolle, Spezialisten, Risiken, Grenzen und Strategiehaltung
- Outcome-Lernen beeinflusst diesen Zustand bereits ueber `strategy_posture`
- der Zustand ist im Dispatcher-Handoff und im `meta`-Payload konsistent verfuegbar

### Noch nicht Teil dieses Schnitts

Dieser Schritt fuehrt bewusst noch **nicht** ein:

- freie Rezeptwahl ueber mehrere Alternativen hinweg
- echtes Rezept-Umschalten mitten im Lauf
- session-uebergreifende adaptive Strategiewechsel auf Basis des Self-State
- vollstaendige Tool-/Gate-/Runtime-Synchronisierung im Self-State

### Empfohlener naechster Schritt

`R1.2`: Self-State aus mehr echten Runtime-Signalen anreichern, z. B.:

- Stability-/Ops-/Budget-Gates
- bekannte gesperrte Strategien
- degradierte Tools/Provider
- aktive Incident-/Quarantine-Signale

Erst danach sollte `R2` mit Alternativrezepten und freier Re-Planung beginnen.
