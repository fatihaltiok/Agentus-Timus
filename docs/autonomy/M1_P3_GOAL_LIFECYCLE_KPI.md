# M1.3 Goal-Lifecycle, Konflikte und KPI-Export

Stand: 2026-02-25

## Ziel
M1.3 haertet die Zielhierarchie aus M1.1/M1.2:
1. formale Status-Transitionen,
2. Konflikterkennung zwischen aktiven Zielen,
3. KPI-Export fuer Monitoring und Canvas.

## Formale Goal-Transitions
In `orchestration/task_queue.py` sind Status-Regeln definiert:
1. `active -> blocked|completed|cancelled`
2. `blocked -> active|completed|cancelled`
3. `completed -> (kein Standard-Transition)`
4. `cancelled -> (kein Standard-Transition)`

Neue API:
1. `transition_goal_status(goal_id, target_status, reason="")`

## Konflikterkennung
Neue APIs:
1. `detect_goal_conflicts(...)`
2. `sync_goal_conflicts(auto_block=False, max_pairs=...)`

Heuristik:
1. Token-Overlap in Goal-Titeln.
2. Antonym-Paare (z. B. `increase/decrease`, `aktivieren/deaktivieren`).
3. Negations-Overlap (`nicht/no/not` bei starkem gemeinsamen Kontext).

Konflikte werden als `goal_edges` mit `edge_type='conflicts_with'` persistiert.

## KPI-Export (Goal Alignment)
Neue API:
1. `get_goal_alignment_metrics(include_conflicts=True)`

Enthaelt u. a.:
1. `open_aligned_tasks / open_tasks`
2. `goal_alignment_rate`
3. `goal_counts` (active/blocked/completed/cancelled)
4. `conflict_count`
5. `orphan_triggered_tasks`

## Integration
1. `gateway/telegram_gateway.py`
   - `/tasks` zeigt offene Alignment-Rate.
   - `/status` zeigt Goal-Alignment + Goal-Status + Konfliktanzahl.
2. `main_dispatcher.py`
   - CLI-`/tasks` zeigt Goal-Alignment.
3. `orchestration/autonomous_runner.py`
   - Heartbeat synchronisiert Konflikte.
   - KPI-Snapshot wird in Logs und (falls vorhanden) als Canvas-Event `goal_kpi` exportiert.

## Kompatibilitaet
1. Keine Signatur-Breaks im Dispatcher/Runner.
2. Feature-Flags aus M0 bleiben wirksam.
3. Additive Erweiterung ohne Entfernung bestehender Pfade.
