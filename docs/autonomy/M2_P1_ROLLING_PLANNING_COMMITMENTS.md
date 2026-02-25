# M2.1 Rolling Planning + Commitments

Stand: 2026-02-25

## Ziel
Robuste Langzeitplanung als additive Erweiterung:
1. Rolling Plans fuer `daily`, `weekly`, `monthly`
2. Commitments mit:
   - Deadline
   - Owner-Agent
   - Success-Metric

## Datenmodell (SQLite, additiv)
In `orchestration/task_queue.py`:
1. `plans`
   - `horizon`, `window_start`, `window_end`, `status`, `metadata`
2. `plan_items`
   - planbezogene Ziele/Aktionen inkl. Owner, Deadline, Success-Metric
3. `commitments`
   - ausfuehrbare Zusagen mit Status, Progress und Metadaten

## Neue APIs
1. Plan:
   - `create_or_get_plan(...)`
   - `list_plans(...)`
2. Plan-Items:
   - `add_plan_item(...)`
   - `list_plan_items(...)`
3. Commitments:
   - `create_commitment(...)`
   - `list_commitments(...)`
   - `update_commitment_status(...)`
4. Metrics:
   - `get_planning_metrics()`
   - inkl. `overdue_commitments`

## Planner-Service
Neues Modul: `orchestration/long_term_planner.py`

Verhalten:
1. Pro Zyklus werden Fenster fuer Tag/Woche/Monat berechnet.
2. Es wird je Fenster ein Plan erstellt/aktualisiert.
3. Aktive/Blocked Goals werden priorisiert in:
   - Daily: Top 3
   - Weekly: Top 6
   - Monthly: Top 10
4. Pro Goal entstehen Plan-Item und Commitment (idempotent via Upsert-Logik).

## Integration in Laufzeit
`orchestration/autonomous_runner.py`:
1. Startet `LongTermPlanner` nur wenn:
   - `AUTONOMY_COMPAT_MODE=false`
   - `AUTONOMY_PLANNING_ENABLED=true`
2. Fuehrt Planner-Zyklus bei jedem Heartbeat aus.
3. Exportiert Planning-KPI in Logs und optional als Canvas-Event `planning_kpi`.

## Sichtbarkeit (Operator)
1. Telegram:
   - `/tasks` zeigt aktive Plaene + Commitments.
   - `/status` zeigt Planning-Metriken inkl. Overdue.
2. CLI:
   - `/tasks` zeigt Planning-Kurzstatus.

## Kompatibilitaet
1. Keine Breaking Changes an bestehenden Dispatcher-/Runner-Signaturen.
2. Alles additive Tabellen/Methoden/Module.
3. Feature-Flag-gated nach M0-Vertrag.
