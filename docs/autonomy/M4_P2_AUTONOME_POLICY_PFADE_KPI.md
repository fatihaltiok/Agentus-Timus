# M4.2 Autonome Policy-Pfade + KPI-Monitoring

Stand: 2026-02-25

## Ziel
Die formalen Policy-Gates aus M4.1 werden auf autonome Ausfuehrungspfade erweitert:
1. Autonome Task-Ausfuehrung (Runner) erhaelt eigenes Gate.
2. Self-Healing-Playbooks werden vor Queue-Enqueue policy-geprueft.
3. Policy-Entscheidungen werden als 24h-KPIs sichtbar (Runner/Telegram/CLI/Canvas).

## Erweiterungen in `utils/policy_gate.py`
1. Neuer Gate-Typ: `autonomous_task`
2. Neue Metrik-API: `get_policy_decision_metrics(window_hours=24)`
   - `decisions_total`
   - `blocked_total`
   - `observed_total`
   - `allowed_total`
   - `strict_decisions`
   - `by_gate`, `by_source`
   - `last_blocked`

## Kritische Pfade (M4.2)
1. `orchestration/autonomous_runner.py`
   - vor Task-Ausfuehrung: `evaluate_policy_gate(gate=\"autonomous_task\", ...)`
   - strict-blocked Tasks werden direkt als failed markiert
   - neue KPI-Exportfunktion: `_export_policy_kpi_snapshot()`
2. `orchestration/self_healing_engine.py`
   - `_trigger_playbook()` prueft Playbook-Task via `autonomous_task`-Gate
   - blockierte Entscheidungen erhoehen `policy_blocks` im Cycle-Summary

## Operator-Sicht
1. Telegram:
   - `/tasks` und `/status` zeigen `Policy(24h)` mit Decisions/Blocked/Observed.
2. CLI:
   - `/tasks` zeigt `Policy(24h)` Zeile.
3. Runner/Canvas:
   - `policy_kpi` Events mit 24h-Metriken.

## Kompatibilitaet
1. Additive Erweiterung ohne Signaturaenderungen.
2. Behavior bleibt an bestehende Flags gekoppelt (`strict`/`audit` + `compat`).
3. M3-, Delegation-, Milestone5/6-Gates bleiben gruen.
