# M3.2 Recovery-Playbooks V2 + Circuit Breaker Basis

Stand: 2026-02-25

## Ziel
M3.1 wird zu einer robusteren Self-Healing-Schicht ausgebaut:
1. Recovery-Playbooks bekommen konkrete, strukturierte Schritte (V2).
2. Circuit Breaker verhindert Recovery-Spam bei persistenten Stoerungen.
3. Nach Cooldown werden kontrollierte Recovery-Retries ausgeloest.

## Datenmodell (additiv)
Neue Tabelle `self_healing_circuit_breakers` in `orchestration/task_queue.py`:
1. `breaker_key`, `component`, `signal`
2. `state` (`closed|open`)
3. `failure_streak`, `trip_count`
4. `cooldown_seconds`, `opened_until`
5. `last_failure_at`, `last_success_at`, `metadata`

## Queue-APIs
1. `record_self_healing_circuit_breaker_result(...)`
2. `get_self_healing_circuit_breaker(...)`
3. `list_self_healing_circuit_breakers(...)`
4. `get_self_healing_circuit_breaker_metrics()`
5. `get_self_healing_metrics()` erweitert um Breaker-Metriken

## Engine-Logik (M3.2)
`orchestration/self_healing_engine.py`:
1. Jeder Health-Signal-Pfad hat einen dedizierten Breaker-Key.
2. Bei Fehlern:
   - Failure-Streak wird aktualisiert
   - Bei Schwellwert wird Breaker `open` und Cooldown gesetzt
3. Bei anhaltendem Fehler:
   - Playbook-Retry nur wenn Cooldown abgelaufen (`retry_due`)
4. Bei gesundem Signal:
   - Incident wird als `recovered` markiert
   - Breaker wird auf `closed` zurueckgesetzt

## Playbooks V2
Playbook-Metadaten enthalten jetzt:
1. `playbook_version = v2`
2. `playbook_template`
3. `playbook_steps` (strukturierte Recovery-Schritte)
4. `suggested_commands` (wo sinnvoll)

Beispiel-Templates:
1. `mcp_recovery`
2. `system_pressure_relief`
3. `queue_backlog_relief`
4. `provider_failover_diagnostics`

## Monitoring / Operator
1. Runner-Logs:
   - Self-Healing Summary inkl. `suppressed` + `trips`
   - KPI inkl. `breakers_open`
2. Telegram/CLI:
   - Healing-Zeile erweitert um `BreakerOpen`

## Kompatibilitaet
1. Additive Erweiterung, keine Signatur-Breaks.
2. Vollstaendig hinter `AUTONOMY_SELF_HEALING_ENABLED`.
3. M1/M2/M3.1 Verhalten bleibt kompatibel.
