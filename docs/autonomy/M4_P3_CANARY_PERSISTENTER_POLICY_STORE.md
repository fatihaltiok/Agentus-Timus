# M4.3 Canary-Rollout + Persistenter Policy-Store

Stand: 2026-02-25

## Ziel
M4.2 wird um zwei fehlende Bausteine erweitert:
1. Strict-Enforcement kann kontrolliert per Canary ausgerollt werden.
2. Policy-Entscheidungen werden persistent in der Timus-DB gespeichert (nicht nur JSONL).

## Canary-Rollout (Strict)
In `utils/policy_gate.py`:
1. `AUTONOMY_CANARY_PERCENT` steuert den Rollout fuer strict-blocking (1-99%).
2. Deterministische Bucket-Entscheidung (`_canary_bucket_for_key`) pro Gate/Source/Subject.
3. Regeln:
   - `hard_block` bleibt immer blockierend.
   - strict + canary defer => `observe` statt `block` (mit `canary_deferred`).
4. Entscheidungsfelder erweitert:
   - `canary_percent`
   - `canary_bucket`
   - `canary_enforced`

## Persistenter Policy-Store
In `orchestration/task_queue.py`:
1. Neue Tabelle `policy_decisions`:
   - Gate/Source/Subject
   - Action/Blocked/Strict
   - Violations/Payload
   - Canary-Felder
   - Timestamp
2. Neue APIs:
   - `record_policy_decision(...)`
   - `list_policy_decisions(...)`
   - `get_policy_decision_metrics(...)`

`audit_policy_decision(...)` schreibt ab jetzt best-effort in den DB-Store.

## Metrikquelle
`utils.policy_gate.get_policy_decision_metrics(...)`:
1. Primaerquelle: DB-Metriken aus `TaskQueue`.
2. Fallback: bisherige JSONL-Auswertung.

## Operator-Sicht
Runner/Telegram/CLI zeigen nun zusaetzlich:
1. `canary_deferred_total` (24h)
2. damit ist sichtbar, welche strict-Entscheidungen im Canary bewusst nur beobachtet wurden.

## Kompatibilitaet
1. Additive DB-Erweiterung, keine Signatur-Breaks.
2. `AUTONOMY_CANARY_PERCENT=0` behaelt bisheriges strict-Verhalten bei.
3. Bestehende M3/M4.1/M4.2-Pfade bleiben kompatibel und testbar.
