# M4.4 Rollout-Guard + Auto-Rollback

Stand: 2026-02-25

## Ziel
Canary-Rollout wird operativ abgesichert:
1. Bei Policy-Block-Spikes wird strict automatisch zurueckgenommen.
2. Runtime-Overrides werden persistent gespeichert.
3. Rollout-Aktionen haben Cooldown, um Flapping zu vermeiden.

## Architektur
### Persistenter Runtime-State
In `orchestration/task_queue.py`:
1. Neue Tabelle `policy_runtime_state`
2. Neue APIs:
   - `set_policy_runtime_state(...)`
   - `get_policy_runtime_state(...)`

### Policy-Entscheidungen persistent
In `orchestration/task_queue.py`:
1. Tabelle `policy_decisions` (M4.3) wird aktiv als Primaerspeicher genutzt.
2. `get_policy_decision_metrics(...)` liefert jetzt auch Runtime-Override-Infos:
   - `strict_force_off`
   - `canary_percent_override`
   - `runtime_overrides`

### Rollout-Guard
In `utils/policy_gate.py`:
1. `evaluate_and_apply_rollout_guard(...)`
   - prueft Blockrate im Zeitfenster
   - setzt bei Ueberschreitung:
     - `strict_force_off=true`
     - `canary_percent_override=0`
2. Canary bleibt deterministisch (`_canary_bucket_for_key`).
3. Cooldown verhindert haeufige Folgeaktionen.

### Runner-Integration
In `orchestration/autonomous_runner.py`:
1. `_apply_policy_rollout_guard()` pro Heartbeat (wenn Policy-Features aktiv).
2. Warn-Log bei `rollback_applied` oder `cooldown_active`.

## Neue ENV-Parameter
1. `AUTONOMY_POLICY_ROLLBACK_ENABLED=false`
2. `AUTONOMY_POLICY_ROLLBACK_WINDOW_HOURS=1`
3. `AUTONOMY_POLICY_ROLLBACK_MIN_DECISIONS=20`
4. `AUTONOMY_POLICY_ROLLBACK_BLOCK_RATE_PCT=40`
5. `AUTONOMY_POLICY_ROLLBACK_COOLDOWN_MIN=60`

## Kompatibilitaet
1. Vollstaendig additive Erweiterung.
2. Default bleibt inaktiv (`AUTONOMY_POLICY_ROLLBACK_ENABLED=false`).
3. Keine Signatur-Breaks in Dispatcher/Registry/Server/Runner.
