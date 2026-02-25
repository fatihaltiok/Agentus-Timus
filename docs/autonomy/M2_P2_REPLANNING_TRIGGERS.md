# M2.2 Replanning Trigger + Recovery

Stand: 2026-02-25

## Ziel
Re-Planning als robuste Erweiterung der M2.1-Planung:
1. Trigger-Erkennung fuer Ziel-/Commitment-Drift
2. Idempotente Replan-Events mit Audit-Trail
3. Automatische Recovery-Commitments (ohne bestehende Flows zu brechen)

## Trigger (M2.2)
1. `deadline_timeout`
   - Commitment ist ueberfaellig
2. `partial_stagnation`
   - Teilfortschritt vorhanden, aber zu lange kein Update
3. `goal_drift`
   - Kein Fortschritt ueber Drift-Schwelle
4. `goal_conflict`
   - Goal-Konflikt erkannt oder Goal bereits `blocked`

## Datenmodell (additiv)
Neue Tabelle `replan_events` in `orchestration/task_queue.py`:
1. `event_key` (idempotent / unique)
2. `commitment_id`, `goal_id`
3. `trigger_type`, `severity`, `status`, `action`
4. `details` (JSON), `created_at`, `updated_at`

## Neue APIs
1. `log_replan_event(...)`
2. `update_replan_event_status(...)`
3. `list_replan_events(...)`
4. `get_replanning_metrics()`
5. `get_plan(...)` (Hilfsmethode fuer Recovery-Deadline-Logik)

## Engine
Neues Modul: `orchestration/replanning_engine.py`

Verhalten pro Zyklus:
1. Scan offener Commitments (`pending`, `in_progress`, `blocked`)
2. Trigger-Detection + Event-Erzeugung mit stabilem `event_key` (Bucket pro Tag)
3. Action-Ausfuehrung:
   - Blockieren oder Nudge des Original-Commitments
   - Recovery-Commitment fuer Timeout/Partial-Drift/Goal-Drift
4. Event-Status auf `applied` oder `failed` setzen

## Laufzeit-Integration
`orchestration/autonomous_runner.py`:
1. Startet `ReplanningEngine` hinter Flags:
   - `AUTONOMY_COMPAT_MODE=false`
   - `AUTONOMY_REPLANNING_ENABLED=true`
2. Fuehrt Replanning bei jedem Heartbeat aus.
3. Exportiert `replanning_kpi` (Log + optional Canvas).

## Operator-Sichtbarkeit
1. Telegram `/tasks`: Replanning Events/24h + Overdue-Kandidaten
2. Telegram `/status`: Replanning-Metriken
3. CLI `/tasks`: Replanning-Kurzstatus

## Kompatibilitaet
1. Additive Tabellen/Methoden/Module, keine Breaking Signatures.
2. Feature-Flag-gated nach M0-Vertrag.
3. Idempotenz verhindert Event-/Recovery-Duplikate pro Signal-Bucket.
