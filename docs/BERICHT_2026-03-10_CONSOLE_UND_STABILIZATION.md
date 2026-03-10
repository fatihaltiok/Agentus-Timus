# Bericht 2026-03-10 - Console, Self-Stabilization und Headless-Hardening

## Ziel

Timus sollte am 10. Maerz 2026 in drei Richtungen gleichzeitig produktionsnaeher werden:

1. autonome Prozesse ruhiger und stabiler machen
2. lokale Service-Kontexte strikt headless halten
3. eine mobile, externe Web-Konsole als primaere Oberflaeche vorbereiten

## Umgesetzt

### 1. Self-Stabilization S1-S6

Der Self-Healing-Pfad wurde zu einem echten Stabilisierungssystem ausgebaut:

- `S1` Incident-Dedupe + Cooldown fuer autonome Benachrichtigungen
- `S2` Recovery-Leiter mit `ok`, `degraded`, `recovering`, `blocked`
- `S3` Quarantine + Circuit Breaker fuer identische Stoerfaelle
- `S4` Resource-Guard fuer RAM-/Swap-/Queue-Druck
- `S5` Incident-Memory fuer bekannte schlechte Muster
- `S6` `self_stabilization_gate` als sichtbares Runtime-Gate

Betroffene Kernpfade:

- [orchestration/autonomous_runner.py](/home/fatih-ubuntu/dev/timus/orchestration/autonomous_runner.py)
- [orchestration/self_healing_engine.py](/home/fatih-ubuntu/dev/timus/orchestration/self_healing_engine.py)
- [orchestration/task_queue.py](/home/fatih-ubuntu/dev/timus/orchestration/task_queue.py)
- [orchestration/self_stabilization_gate.py](/home/fatih-ubuntu/dev/timus/orchestration/self_stabilization_gate.py)
- [gateway/status_snapshot.py](/home/fatih-ubuntu/dev/timus/gateway/status_snapshot.py)

### 2. Headless-Service-Hardening

Timus darf im Service-Kontext keine lokalen GUI-Aktionen mehr ausloesen. Dafuer wurde ein zentraler Guard eingezogen:

- blockiert `code`, `xdg-open`, `gio open`, Browser-Starts und aehnliche Desktop-Aktionen
- schuetzt Logdateien und Runtime-Artefakte vor versehentlichem lokalen Oeffnen
- deaktiviert Canvas-Auto-Open unter systemd

Betroffene Kernpfade:

- [utils/headless_service_guard.py](/home/fatih-ubuntu/dev/timus/utils/headless_service_guard.py)
- [tools/application_launcher/tool.py](/home/fatih-ubuntu/dev/timus/tools/application_launcher/tool.py)
- [agent/base_agent.py](/home/fatih-ubuntu/dev/timus/agent/base_agent.py)
- [agent/visual_nemotron_agent_v4.py](/home/fatih-ubuntu/dev/timus/agent/visual_nemotron_agent_v4.py)
- [server/mcp_server.py](/home/fatih-ubuntu/dev/timus/server/mcp_server.py)

### 3. Console Phase 1 - Proxy, HTTPS, Auth

Die externe Konsole wurde unter einer eigenen Subdomain vorbereitet:

- Ziel-Domain: `console.fatih-altiok.com`
- Reverse Proxy: `Caddy`
- TLS: Let’s Encrypt
- Zugriff: vorgeschaltete Auth

Die echte Referenzkonfiguration liegt in:

- [deploy/console/Caddyfile.example](/home/fatih-ubuntu/dev/timus/deploy/console/Caddyfile.example)
- [deploy/console/timus-console.env.example](/home/fatih-ubuntu/dev/timus/deploy/console/timus-console.env.example)
- [docs/CONSOLE_PHASE1_PROXY_HTTPS_AUTH_2026-03-10.md](/home/fatih-ubuntu/dev/timus/docs/CONSOLE_PHASE1_PROXY_HTTPS_AUTH_2026-03-10.md)

### 4. Console Phase 2-6 - Mobile Canvas Console

Die bestehende Canvas UI wurde zur mobilen Konsole ausgebaut, statt eine zweite Web-App daneben zu bauen.

#### Phase 2 - Mobile Informationsarchitektur

- Bottom-Navigation fuer `Home`, `Status`, `Voice`, `Chat`, `Dateien`
- mobile Home-Hero-Card mit Session, Score, Voice-Orb und Quick-Pills

#### Phase 3 - Chat + Status

- mobile Status-Karten fuer Services, Ops-Gates, Self-Healing und Agenten
- Chat-Zusammenfassung mit Session- und Voice-Zustand

#### Phase 4 - Dateien + Dokumente

- neue Endpunkte:
  - `/files/recent`
  - `/files/download`
- sichere Dateifreigabe nur aus `results/` und `data/uploads/`
- Dateien koennen direkt geoeffnet, heruntergeladen und im Chat weiterverwendet werden

#### Phase 5 - Voice

- browserseitiges Inworld-Playback ueber `/voice/synthesize`
- Voice-Orb fuer `idle`, `listening`, `thinking`, `speaking`, `error`
- `Auto-Vorlesen` und `Letzte Antwort` in der mobilen UI
- Voice-Status zeigt aktive Stimme und Playback-Modus

#### Phase 6 - Mobile Live-Betrieb

- sichtbarer Live-/Reconnect-/Offline-Zustand
- manuelles Mobile-Refresh
- bessere Reaktion auf `online`, `offline` und `visibilitychange`

Betroffene Hauptdateien:

- [server/canvas_ui.py](/home/fatih-ubuntu/dev/timus/server/canvas_ui.py)
- [server/mcp_server.py](/home/fatih-ubuntu/dev/timus/server/mcp_server.py)
- [tools/voice_tool/tool.py](/home/fatih-ubuntu/dev/timus/tools/voice_tool/tool.py)
- [utils/voice_text.py](/home/fatih-ubuntu/dev/timus/utils/voice_text.py)

## Wichtige Tests

Direkt fuer diese Session erweitert oder neu:

- [tests/test_headless_service_guard.py](/home/fatih-ubuntu/dev/timus/tests/test_headless_service_guard.py)
- [tests/test_headless_service_protection.py](/home/fatih-ubuntu/dev/timus/tests/test_headless_service_protection.py)
- [tests/test_self_healing_incident_memory.py](/home/fatih-ubuntu/dev/timus/tests/test_self_healing_incident_memory.py)
- [tests/test_self_healing_quarantine.py](/home/fatih-ubuntu/dev/timus/tests/test_self_healing_quarantine.py)
- [tests/test_self_healing_recovery_ladder.py](/home/fatih-ubuntu/dev/timus/tests/test_self_healing_recovery_ladder.py)
- [tests/test_self_stabilization_gate.py](/home/fatih-ubuntu/dev/timus/tests/test_self_stabilization_gate.py)
- [tests/test_canvas_ui_m1.py](/home/fatih-ubuntu/dev/timus/tests/test_canvas_ui_m1.py)
- [tests/test_console_files.py](/home/fatih-ubuntu/dev/timus/tests/test_console_files.py)
- [tests/test_console_voice.py](/home/fatih-ubuntu/dev/timus/tests/test_console_voice.py)
- [tests/test_console_voice_contracts.py](/home/fatih-ubuntu/dev/timus/tests/test_console_voice_contracts.py)

## Verifikation

Gruen gelaufen:

- `py_compile`
- `pytest` fuer die gezielten Guard-, Self-Healing-, Console-, File- und Voice-Schnitte
- `CrossHair`
- `Lean`
- `bandit`
- `python scripts/run_production_gates.py`

Letzter Gesamtstand:

- `READY | total=4 passed=4 failed=0 skipped=0 blocking_failed=0`

## Ergebnis

Timus ist nach dieser Session deutlich ruhiger und bedienbarer:

- weniger Eskalationsspam
- weniger selbstverursachte Service-Stoerungen
- keine lokalen Desktop-Aktionen mehr im Service-Kontext
- mobile, externe Konsole fuer Chat, Status, Dateien und Voice

Der naechste sinnvolle Schritt ist jetzt eine echte Live-Betriebsprobe der neuen Konsole auf dem Smartphone und danach ein gezielter Feinschliff fuer Auth, Session-Management und echte Session-gebundene Datei-/Voice-Historie.
