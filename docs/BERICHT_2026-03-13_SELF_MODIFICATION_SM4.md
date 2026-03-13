# Self-Modification SM4

## Ziel

SM4 zieht einen harten Verifikations-Gate vor jede autonome Anwendung von Self-Modification.

## Umsetzung

- Neues Verifikationsmodul: `orchestration/self_modification_verification.py`
- Policy-Zonen definieren jetzt nicht nur Testtargets, sondern auch Pflicht-Checks
- `SelfModifierEngine` promotet isolierte Patches erst nach erfolgreich bestandenem Verifikationslauf

## Pflicht-Checks

- `py_compile`
- `pytest_targeted`
- `crosshair` fuer geeignete Contract-Dateien
- `lean` fuer Policy-/Workflow-Zonen
- `production_gates`

## Verhalten

- Fehler in einem einzelnen Pflicht-Check stoppen die Promotion
- Die isolierte Workspace-Pipeline aus SM3 bleibt erhalten
- `SelfModifyResult` enthaelt jetzt zusaetzlich eine `verification_summary`

## Wirkung

Autonome Selbstmodifikation ist damit nicht mehr nur policy- und risikogesteuert, sondern muss vor Anwendung einen harten, zonenspezifischen Verifikationslauf bestehen.
