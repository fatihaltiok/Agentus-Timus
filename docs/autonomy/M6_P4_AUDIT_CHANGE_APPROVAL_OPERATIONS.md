# M6.4 Audit Change Approval Operations

Stand: 2026-02-25

## Ziel
Approval-Gates werden operativ nutzbar und robust gegen Stau:
1. Operatoren koennen Pending-Approvals direkt via CLI/Telegram entscheiden.
2. Pending-Approvals werden mit SLA ueberwacht.
3. Zeitueberschreitungen werden eskaliert (optional mit Task-Erzeugung) oder automatisch abgelehnt.

## Architektur
### Operator Surface
In `main_dispatcher.py`:
1. CLI-Befehle:
   - `/approvals [limit]`
   - `/approve <request_id_prefix> [note]`
   - `/reject <request_id_prefix> [note]`
2. Prefix-ID-Aufloesung ueber zentrale Control-Logik.

In `gateway/telegram_gateway.py`:
1. Telegram-Befehle:
   - `/approvals [limit]`
   - `/approve <request_id_prefix> [note]`
   - `/reject <request_id_prefix> [note]`
2. Freigabe-Entscheidung und optionaler Sofort-Apply fuer `approved`.

### Control-Logik
In `orchestration/autonomy_change_control.py`:
1. `resolve_change_request_id(...)` fuer stabile Prefix-Aufloesung.
2. `list_pending_approval_change_requests(...)` fuer Inbox-Ansicht.
3. `enforce_pending_approval_sla(...)` fuer Timeout-Handling:
   - Eskalation in Runtime-State
   - optionale Eskalations-Tasks
   - optionales Auto-Reject bei SLA-Verletzung.

### Runner-Integration
In `orchestration/autonomous_runner.py`:
1. Heartbeat verarbeitet weiterhin `approved` Requests.
2. Danach SLA-Check mit Warn-Logging fuer Timeout-Faelle.

## Neue ENV-Parameter
1. `AUTONOMY_AUDIT_CHANGE_APPROVAL_SLA_HOURS=12`
2. `AUTONOMY_AUDIT_CHANGE_APPROVAL_ESCALATION_ENABLED=true`
3. `AUTONOMY_AUDIT_CHANGE_APPROVAL_ESCALATION_TASK_ENABLED=true`
4. `AUTONOMY_AUDIT_CHANGE_APPROVAL_ESCALATION_MIN_INTERVAL_MIN=60`
5. `AUTONOMY_AUDIT_CHANGE_APPROVAL_AUTO_REJECT_ON_TIMEOUT=false`

## Kompatibilitaet
1. Additive Erweiterung hinter M6.2/M6.3 Feature-Flags.
2. Ohne Approval-Flags bleibt Verhalten aus M6.2 unveraendert.
3. Ohne SLA-Timeout keine zusaetzlichen Eskalations-Aktionen.
