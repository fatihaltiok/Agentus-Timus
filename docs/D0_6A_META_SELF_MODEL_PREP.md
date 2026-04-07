# D0.6a Meta Self-Model Calibration

Stand: 2026-04-07

## Status

D0.6a ist jetzt im eigenen Scope funktional abgeschlossen.

Das operative Selbstmodell ist nicht mehr nur ein Schema im Handoff, sondern greift jetzt auch im echten Routing- und Policy-Pfad fuer Selbstbildfragen.

Umgesetzt:

- Dispatcher routet Selbstbild- und Faehigkeitsfragen an `meta`
- D0.6-Policy erkennt diese Fragen als `self_model_status_request`
- `meta` bleibt dann auf `single_lane`, ohne Delegation
- `response_mode` wird auf `summarize_state` gezogen
- `self_model_bound_applied` wird in der Runtime beobachtbar gemacht
- der Meta-Prompt verpflichtet sich auf `meta_self_state` statt auf freie Selbstbehauptung

## Neu im Self-State

Der maschinenlesbare Self-State von `meta` traegt jetzt zusaetzlich:

- `current_capabilities`
- `partial_capabilities`
- `planned_capabilities`
- `blocked_capabilities`
- `confidence_bounds`
- `autonomy_limits`

Diese Felder werden bereits im strukturierten Dispatcher-zu-Meta-Handoff mitgegeben.

## Bedeutung der Felder

### `current_capabilities`

Faehigkeiten, die Timus aktuell als runtime- und testgestuetzt verfuegbar behandeln darf.

Beispiele:

- `structured_delegation`
- `turn_understanding`
- `context_rehydration`
- `response_mode_policy`

### `partial_capabilities`

Faehigkeiten, die vorhanden sind, aber noch mit klaren Caveats beschrieben werden muessen.

Beispiele:

- `specialist_handoffs`
- `site_profile_coverage`
- `browser_workflow_orchestration`

### `planned_capabilities`

Roadmap-Faehigkeiten, die nicht als aktuelle Realitaet behauptet werden duerfen.

Beispiele:

- `approval_gate_workflows`
- `user_mediated_login`
- `specialist_context_propagation`
- `state_decay_cleanup`
- `self_model_policy_binding`

### `blocked_capabilities`

Faehigkeiten, die aktuell durch Runtime-Grenzen oder Guards blockiert sind.

Beispiele:

- `browser_workflow_orchestration`
- `heavy_research_delegation`
- `unattended_background_autonomy`

### `confidence_bounds`

Maschinenlesbare Leitplanken dafuer, wie `meta` ueber eigene Faehigkeiten sprechen soll.

Startlogik:

- `current_only`
- `partial_with_caveats`
- `planned_not_current`
- `bounded`
- optional `blocked_now`

### `autonomy_limits`

Explizite Grenzen, die nicht nur implizit in `known_limits` versteckt bleiben sollen.

Startlogik:

- `bounded_replanning_only`
- `approval_gate_not_fully_active`
- `user_mediated_auth_required`
- optional runtime-bedingte Blocker wie `autonomy_hold`

## Was D0.6a noch nicht macht

Dieser Block loest nicht jede kuenftige Selbstbildfrage automatisch perfekt.

Noch offen:

- spaetere Feinschliffe im Stil und in der Formulierung
- weitere Live-Evals ueber Canvas/Telegram
- moegliche spaetere Nachjustierung einzelner Query-Muster

## Ergebnis

Timus kann jetzt bei Selbstbildfragen erstmals systemisch unterscheiden zwischen:

- aktuell verfuegbar
- nur teilweise verfuegbar
- geplant
- aktuell blockiert

und diese Fragen landen nicht mehr auf dem alten Executor-Kurzpfad, sondern im dafuer passenden Meta-Selbstmodellpfad.
