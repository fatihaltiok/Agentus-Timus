# M0.2 Test-Matrix und Gate-Strategie

Stand: 2026-02-25

## Ziel
Fehler frueh erkennen, bevor Architektur-Inkompatibilitaeten entstehen.

## Testebenen
1. `Contract`-Tests: Signaturen, Kernpfade, Pflichtmodule.
2. `Regression`-Tests: bestehende Quality-Gates bleiben stabil.
3. `Integration`-Tests: Dispatcher -> Agent -> Logging -> Queue.
4. `Safety`-Tests: Policy- und Delegationsgrenzen.

## Pflicht-Gates je Meilenstein-Phase
1. Gate A (schnell): neue/angepasste Unit- und Contract-Tests.
2. Gate B (regression): `tests/test_milestone5_quality_gates.py`.
3. Gate C (readiness): `tests/test_milestone6_e2e_readiness.py`.
4. Gate D (optional bei Core-Eingriff): betroffene Integrationssuite.

## Minimaler Befehlsplan pro Phase
1. `pytest -q tests/test_m0_autonomy_contracts.py`
2. `pytest -q tests/test_milestone5_quality_gates.py`
3. `pytest -q tests/test_milestone6_e2e_readiness.py`

## Abbruchkriterien
1. Signatur/Contract-Fehler in Kernpfaden.
2. Regression in Milestone5/6-Gates.
3. Feature-Flag wirkt nicht (aktiviert Verhalten trotz Default `false`).

## Artefakte pro Phase
1. Test-Output (kurz) im Phasenprotokoll.
2. Geaenderte Dateien + Risikoeinschaetzung.
3. Entscheidung `Go` oder `No-Go`.
