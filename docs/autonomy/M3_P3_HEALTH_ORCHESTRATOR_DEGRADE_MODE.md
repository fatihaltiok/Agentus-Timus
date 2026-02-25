# M3.3 Health-Orchestrator + Degrade-Mode

Stand: 2026-02-25

## Ziel
M3.2 wird um eine koordinierende Schicht erweitert:
1. Recovery-Aktionen werden priorisiert geroutet (Agent, Prioritaet, Lane, Template).
2. Self-Healing ermittelt einen globalen Betriebsmodus (`normal|degraded|emergency`).
3. Der Modus wird persistent gespeichert und in Runner/Status sichtbar gemacht.

## Datenmodell (additiv)
`self_healing_runtime_state` wird aktiv genutzt:
1. `state_key=degrade_mode`
2. `state_value` = `normal|degraded|emergency`
3. `metadata` enthaelt `reason`, `reason_codes`, `score`, `inputs`, Routing-Summary

Neue Queue-APIs in `orchestration/task_queue.py`:
1. `set_self_healing_runtime_state(...)`
2. `get_self_healing_runtime_state(...)`
3. `get_self_healing_metrics()` erweitert um:
   - `degrade_mode`
   - `degrade_reason`
   - `degrade_updated_at`

## Health-Orchestrator
Neues Modul: `orchestration/health_orchestrator.py`

### Recovery-Routing
Routing pro Signal auf Basis von `component/signal/severity`:
1. Ziel-Agent (`system` oder `meta`)
2. Prioritaet (inkl. Escalation auf `CRITICAL` fuer kritische Pfade)
3. Lane (`self_healing_fast_lane|self_healing_standard_lane|self_healing_observe_lane`)
4. Playbook-Template-Mapping

### Degrade-Mode
`evaluate_degrade_mode(...)` nutzt:
1. offene Incidents
2. offene Circuit Breaker
3. offene High/Critical-Incidents
4. ungesunde Health-Signale des aktuellen Zyklus

Schwellwerte sind via ENV konfigurierbar:
1. `AUTONOMY_SELF_HEALING_DEGRADED_OPEN_THRESHOLD`
2. `AUTONOMY_SELF_HEALING_DEGRADED_BREAKERS_OPEN_THRESHOLD`
3. `AUTONOMY_SELF_HEALING_EMERGENCY_OPEN_THRESHOLD`
4. `AUTONOMY_SELF_HEALING_EMERGENCY_BREAKERS_OPEN_THRESHOLD`
5. `AUTONOMY_SELF_HEALING_EMERGENCY_HIGH_SEVERITY_THRESHOLD`

## Engine-Integration
`orchestration/self_healing_engine.py`:
1. Jede Incident-Registrierung holt zuerst eine Routing-Entscheidung vom Orchestrator.
2. Routing wird in Summary + Incident-Details + Playbook-Metadata dokumentiert.
3. Am Zyklusende wird `degrade_mode` berechnet und in Runtime-State persistiert.
4. Summary liefert jetzt zusaetzlich:
   - `routed_playbooks`, `routed_by_agent`, `routed_by_lane`, `routed_by_template`
   - `degrade_mode`, `degrade_reason`, `degrade_mode_changed`, `degrade_score`

## Operator-Sicht
1. Runner-Heartbeat und KPI-Log zeigen den aktuellen Degrade-Mode.
2. Telegram `/tasks` und `/status` zeigen `Mode <degrade_mode>` in der Healing-Zeile.
3. CLI `/tasks` zeigt ebenfalls den Mode in der Healing-Zeile.

## Kompatibilitaet
1. Vollstaendig additive Erweiterung.
2. Keine Breaking-Signatur fuer bestehende APIs.
3. Verhalten bleibt hinter `AUTONOMY_SELF_HEALING_ENABLED`.
