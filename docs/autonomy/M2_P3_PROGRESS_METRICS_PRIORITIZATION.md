# M2.3 Fortschrittsmetriken + Replanning-Priorisierung

Stand: 2026-02-25

## Ziel
M2.2 wird um zwei operative Faehigkeiten erweitert:
1. Plan-/Commitment-Fortschritt mit Abweichungsmetriken messbar machen.
2. Replanning auf die kritischsten Commitments priorisieren.

## Neue Metriken (Queue-Layer)
In `orchestration/task_queue.py`:
1. `get_commitment_progress_snapshot()`
   - Open/Closed/Completion-Rate
   - Overdue + Due-24h
   - Partial-Stagnation + Drift
   - `plan_deviation_score` (Soll/Ist-Gap)
   - Horizon-Health fuer `daily|weekly|monthly`
2. `get_planning_metrics()` erweitert um:
   - `due_24h_commitments`
   - `blocked_open_commitments`
   - `avg_progress_open`
   - `plan_deviation_score`

## Replanning-Priorisierung
In `orchestration/task_queue.py`:
1. `list_replanning_candidates(...)`
   - Prioritaets-Score aus: overdue, blocked, goal_conflict, stagnation, drift, progress_gap, horizon
   - Rueckgabe inkl. `priority_score` + `priority_reasons`
2. `get_replanning_metrics()` erweitert um:
   - `top_priority_score`
   - `top_candidates` (kompakte Top-Liste)

## Engine-Anpassung
`orchestration/replanning_engine.py`:
1. Nutzt priorisierte Kandidatenliste statt unsortierter Commitment-Liste.
2. Summary liefert:
   - `priority_candidates`
   - `top_priority_score`
3. Verhalten bleibt additiv und idempotent (M2.2-Event-Keys unveraendert).

## Monitoring / Operator
1. Runner-Log + Canvas:
   - Planning-KPI jetzt mit `plan_deviation_score`
   - Replanning-KPI jetzt mit `top_priority_score`
2. Telegram `/tasks` + `/status`:
   - Deviation + Top-Priority sichtbar
3. CLI `/tasks`:
   - Deviation + Top-Priority sichtbar

## Kompatibilitaet
1. Keine Breaking Signatures.
2. Additive Metrik-/Priorisierungslogik auf bestehendem M2.2-Design.
3. Vollstaendig hinter bestehender M0/M2-Flag-Strategie.
