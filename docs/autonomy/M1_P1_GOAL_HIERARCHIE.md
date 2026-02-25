# M1.1 Goal-Hierarchie (additiv, kompatibel)

Stand: 2026-02-25

## Ziel
Additiver Start fuer Autonomie-M1: TaskQueue bekommt ein persistentes Goal-Graph-Modell
(`goals`, `goal_edges`, `goal_state`) ohne Bruch bestehender Dispatcher/Agent/Queue-Vertraege.

## Architektur-Fit zu Timus
1. Bestehender SQLite-Pfad bleibt: `data/task_queue.db`.
2. `TaskQueue.add(...)` bleibt aufrufkompatibel; neues Feld `goal_id` ist optional.
3. Bestehende Task-Status-/Claim-Logik bleibt unveraendert.
4. Goal-Fortschritt ist rein additiv und ueber Feature-Flag gated.

## Neue Datenmodelle (SQLite)
1. `goals`: Zielobjekte mit `status`, `priority_score`, `source`.
2. `goal_edges`: gerichtete Kanten (z. B. parent_child / depends_on).
3. `goal_state`: Fortschritt, letztes Event, Metriken als JSON.
4. `tasks.goal_id` (optional) zur Zuordnung Task -> Ziel.

## Feature-Flag Verhalten
1. Standard: `AUTONOMY_COMPAT_MODE=true` blockiert M1-Automatik.
2. M1 aktiv nur wenn:
   - `AUTONOMY_COMPAT_MODE=false`
   - `AUTONOMY_GOALS_ENABLED=true`
3. Bei aktiver M1-Automatik erzeugt `TaskQueue.add(...)` bei fehlendem `goal_id`
   ein Goal und verknuepft den Task.

## Neue TaskQueue-API (additiv)
1. `create_goal(...)`
2. `link_goals(...)`
3. `get_goal(...)`
4. `get_goal_state(...)`
5. `list_goals(...)`
6. `update_goal_state(...)`
7. `refresh_goal_progress(...)`

## Runner-Integration (M1.1)
`AutonomousRunner._execute_task(...)` aktualisiert bei erfolgreichem/fehlgeschlagenem
Task den Goal-Fortschritt, wenn M1-Flags aktiv sind.

## Risiken / Grenzen
1. Priorisierung und Ziel-Score-Berechnung sind noch einfach (kein Multi-KPI-Scorer).
2. Noch kein eigenstaendiger Goal-Generator aus Memory/Curiosity-Events.
3. Noch kein Re-Planning/Commitment-Layer (M2).
