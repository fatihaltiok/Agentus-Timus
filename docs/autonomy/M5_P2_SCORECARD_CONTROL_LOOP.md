# M5.2 Scorecard Control-Loop

Stand: 2026-02-25

## Ziel
M5.1 wird operativ wirksam:
1. Scorecard entscheidet automatisch ueber `promote|hold|rollback`.
2. Canary-Rollout wird stufenweise ausgebaut statt statisch konfiguriert.
3. Risiko-Signale (niedriger Score, degradierter Healing-Mode) erzwingen Rollback.

## Architektur
### Control-Loop in `orchestration/autonomy_scorecard.py`
1. Neue Funktion `evaluate_and_apply_scorecard_control(...)`.
2. Verwendet Scorecard + Runtime-State fuer Entscheidungen:
   - `promote_canary`
   - `hold`
   - `rollback_applied`
   - `cooldown_active`
3. Persistiert Runtime-States in `policy_runtime_state`:
   - `canary_percent_override`
   - `strict_force_off`
   - `scorecard_last_action`
   - `scorecard_last_score`

### Runner-Integration
In `orchestration/autonomous_runner.py`:
1. `_apply_autonomy_scorecard_control()` wird pro Heartbeat ausgefuehrt.
2. Warn-Logs bei Promotion, Rollback oder aktivem Cooldown.

### Status/Operator-Sichtbarkeit
1. CLI (`main_dispatcher.py`) zeigt `Scorecard-Control` Zustand.
2. Telegram (`gateway/telegram_gateway.py`) zeigt `Control` Zeile in `/tasks` und `/status`.

## Neue ENV-Parameter
1. `AUTONOMY_SCORECARD_CONTROL_ENABLED=false`
2. `AUTONOMY_SCORECARD_PROMOTE_THRESHOLD=80`
3. `AUTONOMY_SCORECARD_ROLLBACK_THRESHOLD=55`
4. `AUTONOMY_SCORECARD_PROMOTE_STEP=10`
5. `AUTONOMY_SCORECARD_MAX_CANARY=100`
6. `AUTONOMY_SCORECARD_CONTROL_COOLDOWN_MIN=120`

## Kompatibilitaet
1. Rein additive Erweiterung.
2. Standardmaessig deaktiviert (`AUTONOMY_SCORECARD_CONTROL_ENABLED=false`).
3. Keine Breaking-Signaturaenderungen.
