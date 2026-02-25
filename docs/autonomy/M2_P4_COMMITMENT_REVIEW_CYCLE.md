# M2.4 Commitment-Review-Zyklus

Stand: 2026-02-25

## Ziel
Langzeitplanung bekommt einen verbindlichen Review-Loop:
1. Checkpoints fuer offene Commitments werden automatisch geplant.
2. Faellige Reviews werden gegen Erwartungsfortschritt bewertet.
3. Hohe Abweichungen eskalieren in Replanning-Events.

## Datenmodell
Neue Tabelle `commitment_reviews` in `orchestration/task_queue.py`:
1. `commitment_id`, `plan_id`, `goal_id`, `horizon`
2. `review_due_at`, `reviewed_at`, `review_type`
3. `status` (`scheduled|completed|escalated|skipped`)
4. `expected_progress`, `observed_progress`, `progress_gap`, `risk_level`
5. `notes`, `metadata`

## Queue-APIs
1. `upsert_commitment_review(...)`
2. `list_commitment_reviews(...)`
3. `update_commitment_review(...)`
4. `sync_commitment_review_checkpoints(...)`
5. `get_commitment_review_metrics()`
6. `get_commitment(...)` (Helper fuer Engine)

Zusatz:
1. `get_planning_metrics()` enthaelt jetzt Review-Kennzahlen (`due_reviews`, `avg_review_gap_7d`, ...)

## Engine
Neues Modul: `orchestration/commitment_review_engine.py`

Zyklus:
1. Synchronisiert Checkpoints je Horizont:
   - Daily: 6h
   - Weekly: 24h
   - Monthly: 72h
2. Bearbeitet faellige Reviews (`scheduled` + `review_due_at <= now`).
3. Bewertet Risiko anhand Gap zwischen `expected_progress` und `observed_progress`.
4. Eskaliert High/Critical in `replan_events` (wenn Replanning aktiviert).

## Laufzeitintegration
`orchestration/autonomous_runner.py`:
1. Startet `CommitmentReviewEngine` bei aktivem Planning-Flag.
2. Fuehrt Review-Zyklus pro Heartbeat aus.
3. Exportiert `commitment_review_kpi` in Log + Canvas.

## Operator-Sicht
1. Telegram `/tasks` + `/status`: Review-Due, Escalated(7d), Gap(7d)
2. CLI `/tasks`: gleiche Review-Kurzmetriken

## Kompatibilitaet
1. Additiv, keine Breaking Signatures.
2. M0-Flagstrategie unveraendert.
3. M2.2/M2.3 bleiben voll kompatibel.
