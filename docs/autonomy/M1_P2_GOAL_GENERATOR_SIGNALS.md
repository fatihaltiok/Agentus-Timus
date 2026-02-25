# M1.2 Goal-Generator aus Signalen (kompatibel)

Stand: 2026-02-25

## Ziel
Eigenstaendige Zielkandidaten aus drei bestehenden Timus-Signalquellen erzeugen:
1. Memory-Dialogzustand
2. Curiosity-Historie
3. Event-getriggerte Tasks

## Implementierung
Neues Modul: `orchestration/goal_generator.py`

### Signalquellen
1. Memory (`memory_manager.session.get_dynamic_state()`):
   - `last_user_goal`
   - `open_threads`
   - `top_topics`
2. Curiosity (`curiosity_sent` Tabelle):
   - letzte Eintraege innerhalb Lookback-Fenster
   - Ableitung von Follow-up-Zielen
3. Events (`TaskType.TRIGGERED` ohne `goal_id`):
   - Legacy/Compat Event-Tasks werden nachtraeglich Zielgraphen zugeordnet

### Dedupe und Priorisierung
1. Titel-normalisierte Deduplizierung ueber alle Signalquellen.
2. Hoechster Prioritaetsscore gewinnt.
3. Task-IDs aus Event-Signalen werden zusammengefuehrt.

## Queue-Erweiterungen (M1.2)
In `orchestration/task_queue.py` additiv ergaenzt:
1. `upsert_goal_from_signal(...)`
2. `assign_task_goal(...)`
3. `get_unassigned_triggered_tasks(...)`

## Runner-Integration
`AutonomousRunner` startet den `GoalGenerator` nur bei aktiven M1-Flags
und verarbeitet Signale bei jedem Heartbeat (`run_cycle(max_goals=3)`).

## Kompatibilitaet
1. Bei `AUTONOMY_COMPAT_MODE=true` bleibt Verhalten unveraendert.
2. Keine bestehende Signatur geaendert.
3. Nur additive Tabellen/Methoden/Module.
