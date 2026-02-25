# M5.3 Scorecard Trends + Adaptive Thresholds

Stand: 2026-02-25

## Ziel
M5.2 wird stabilisiert durch Trendwissen:
1. Scorecard-Snapshots persistent speichern.
2. Trendmetriken (24h/30d) fuer Score, Richtung und Volatilitaet ableiten.
3. Control-Schwellen dynamisch anpassen (tighten/relax/stable).

## Architektur
### Persistente Snapshots
In `orchestration/task_queue.py`:
1. Neue Tabelle `autonomy_scorecard_snapshots`.
2. API:
   - `record_autonomy_scorecard_snapshot(...)`
   - `list_autonomy_scorecard_snapshots(...)`
   - `get_autonomy_scorecard_trends(...)`

### Trenddaten in Scorecard
In `orchestration/autonomy_scorecard.py`:
1. `build_autonomy_scorecard(...)` liefert jetzt `trends`.
2. Trends enthalten u.a.:
   - `avg_score_window`
   - `avg_score_baseline`
   - `trend_delta`
   - `trend_direction`
   - `volatility_window`

### Adaptive Control-Schwellen
In `orchestration/autonomy_scorecard.py`:
1. `_adaptive_control_thresholds(...)` passt `promote/rollback` an:
   - `tighten` bei fallendem/volatilem Trend
   - `relax` bei stabilem Aufwaertstrend
2. `evaluate_and_apply_scorecard_control(...)` gibt die aktiven Schwellen + Adaptive-Status zurueck.

### Runner/Status-Integration
1. Runner persistiert pro Heartbeat den Snapshot vor der Control-Entscheidung.
2. CLI/Telegram zeigen zusaetzlich `Scorecard-Trend`.

## Neue ENV-Parameter
1. `AUTONOMY_SCORECARD_ADAPTIVE_THRESHOLDS_ENABLED=false`
2. `AUTONOMY_SCORECARD_TREND_BASELINE_DAYS=30`

## Kompatibilitaet
1. Additive Erweiterung.
2. Adaptive Schwellen standardmaessig inaktiv.
3. Ohne neue Flags bleibt M5.2-Verhalten unveraendert.
