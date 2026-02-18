# Canvas MVP (Timus)

Stand: 2026-02-18

Der Canvas-MVP ergaenzt Timus um einen persistierten Arbeitsgraphen fuer Sessions, Agenten und Run-Events.

## Ziele
- Session an Canvas binden
- Nodes/Edges fuer Workflow-Struktur speichern
- Agent-Run-Events automatisch aus `main_dispatcher.run_agent(...)` loggen

## Persistenz
- Datei: `data/canvas_store.json`
- Modul: `orchestration/canvas_store.py`

## HTTP-Endpoints (MCP Server)
- `GET /canvas/ui` (Web-UI)
- `GET /canvas?limit=50`
- `POST /canvas/create`
- `GET /canvas/{canvas_id}`
- `GET /canvas/by_session/{session_id}`
- `POST /canvas/{canvas_id}/attach_session`
- `POST /canvas/{canvas_id}/nodes/upsert`
- `POST /canvas/{canvas_id}/edges/add`
- `POST /canvas/{canvas_id}/events/add`

### Filter-Parameter fuer Read-Views
`GET /canvas/{canvas_id}` und `GET /canvas/by_session/{session_id}` unterstuetzen:
- `session_id` (nur bei `/canvas/{canvas_id}`)
- `agent`
- `status`
- `only_errors=true|false`
- `event_limit=1..1000`

## Minimaler Test-Flow
1. Canvas erstellen:
```bash
curl -sS -X POST http://127.0.0.1:5000/canvas/create \
  -H 'content-type: application/json' \
  -d '{"title":"Live Task Canvas","description":"E2E Session"}'
```

2. Session verknuepfen:
```bash
curl -sS -X POST http://127.0.0.1:5000/canvas/<canvas_id>/attach_session \
  -H 'content-type: application/json' \
  -d '{"session_id":"hybrid_abc123"}'
```

3. Danach laufen Agent-Events automatisch ein, wenn `run_agent(..., session_id="hybrid_abc123")` genutzt wird.

4. Canvas lesen:
```bash
curl -sS http://127.0.0.1:5000/canvas/by_session/hybrid_abc123
```

5. Web-UI oeffnen:
```bash
xdg-open http://127.0.0.1:5000/canvas/ui
```

## Hinweise
- Das Canvas-Logging ist best effort und blockiert keine Agent-Ausfuehrung.
- Events werden pro Canvas auf die letzten 2000 begrenzt.
- Delegation-Flow loggt automatisch Edges/Events (`from_agent -> to_agent`), wenn die Session einem Canvas zugeordnet ist.
- Beim MCP-Start wird automatisch ein Default-Canvas erstellt, falls noch keines existiert.
- Beim MCP-Start wird die Canvas-UI automatisch im Browser geoeffnet (best effort).
- ENV-Schalter:
  - `TIMUS_CANVAS_AUTO_CREATE=true|false` (default: `true`)
  - `TIMUS_CANVAS_AUTO_OPEN=true|false` (default: `true`)
  - `TIMUS_CANVAS_DEFAULT_TITLE="..."` (default: `Live Canvas`)
