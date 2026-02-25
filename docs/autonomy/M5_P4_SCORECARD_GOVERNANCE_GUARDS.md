# M5.4 Scorecard Governance Guards

Stand: 2026-02-25

## Ziel
Harte Governance-Regeln fuer den Control-Loop:
1. Promotion nur bei stabilen Mindest-Pillar-Werten.
2. Kritische Pillar-Verletzungen erzwingen sofortigen Rollback.
3. Negative Trendlagen koennen Promotion einfrieren.

## Architektur
### Governance-Auswertung
In `orchestration/autonomy_scorecard.py`:
1. Neue Governance-Funktionen:
   - `_scorecard_governance_enabled()`
   - `_evaluate_scorecard_governance(...)`
2. Governance-Zustaende:
   - `allow`
   - `freeze` (Promotion-Stop)
   - `force_rollback`
3. Guard-Signale:
   - Pillar unter `MIN_PILLAR_SCORE` -> `freeze`
   - Pillar unter `CRITICAL_PILLAR_SCORE` -> `force_rollback`
   - optional Trend-Freeze bei Delta/Volatilitaet

### Control-Loop-Integration
In `evaluate_and_apply_scorecard_control(...)`:
1. Governance wird vor Promotion-Logik ausgewertet.
2. `force_rollback` ueberschreibt Cooldown und setzt:
   - `strict_force_off=true`
   - `canary_percent_override=0`
3. `freeze` blockiert Promotion und erzeugt `governance_hold`.

### Runtime-Sichtbarkeit
1. Persistenz in `policy_runtime_state`:
   - `scorecard_governance_state`
2. Scorecard-Control-State zeigt:
   - Governance-State
   - Governance-Reason
3. CLI/Telegram erweitern `Control` Ausgabe um Governance-Status.

## Neue ENV-Parameter
1. `AUTONOMY_SCORECARD_GOVERNANCE_ENABLED=false`
2. `AUTONOMY_SCORECARD_MIN_PILLAR_SCORE=60`
3. `AUTONOMY_SCORECARD_CRITICAL_PILLAR_SCORE=40`
4. `AUTONOMY_SCORECARD_FREEZE_ON_DECLINING=true`
5. `AUTONOMY_SCORECARD_DECLINE_DELTA=-6`
6. `AUTONOMY_SCORECARD_VOLATILITY_FREEZE_THRESHOLD=12`

## Kompatibilitaet
1. Additive Erweiterung.
2. Governance standardmaessig deaktiviert.
3. Bei deaktiviertem Flag bleibt M5.3-Verhalten unveraendert.
