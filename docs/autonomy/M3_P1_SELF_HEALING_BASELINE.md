# M3.1 Self-Healing Baseline

Stand: 2026-02-25

## Ziel
Erste belastbare Self-Healing-Schicht fuer Timus:
1. Infrastruktur-/Betriebsstoerungen frueh erkennen.
2. Vorfaelle persistent protokollieren (Incident-Store).
3. Recovery-Playbooks automatisch anstossen.

## Baseline-Checks
1. MCP Health (`/health` erreichbar und `status=healthy`)
2. Systemdruck (CPU/RAM/Disk gegen Schwellwerte)
3. Queue-Backlog (pending ueber Schwellwert)
4. Failure-Spike (fehlgeschlagene Tasks im Zeitfenster)

## Datenmodell (additiv)
Neue Tabelle `self_healing_incidents` in `orchestration/task_queue.py`:
1. `incident_key` (dedupliziert Ereignisse)
2. `component`, `signal`, `severity`, `status`
3. `title`, `details`, `recovery_action`, `recovery_status`
4. `first_seen_at`, `last_seen_at`, `recovered_at`

## Queue-APIs
1. `upsert_self_healing_incident(...)`
2. `resolve_self_healing_incident(...)`
3. `list_self_healing_incidents(...)`
4. `get_self_healing_incident(...)`
5. `get_self_healing_metrics()`

## Engine
Neues Modul: `orchestration/self_healing_engine.py`

Verhalten:
1. Fuehrt die vier Baseline-Checks pro Zyklus aus.
2. Oeffnet/Reopened Incidents idempotent.
3. Startet Playbook bei neuen/reopened Incidents:
   - Queue-Task mit `task_type=triggered`
   - Agent-Ziel je Signal (`system` oder `meta`)
4. Markiert Incidents automatisch als `recovered`, sobald Signal wieder gesund.

## Laufzeitintegration
`orchestration/autonomous_runner.py`:
1. Aktivierung nur bei:
   - `AUTONOMY_COMPAT_MODE=false`
   - `AUTONOMY_SELF_HEALING_ENABLED=true`
2. Zyklus pro Heartbeat.
3. KPI-Export als `self_healing_kpi` (Log + optional Canvas).

## Operator-Sicht
1. Telegram `/tasks` + `/status`: Healing-Metriken
2. CLI `/tasks`: Healing-Kurzstatus

## Kompatibilitaet
1. Additive Erweiterung ohne Signatur-Breaks.
2. M0-Flag-Vertrag bleibt unveraendert.
3. Bestehende M1/M2-Funktionen unveraendert nutzbar.
