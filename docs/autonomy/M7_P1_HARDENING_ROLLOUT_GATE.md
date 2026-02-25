# M7.1 Hardening + Rollout Gate

Stand: 2026-02-25

## Ziel
Vor/autonomem Rollout wird der Systemzustand zentral bewertet und bei Risiken aktiv abgesichert:
1. Einheitlicher Hardening-Zustand `green|yellow|red`.
2. Optionales Enforcement (`freeze` bei gelb, `rollback` bei rot).
3. Sichtbarkeit in Runner, CLI und Telegram.

## Architektur
### Hardening Engine
In `orchestration/autonomy_hardening_engine.py`:
1. `build_rollout_hardening_snapshot(...)` sammelt:
   - Self-Healing-Metriken (Open Incidents, Recovery Rate)
   - Policy-Blockrate (24h)
   - Pending Approvals
   - Autonomy Score
2. `evaluate_and_apply_rollout_hardening(...)` bewertet gegen Schwellwerte.
3. Runtime-States:
   - `hardening_last_state`
   - `hardening_last_action`
   - `hardening_last_reasons`
   - `hardening_*` KPI-States
4. Optionaler Eingriff:
   - `red` -> `strict_force_off=true`, Canary `0`
   - `yellow` -> `hardening_rollout_freeze=true`

### Runner-Integration
In `orchestration/autonomous_runner.py`:
1. Heartbeat ruft Hardening-Bewertung auf.
2. Warn-Log bei `yellow|red` oder aktiver Schutzaktion.

### Integration in Change-Flow
In `orchestration/autonomy_change_control.py`:
1. Promote-Requests respektieren `hardening_rollout_freeze`.
2. Bei aktivem Freeze wird Promote als `hold` behandelt (`hardening_freeze_active`).

## Neue ENV-Parameter
1. `AUTONOMY_HARDENING_ENABLED=false`
2. `AUTONOMY_HARDENING_ENFORCE=false`
3. `AUTONOMY_HARDENING_WINDOW_HOURS=24`
4. `AUTONOMY_HARDENING_MAX_OPEN_INCIDENTS=2`
5. `AUTONOMY_HARDENING_MIN_RECOVERY_RATE_24H=70`
6. `AUTONOMY_HARDENING_MAX_POLICY_BLOCK_RATE_24H=35`
7. `AUTONOMY_HARDENING_MAX_PENDING_APPROVALS=5`
8. `AUTONOMY_HARDENING_MIN_AUTONOMY_SCORE=75`
9. `AUTONOMY_HARDENING_ROLLBACK_ON_RED=true`
10. `AUTONOMY_HARDENING_FREEZE_ON_YELLOW=true`

## Kompatibilitaet
1. Additive Erweiterung hinter `AUTONOMY_HARDENING_ENABLED`.
2. Standardmaessig deaktiviert.
3. Ohne `AUTONOMY_HARDENING_ENFORCE=true` nur Beobachtungsmodus.
