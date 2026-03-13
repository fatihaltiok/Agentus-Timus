# Bericht: Self-Modification Program v1.5 - SM1

Datum: 2026-03-13

## Ziel

Timus bekommt fuer Level 2 der autonomen Selbstmodifikation zuerst eine **formale Change Policy**, bevor Risk Classifier, isolierte Patch-Pipeline oder autonomes Apply folgen.

SM1 beantwortet vier Fragen:

1. Welche Dateien darf Timus autonom aendern?
2. Welche Aenderungstypen sind dort ueberhaupt erlaubt?
3. Welche Testziele sind pro Aenderungszone Pflicht?
4. Welche Bereiche bleiben immer blockiert?

## Umgesetzt

### 1. Zentrales Policy-Modul

Neu in [orchestration/self_modification_policy.py](/home/fatih-ubuntu/dev/timus/orchestration/self_modification_policy.py):

- gesperrte Zonen wie:
  - `.env`
  - `server/**`
  - `gateway/**`
  - `agent/agents/**`
  - `orchestration/autonomous_runner.py`
  - `orchestration/self_modifier_engine.py`
  - `tools/email_tool/**`
  - `tools/shell_tool/**`
  - `tools/voice_tool/**`
- freigegebene Low-Risk-Zonen wie:
  - `agent/prompts.py`
  - `orchestration/meta_*.py`
  - `orchestration/orchestration_policy.py`
  - `orchestration/browser_workflow_*.py`
  - `tests/test_*.py`
  - `docs/*.md`
- erlaubte Aenderungstypen pro Zone
- Pflicht-Testziele pro Zone

### 2. SelfModifierEngine integriert die Policy

In [orchestration/self_modifier_engine.py](/home/fatih-ubuntu/dev/timus/orchestration/self_modifier_engine.py):

- Policy wird direkt nach `safety_check(...)` ausgewertet
- gesperrte Pfade werden mit `status="blocked"` beendet
- freigegebene Pfade ziehen ihre zonenspezifischen Testziele
- `SelfModifyResult` traegt jetzt auch `policy_zone`

### 3. Tests angepasst und erweitert

Neu:
- [tests/test_self_modification_policy.py](/home/fatih-ubuntu/dev/timus/tests/test_self_modification_policy.py)
- [tests/test_self_modification_policy_contracts.py](/home/fatih-ubuntu/dev/timus/tests/test_self_modification_policy_contracts.py)

Erweitert:
- [tests/test_self_modifier_engine.py](/home/fatih-ubuntu/dev/timus/tests/test_self_modifier_engine.py)

Neue Absicherung:
- `agent/agents/meta.py` ist fuer autonome Selbstmodifikation blockiert, obwohl der Editor-Whitelist-Pfad das generell hergaebe
- `orchestration/meta_orchestration.py` ist als erlaubte Low-Risk-Zone testseitig abgesichert
- zonenspezifische Testtargets werden wirklich an den SelfModifier weitergereicht

## Bewusste Grenzen

SM1 macht **noch nicht**:

- Risk Classification `low / medium / high`
- isolierte Worktrees oder Branch-Patches
- Hard Verification Gates ueber `pytest` hinaus
- Canary oder Rollback-Steuerung
- autonomes Anwenden von Changes

Das ist beabsichtigt. SM1 ist nur das formale Regelwerk, auf dem die spaeteren Phasen aufbauen.

## Naechste sinnvolle Schritte

1. `SM2` Risk Classifier
2. `SM3` Isolierte Patch Pipeline
3. danach erst `SM4` Hard Verification Gate
