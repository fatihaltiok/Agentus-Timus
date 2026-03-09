# Timus Restart Status Report

Datum: 2026-03-08

## Kurzfassung

Die vorherige Version dieses Reports hat Beobachtungen, Hypothesen und Code-Status vermischt.

Was aktuell belegt ist:

- Der Detached-Restart-Ansatz aus Commit `3e360b4` existiert.
- Die lokalen Agent-Änderungen für einen terminalen Restart-Pfad existieren im Working Tree.
- Diese lokalen Agent-Änderungen waren aber nicht end-to-end wirksam, weil `restart_timus` zur Laufzeit als normalisierter Tool-Envelope mit `status: "success"` ankommt und `pending_restart` unter `data.status` steckt.
- Dadurch hat der Agent nach `restart_timus(...)` weiterhin weitere Tool-Calls ausgeführt.
- Ein echter systemd-Stop-Timeout von `timus-mcp.service` ist inzwischen ebenfalls belegt.

Was nicht sauber belegt war und deshalb in diesem Report nicht mehr als Fakt behauptet wird:

- `Waiting for connections to close.` als gesicherter aktueller Bruchpunkt
- dass der MCP-Timeout allein die gesamte Fehlerserie erklärt

## Gesicherte Beobachtungen aus Logs und Workspace

### 1. Restart-Lauf um 16:15 CET

Quelle: `logs/2026-03-08_task_126c1053.jsonl`

- `16:15:57` `restart_timus(mode="full")` wurde gestartet.
- `16:15:58` `timus-mcp.service` war `active (running)`.
- `16:15:59` `timus-dispatcher.service` war `inactive (dead)`.
- Direkt danach hat der Agent weitergemacht und weitere Tools aufgerufen.
- Diese Folgeaufrufe liefen in `All connection attempts failed`.

Das ist wichtig: Der beobachtete Fehlerpfad war in diesem Lauf nicht "MCP stoppt wegen offenem Uvicorn-Shutdown-Timeout", sondern "Agent ruft nach gestartetem Restart im selben Run weitere Tools auf".

### 2. Restart-Lauf um 16:30 CET

Quelle: `logs/2026-03-08_task_1cde98d5.jsonl`

- Der Shell-Kontext zeigte vor dem Restart: `Services: timus-mcp=active, timus-dispatcher=active`.
- `restart_timus(mode="full")` wurde erneut gestartet.
- Die Tool-Observation kam als normalisierter Envelope zurück:
  - top-level `status: "success"`
  - nested `data.status: "pending_restart"`
- Der neue Code in `agent/base_agent.py` prüfte nur top-level `status == "pending_restart"`.
- Deshalb griff der behauptete terminale Early-Exit nicht.
- Der Agent antwortete erst prose-artig, erzeugte einen Parse-Error und schrieb erst danach eine `Final Answer`.

Damit war der lokale "terminale Restart-Pfad" zwar implementiert, aber nicht korrekt an den tatsächlichen Tool-Envelope angepasst.

### 3. Aktuelle Restart-Artefakte im Workspace

Stand der Dateien:

- `logs/timus_restart_status.json`
  - aktuell: `status: "running"`, `phase: "preflight"`
  - Timestamp: `2026-03-08T15:53:51Z`
- `logs/timus_restart_detached.log`
  - Größe: `0` Bytes

Diese beiden Dateien zeigen weiterhin, dass der Supervisor-/Statuspfad den echten Abschluss nicht verlässlich widerspiegelt.

### 4. Journald-Beleg für echten MCP-Stop-Timeout

Quelle: vom Nutzer gelieferte Journal-Ausgabe vom `2026-03-08`

Gesichert beobachtet:

- `16:54:21` bis `16:54:27`: Der META-Agent ruft nach dem Restart weiterhin Tools auf und läuft in `All connection attempts failed`.
- `16:54:42`: Die finale Antwort behauptet trotzdem: "System-Neustart erfolgreich initiiert" und stuft die Verbindungsfehler als normal während des Neustarts ein.
- `16:55:24`: systemd meldet:
  - `timus-mcp.service: State 'stop-sigterm' timed out. Killing.`
  - `timus-mcp.service: Main process exited, code=killed, status=9/KILL`
  - `timus-mcp.service: Failed with result 'timeout'.`

Damit sind jetzt zwei getrennte Tatsachen belegt:

- Der Agent lief nach dem Restart unzulässig weiter.
- Der MCP-Service lief beim Stop zusätzlich in einen echten systemd-Timeout.

### 5. Verifikation der lokalen Änderungen

Bestätigt:

- `pytest -q tests/test_base_agent_tool_envelope.py tests/test_restart_timus_safety.py`
  - `17 passed`
- `python -m py_compile agent/base_agent.py agent/prompts.py tools/shell_tool/tool.py scripts/restart_supervisor.py`
  - erfolgreich
- `lean lean/CiSpecs.lean`
  - erfolgreich

Wichtig: Die ursprüngliche Testabdeckung war unvollständig. Sie prüfte den Raw-Return `{"status": "pending_restart"}`, aber nicht den normalisierten JSON-RPC-Envelope mit `data.status`.

## Code-Status

### Bereits gepusht

Commit:

- `3e360b4` `fix(restart): add detached supervisor and hard preflight`

Betroffene Dateien:

- [tools/shell_tool/tool.py](/home/fatih-ubuntu/dev/timus/tools/shell_tool/tool.py)
- [scripts/restart_timus.sh](/home/fatih-ubuntu/dev/timus/scripts/restart_timus.sh)
- [scripts/restart_supervisor.py](/home/fatih-ubuntu/dev/timus/scripts/restart_supervisor.py)
- [tests/test_restart_timus_safety.py](/home/fatih-ubuntu/dev/timus/tests/test_restart_timus_safety.py)
- [lean/CiSpecs.lean](/home/fatih-ubuntu/dev/timus/lean/CiSpecs.lean)

### Lokal vorhanden

- [agent/base_agent.py](/home/fatih-ubuntu/dev/timus/agent/base_agent.py)
- [agent/prompts.py](/home/fatih-ubuntu/dev/timus/agent/prompts.py)
- [tests/test_base_agent_tool_envelope.py](/home/fatih-ubuntu/dev/timus/tests/test_base_agent_tool_envelope.py)

Zusätzlicher Befund aus dieser Korrektur:

- Der Agent muss `restart_timus` sowohl im Raw-Format als auch im normalisierten Tool-Envelope als terminal behandeln.

## Korrigierte Root-Cause-Einschätzung

Die bestbelegte unmittelbare Ursache für die Fehlerserie vom 2026-03-08 ist:

1. `restart_timus(...)` startet asynchron im Hintergrund.
2. Der Agent behandelt das Ergebnis nicht robust als terminal.
3. Im selben Run folgen weitere Tool-Calls gegen ein System im Restart-Übergang.
4. Dadurch entstehen Anschlussfehler wie `All connection attempts failed`.
5. Parallel dazu zeigt der spätere Journald-Verlauf, dass `timus-mcp.service` beim Stop zusätzlich in `stop-sigterm` timeoutet und von systemd hart gekillt wird.

Die saubere Einordnung ist daher:

- Agent-/Envelope-Bug: gesichert und bereits lokal gefixt
- MCP-Service-Stop-Timeout: gesichert beobachtet, aber noch nicht technisch isoliert
- Exakte Kausalität zwischen beiden: noch offen

## Pragmatischer nächster Schritt

1. Den Agent-Fix für den normalisierten Restart-Envelope übernehmen.
2. Restart erneut testen.
3. Danach den tatsächlichen Endzustand getrennt prüfen:

```bash
systemctl status timus-mcp.service timus-dispatcher.service --no-pager
curl -sS http://127.0.0.1:5000/health
cat /home/fatih-ubuntu/dev/timus/logs/timus_restart_status.json
```

4. Danach den Service-Layer separat untersuchen:

```bash
journalctl -u timus-mcp.service -n 200 --no-pager
systemctl show timus-mcp.service -p TimeoutStopUSec -p KillMode -p ExecStart -p ExecStop
```

5. Ziel der nächsten Analyse: klären, warum Uvicorn bzw. Kindprozesse den SIGTERM-Stop nicht innerhalb des systemd-Timeouts beenden.

## Kurzfazit

- Der alte Report hat zu viel als Fakt formuliert.
- Der konkrete, belegte Bug lag im Agent-/Tool-Envelope-Pfad.
- Der terminale Restart-Fix war nur teilweise korrekt und ist jetzt lokal auf den echten Envelope angepasst.
- Ein echter MCP-Stop-Timeout ist inzwischen ebenfalls belegt.
- Die Statusdatei und das Detached-Log sind weiterhin keine verlässliche Abschlussquelle.
