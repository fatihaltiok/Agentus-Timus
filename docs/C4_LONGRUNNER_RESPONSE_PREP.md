# C4 Vorbereitung - Langlaeufer und Nutzerantwortpfade

Stand: 2026-04-06

Diese Datei bereitet C4 vor, ohne bereits die Runtime- oder Transportpfade umzubauen.

## Ziel

C4 soll verhindern, dass lange Laeufe fuer Nutzer wie "Timus antwortet nicht" wirken.

Der Block soll vor allem:

- sichtbaren Zwischenstatus fuer Langlaeufer schaffen
- echte Blocker sauber und frueh kommunizieren
- Research-, Diagnose- und Visual-Laeufe in einen gemeinsamen Fortschrittspfad bringen
- Canvas zuerst verbessern, Telegram danach gezielt nachziehen

## Bekannte Ausgangslage im aktuellen Code

### 1. Delegationen haben bereits internes Progress-Signal, aber keinen echten Nutzerpfad

In [agent/agent_registry.py](/home/fatih-ubuntu/dev/timus/agent/agent_registry.py):

- `_make_progress_callback(...)` fuehrt bereits ein internes Stage-Signal
- `_run_agent_with_watchdog(...)` wartet bei `executor` auf erstes Progress-Lebenszeichen
- beim Ausbleiben wird ein `DelegationProgressTimeout` erzeugt

Das ist ein guter Startpunkt, aber:

- der Fortschritt bleibt intern
- der Nutzer bekommt daraus heute noch keinen standardisierten Zwischenstatus

### 2. Canvas-SSE transportiert nur Agent-Status und Thinking-LED

In [server/mcp_server.py](/home/fatih-ubuntu/dev/timus/server/mcp_server.py):

- `_set_agent_status(...)` broadcastet nur `agent_status` und `thinking`
- `/events/stream` liefert `init`, `agent_status`, `thinking`, `ping`
- `/chat` wartet bis `run_agent(...)` fertig ist und schreibt erst dann die Endantwort

Damit fehlt heute:

- strukturierter `progress`
- strukturierter `blocker`
- strukturierter `partial_result`

### 3. Lokale Zwischenstatus existieren bereits vereinzelt

In [agent/visual_nemotron_agent_v4.py](/home/fatih-ubuntu/dev/timus/agent/visual_nemotron_agent_v4.py) nutzt der Visual-Pfad bereits:

- `status: "in_progress"`
- `status: "step_done"`
- `status: "step_blocked"`

Das ist nuetzlich, aber noch kein systemweit einheitlicher Vertrag.

### 4. Partial-/Timeout-Semantik ist agent-seitig schon vorhanden

In [agent/agent_registry.py](/home/fatih-ubuntu/dev/timus/agent/agent_registry.py):

- `research`-Timeouts werden als `partial` behandelt
- andere Agenten-Timeouts bleiben `error`

Das ist ein guter C4-Hebel:

- Research soll bei Langlaeufern frueher sichtbare Teilergebnisse liefern
- nicht erst am harten Ende

## C4 Arbeitsreihenfolge

1. Gemeinsamen Long-Run-Vertrag definieren

- einheitliche Statuswerte:
  - `in_progress`
  - `partial`
  - `awaiting_user`
  - `blocked`
  - `completed`
  - `error`
- einheitliche Pflichtfelder:
  - `run_id`
  - `agent`
  - `stage`
  - `message`
  - `progress_hint`
  - `blocker_reason`
  - `next_expected_update_s`

2. Canvas-Transport erweitern

- neuer SSE-Typ `progress`
- neuer SSE-Typ `blocker`
- neuer SSE-Typ `partial_result`
- `agent_status/thinking` bleiben bestehen, aber werden nicht mehr ueberladen

3. AgentRegistry als zentrale Quelle nutzen

- internes Progress-Signal aus `_delegation_progress_callback` nicht nur fuer Timeout-Watchdog nutzen
- dieselben Stages optional nach SSE/Transport weiterreichen
- kein paralleles zweites Progress-System auf Agent-Ebene erfinden

4. Erste echte Langlaeufer anbinden

- `executor` bei `simple_live_lookup` / source-aware Lookups
- `research`
- `visual_nemotron`
- spaeter `meta`, wenn es selbst mehrschrittige orchestrierte Laeufe sichtbar machen soll

5. Blocker-Pfad vereinheitlichen

- ehrliche Rueckmeldung bei:
  - Login erforderlich
  - Quelle blockiert
  - CAPTCHA / Challenge
  - Timeout ohne vernuenftiges Ergebnis
- Blocker muessen sichtbar vor dem finalen Fehlerpfad kommen

6. Telegram-Nachzug als eigener Nachblock

- Canvas/SSE zuerst
- Telegram spaeter mit kompakten Heartbeats / Teilergebnissen
- keine Telegram-Sonderlogik vor dem gemeinsamen Kernvertrag

## Konkrete C4-Artefakte

### A. Progress-Event-Shape

```json
{
  "type": "progress",
  "run_id": "run_...",
  "agent": "research",
  "stage": "searching_sources",
  "message": "Suche Quellen und baue belastbare Trefferliste auf.",
  "progress_hint": "started",
  "next_expected_update_s": 15
}
```

### B. Blocker-Event-Shape

```json
{
  "type": "blocker",
  "run_id": "run_...",
  "agent": "executor",
  "stage": "auth_wall",
  "message": "Die Quelle liefert ohne Login nur unvollstaendige Inhalte.",
  "blocker_reason": "auth_required",
  "user_action_required": "Bitte bestaetige, ob Timus deinen Zugang dafuer verwenden darf."
}
```

### C. Partial-Result-Shape

```json
{
  "type": "partial_result",
  "run_id": "run_...",
  "agent": "research",
  "message": "Erste belastbare Teilergebnisse liegen vor.",
  "content_preview": "Drei relevante Quellen sind bereits ausgewertet.",
  "is_final": false
}
```

## Testmatrix fuer C4

1. `executor` sendet innerhalb des Startfensters sichtbaren Progress
2. `research` liefert bei Langlauf zuerst Progress und spaeter Ergebnis
3. `visual_nemotron` mappt `step_blocked` auf ein standardisiertes Blocker-Signal
4. `/events/stream` transportiert `progress`, `blocker`, `partial_result`
5. `/chat` bleibt kompatibel, auch wenn parallel SSE-Fortschritt laeuft
6. Blocker ohne Endergebnis fuehlen sich fuer den Nutzer nicht wie Stille an

## Nicht Teil von C4

- echte Nutzerfreigaben fuer Login / Zahlung
- Session-Reuse fuer authentische Browser-Sitzungen
- CAPTCHA-/2FA-Handover

Das gehoert in Phase D.

## Fertig fuer Start, wenn

- die Transport-Events klar definiert sind
- `agent_registry` als zentrale Progress-Quelle gesetzt ist
- Canvas/SSE als erster Zielpfad feststeht
- die ersten drei Langlaeufer (`executor`, `research`, `visual_nemotron`) priorisiert sind
