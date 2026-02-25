# M6.1 Autonomy Audit Report Export

Stand: 2026-02-25

## Ziel
Operative Nachvollziehbarkeit fuer Rollout-Entscheidungen:
1. Mehr-Tages-Autonomieprofil als Report exportieren.
2. Klare Empfehlung `promote|hold|rollback` ableiten.
3. Empfehlung und Exportpfad persistent fuer Operatoren bereitstellen.

## Architektur
### Neues Modul
In `orchestration/autonomy_audit_report.py`:
1. `build_autonomy_audit_report(...)`
2. `export_autonomy_audit_report(...)`
3. `should_export_audit_report(...)`

### Report-Inhalt
1. Scorecard-Zusammenfassung (inkl. Control/Pillars)
2. Trends (Fenster + Baseline)
3. Policy-Metriken
4. Rollout-Policy:
   - `recommendation`
   - `reason`
   - `risk_flags`

### Runner-Integration
In `orchestration/autonomous_runner.py`:
1. Feature-Flag `AUTONOMY_AUDIT_REPORT_ENABLED`
2. Cadence-Pruefung vor Export
3. Export-Event im Canvas als `autonomy_audit_report`

### Runtime-State
In `policy_runtime_state`:
1. `audit_report_last_path`
2. `audit_report_last_recommendation`
3. `audit_report_last_exported_at`

## Neue ENV-Parameter
1. `AUTONOMY_AUDIT_REPORT_ENABLED=false`
2. `AUTONOMY_AUDIT_REPORT_CADENCE_HOURS=6`
3. `AUTONOMY_AUDIT_REPORT_WINDOW_DAYS=7`
4. `AUTONOMY_AUDIT_REPORT_BASELINE_DAYS=30`

## Kompatibilitaet
1. Additive Erweiterung ohne Signatur-Breaks.
2. Default inaktiv.
3. Bei deaktiviertem Flag kein zusaetzlicher Laufzeitpfad.
