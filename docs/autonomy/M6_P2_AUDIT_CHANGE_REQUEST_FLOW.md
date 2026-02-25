# M6.2 Audit Change-Request Flow

Stand: 2026-02-25

## Ziel
Audit-Empfehlungen werden formalisiert und reproduzierbar angewendet:
1. Empfehlung wird als persistenter Change-Request angelegt.
2. Dedupe ueber Audit-ID verhindert Doppelanwendung.
3. Apply-Status + Runtime-Trace werden fuer Operatoren sichtbar.

## Architektur
### Persistenter Request-Store
In `orchestration/task_queue.py`:
1. Neue Tabelle `autonomy_change_requests`.
2. APIs:
   - `create_autonomy_change_request(...)`
   - `update_autonomy_change_request(...)`
   - `get_autonomy_change_request(...)`
   - `get_autonomy_change_request_by_audit_id(...)`
   - `list_autonomy_change_requests(...)`

### Change-Control Modul
In `orchestration/autonomy_change_control.py`:
1. `create_change_request_from_audit(...)`
2. `evaluate_and_apply_audit_change_request(...)`
3. Apply-Logik fuer Empfehlungen:
   - `promote` -> Canary erhoehen (konfigurierbarer Step)
   - `hold` -> kein Runtime-Override
   - `rollback` -> `strict_force_off=true`, Canary auf 0

### Runner-Integration
In `orchestration/autonomous_runner.py`:
1. Nach Audit-Report-Export wird optional der Change-Request-Flow ausgefuehrt.
2. Canvas-Event `autonomy_audit_change_request` fuer Nachvollziehbarkeit.

### Runtime-Sichtbarkeit
In `policy_runtime_state`:
1. `audit_change_last_request_id`
2. `audit_change_last_audit_id`
3. `audit_change_last_action`
4. `audit_change_last_status`
5. `audit_change_last_applied_at`

## Neue ENV-Parameter
1. `AUTONOMY_AUDIT_CHANGE_REQUESTS_ENABLED=false`
2. `AUTONOMY_AUDIT_CHANGE_REQUEST_MIN_INTERVAL_MIN=30`
3. `AUTONOMY_AUDIT_CHANGE_PROMOTE_STEP=5`
4. `AUTONOMY_AUDIT_CHANGE_MAX_CANARY=100`

## Kompatibilitaet
1. Additive Erweiterung.
2. Standardmaessig deaktiviert.
3. Ohne Flag kein zusaetzlicher Apply-Pfad.
