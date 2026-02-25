# M3.4 Escalation Control Loop + Attempt Budget

Stand: 2026-02-25

## Ziel
Self-Healing wird fuer lang anhaltende Stoerungen robuster:
1. Wiederholte Playbook-Trigger pro Incident werden begrenzt (Attempt-Budget).
2. Alte offene Incidents werden automatisch eskaliert (SLA-basiert).
3. Escalation-Status wird in Metriken und Operator-Ansichten sichtbar.

## Engine-Erweiterung
`orchestration/self_healing_engine.py`:
1. Neue Summary-KPIs:
   - `incidents_escalated`
   - `escalation_tasks_created`
   - `playbook_attempts_blocked`
2. Attempt-Budget:
   - Env: `AUTONOMY_SELF_HEALING_MAX_PLAYBOOK_ATTEMPTS`
   - Nach Erreichen des Budgets werden weitere Retries blockiert (`attempts_exhausted`).
3. Escalation-Control-Loop:
   - Env: `AUTONOMY_SELF_HEALING_ESCALATE_AFTER_MIN`
   - Env: `AUTONOMY_SELF_HEALING_ESCALATION_LIMIT_PER_CYCLE`
   - Stale Open-Incidents werden als `incident_escalation` Playbook priorisiert weitergeleitet.
4. Recovery-Reset:
   - Bei erfolgreicher Recovery werden Escalation-/Attempt-Marker zurueckgesetzt.

## Daten-/API-Erweiterung
`orchestration/task_queue.py`:
1. `upsert_self_healing_incident(...)` erhaelt optional `observed_at`.
2. `resolve_self_healing_incident(...)` erhaelt optional `observed_at`.
3. `get_self_healing_metrics()` erweitert um:
   - `open_escalated_incidents`
   - `max_open_incident_age_min`

Die `observed_at`-Erweiterung macht den Incident-Zeitverlauf deterministisch und testbar.

## Operator-Sicht
1. Runner-Heartbeat loggt Escalation/Blocked-Attempts.
2. Self-Healing-KPI zeigt:
   - `escalated_open`
   - `max_open_age_min`
3. Telegram und CLI zeigen `EscalatedOpen` in der Healing-Zeile.

## Neue ENV-Parameter
1. `AUTONOMY_SELF_HEALING_MAX_PLAYBOOK_ATTEMPTS=3`
2. `AUTONOMY_SELF_HEALING_ESCALATE_AFTER_MIN=30`
3. `AUTONOMY_SELF_HEALING_ESCALATION_LIMIT_PER_CYCLE=3`

## Kompatibilitaet
1. Additive Erweiterung ohne Breaking-Signaturen.
2. Verhalten bleibt hinter `AUTONOMY_SELF_HEALING_ENABLED`.
3. M1/M2/M3.1-M3.3 bleiben kompatibel.
