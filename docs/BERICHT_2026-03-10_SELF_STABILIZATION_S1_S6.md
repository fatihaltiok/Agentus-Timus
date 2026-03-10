# Bericht 2026-03-10: Self-Stabilization S1-S6

## Ziel

Timus sollte bei Betriebsstoerungen nicht mehr nervoes, redundant oder selbstschaedlich reagieren, sondern kontrolliert:
- Incidents deduplizieren
- Recovery stufenweise fahren
- kaputte Pfade quarantänisieren
- Lastdruck aktiv drosseln
- aus wiederkehrenden Vorfaellen lernen
- diese Stabilisierung als sichtbares Live-Gate in Runtime und Ops fuehren

## Umgesetzt

### S1: Incident-Dedupe + Cooldown
- autonome Incident-Benachrichtigungen werden pro `incident_key` gedrosselt
- gleicher Vorfall erzeugt innerhalb des Cooldowns keine Mail-/Telegram-Flut mehr
- Notification-State wird in `self_healing_runtime_state` persistiert

Relevante Dateien:
- `orchestration/autonomous_runner.py`
- `gateway/status_snapshot.py`

### S2: Recovery-Leiter
- offene Self-Healing-Incidents haben jetzt explizite Phasen und Stufen
- Phasen: `degraded`, `recovering`, `blocked`, `ok`
- Stufen: `observe`, `diagnose`, `fallback`, `breaker_cooldown`, `manual_review`, `human_escalation`
- harte Eskalation erst bei verifiziertem Outage oder ausgeschoepfter Leiter

Relevante Dateien:
- `orchestration/self_healing_engine.py`
- `gateway/status_snapshot.py`

### S3: Circuit Breaker + Quarantine
- Self-Healing-Tasks werden bei offenem Breaker nicht blind weiter ausgefuehrt
- stattdessen Requeue mit Quarantaene-Zustand und Wiederanlaufzeit

Relevante Dateien:
- `orchestration/autonomous_runner.py`
- `orchestration/task_queue.py`
- `gateway/status_snapshot.py`

### S4: Ressourcen-Stabilisierung
- schwere `NORMAL/LOW`-Autonomy-Tasks werden bei `degrade_mode` und Systemdruck verschoben
- Resource-Guard verhindert weiteres Aufstauen unter Last

Relevante Dateien:
- `orchestration/autonomous_runner.py`
- `orchestration/task_queue.py`
- `gateway/status_snapshot.py`

### S5: Incident-Gedaechtnis
- wiederkehrende Fehlerbilder werden pro `component/signal` gespeichert
- Timus merkt sich:
  - `seen_count`
  - `resolved_count`
  - `escalated_count`
  - `failed_count`
  - `last_outcome`
  - `conservative_mode`
- bekannte schlechte Muster ziehen Recovery frueher auf `known_bad_pattern` bzw. `manual_review`

Relevante Dateien:
- `orchestration/self_healing_engine.py`
- `gateway/status_snapshot.py`

### S6: Live Stability Gate
- neuer Stability-Gate aus dem Self-Healing-Zustand
- bewertet live:
  - offene Incidents
  - Degrade-Mode
  - offene Circuit Breaker
  - Quarantaene
  - Notification-Cooldowns
  - bekannte schlechte Muster
- Gate ist sichtbar im Status und wirkt in die Ops-/Release-Steuerung ein

Relevante Dateien:
- `orchestration/self_stabilization_gate.py`
- `orchestration/ops_observability.py`
- `gateway/status_snapshot.py`

## Tests und Verifikation

Gezielt verifiziert mit:
- `pytest -q tests/test_autonomous_runner_incident_notifications.py`
- `pytest -q tests/test_self_healing_recovery_ladder.py`
- `pytest -q tests/test_self_healing_quarantine.py`
- `pytest -q tests/test_autonomous_runner_resource_guard.py`
- `pytest -q tests/test_self_healing_incident_memory.py`
- `pytest -q tests/test_self_stabilization_gate.py tests/test_ops_observability.py tests/test_ops_release_gate.py tests/test_telegram_status_snapshot.py`
- `python -m crosshair check tests/test_autonomous_runner_incident_contracts.py --analysis_kind=deal`
- `python -m crosshair check tests/test_self_healing_recovery_ladder_contracts.py --analysis_kind=deal`
- `python -m crosshair check tests/test_self_stabilization_gate_contracts.py --analysis_kind=deal`
- `python -m bandit -q -ll orchestration/autonomous_runner.py orchestration/task_queue.py orchestration/self_healing_engine.py orchestration/self_stabilization_gate.py orchestration/ops_observability.py gateway/status_snapshot.py`
- `lean lean/CiSpecs.lean`
- `python scripts/run_production_gates.py`

Endstand:
- `production_gates`: `READY | total=4 passed=4 failed=0 skipped=0 blocking_failed=0`

## Wirkung

Timus reagiert jetzt bei Stoerungen deutlich kontrollierter:
- weniger doppelte Eskalationsmails
- weniger Wiederholung derselben kaputten Recovery-Pfade
- weniger Lastaufbau unter Druck
- schlechtere Incident-Muster werden konservativer behandelt
- Self-Healing ist nicht mehr nur "aktiv", sondern als eigener Stabilitaets-Gate sichtbar und fuer Ops/Release verwertbar

## Naechster sinnvoller Schritt

Echte Live-Betriebsprobe dieser Stabilisierung unter Randbedingungen:
- wiederholter MCP-Ausfall
- Provider-Ausfall
- Queue-Backlog + hoher RAM-/Swap-Druck
- verifizieren, dass Timus in `warn/blocked` sauber drosselt statt erneut zu eskalieren
