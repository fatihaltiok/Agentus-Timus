# M6.3 Audit Change-Request Approval Gates

Stand: 2026-02-25

## Ziel
Kritische Audit-Change-Requests werden nicht mehr sofort angewendet, sondern laufen ueber eine formale Freigabe:
1. Request wird als `pending_approval` markiert, wenn Gate-Regeln greifen.
2. Nur explizit `approved` Requests duerfen in den Apply-Pfad.
3. Entscheidung und Pending-Backlog sind in Runtime-State/CLI/Telegram sichtbar.

## Architektur
### Approval-Entscheidung
In `orchestration/autonomy_change_control.py`:
1. Approval-Regeln ueber `_approval_requirement(...)`.
2. Gate-Status `pending_approval` fuer blockierte Requests.
3. Freigabe-API `set_change_request_approval(...)`.
4. Separater Apply-Loop fuer freigegebene Requests:
   `evaluate_and_apply_pending_approved_change_requests(...)`.

### Runner-Integration
In `orchestration/autonomous_runner.py`:
1. Audit-Request wird weiterhin aus Export erzeugt.
2. Pending-freigegebene Requests werden in jedem Heartbeat verarbeitet.
3. Neue Action `awaiting_approval` wird im Log sichtbar.

### Runtime-Sichtbarkeit
Neue/erweiterte Runtime-States:
1. `audit_change_pending_approval_count`
2. `audit_change_last_approval_status`
3. `audit_change_last_approval_request_id`
4. `audit_change_last_approver`
5. `audit_change_last_approval_at`

CLI (`main_dispatcher.py`) und Telegram (`gateway/telegram_gateway.py`) zeigen:
1. Anzahl `PendingApproval`
2. `LastApproval` Status

## Neue ENV-Parameter
1. `AUTONOMY_AUDIT_CHANGE_APPROVAL_ENABLED=false`
2. `AUTONOMY_AUDIT_CHANGE_APPROVAL_REQUIRED_ACTIONS=rollback,promote`
3. `AUTONOMY_AUDIT_CHANGE_APPROVAL_PROMOTE_MIN_STEP=10`
4. `AUTONOMY_AUDIT_CHANGE_AUTO_APPROVE=false`
5. `AUTONOMY_AUDIT_CHANGE_AUTO_APPROVER=system`

## Kompatibilitaet
1. Additive Erweiterung hinter `AUTONOMY_AUDIT_CHANGE_APPROVAL_ENABLED`.
2. Standardmaessig deaktiviert.
3. Ohne Approval-Flag bleibt M6.2-Verhalten unveraendert.
