# M5.1 Autonomy-Scorecard Baseline

Stand: 2026-02-25

## Ziel
Ein einheitlicher Reifegrad fuer Autonomie 9/10 aufbauen:
1. M1-M4 KPIs zu einer konsistenten Scorecard verdichten.
2. Reifegrad transparent in Runner/CLI/Telegram sichtbar machen.
3. Additiv und rueckwaertskompatibel hinter Feature-Flag halten.

## Architektur
### Neues Modul
In `orchestration/autonomy_scorecard.py`:
1. `build_autonomy_scorecard(...)` aggregiert KPI-Pfeiler:
   - Goals
   - Planning/Replanning/Reviews
   - Self-Healing
   - Policy-Gates
2. Jeder Pfeiler wird auf 0..100 normalisiert.
3. Gesamtscore wird gewichtet (je 25%) berechnet.
4. Ausgabe enthaelt:
   - `overall_score`, `overall_score_10`, `autonomy_level`
   - `ready_for_very_high_autonomy`
   - Pillar-Details und Gewichte

### Runner-Integration
In `orchestration/autonomous_runner.py`:
1. Neues Flag `AUTONOMY_SCORECARD_ENABLED`.
2. Heartbeat-Export per `_export_autonomy_scorecard_snapshot()`.
3. Log + optional Canvas-Event `autonomy_scorecard`.

### Operator-Sichtbarkeit
1. CLI (`main_dispatcher.py`) erweitert `/tasks` um `Autonomy-Score`.
2. Telegram (`gateway/telegram_gateway.py`) erweitert `/tasks` und `/status`.

## Neue ENV-Parameter
1. `AUTONOMY_SCORECARD_ENABLED=false`
2. `AUTONOMY_SCORECARD_WINDOW_HOURS=24`

## Kompatibilitaet
1. Rein additive Erweiterung.
2. Default-inaktiv ueber Feature-Flag.
3. Bestehende M1-M4 APIs/Signaturen unveraendert.
