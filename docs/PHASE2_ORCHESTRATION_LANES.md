# Phase 2: Orchestrierungs-Lanes und Queueing

**Status:** ✅ Abgeschlossen  
**Datum:** Februar 2026

## Ziel
"Default serial, explicit parallel" wie OpenClaw - Weniger Race Conditions, sauberere Logs, stabilere Multi-Step-Abläufe.

## Architektur

```
┌─────────────────────────────────────────────────────────────┐
│                      LaneManager                             │
│  - Verwaltet alle Lanes                                      │
│  - max_lanes (default: 100)                                  │
│  - Auto-Cleanup inaktiver Lanes                              │
└─────────────────────────────────────────────────────────────┘
                           │
         ┌─────────────────┼─────────────────┐
         ▼                 ▼                 ▼
    ┌─────────┐      ┌─────────┐      ┌─────────┐
    │  Lane 1 │      │  Lane 2 │      │  Lane N │
    │ session │      │ session │      │ session │
    │   _a    │      │   _b    │      │   _x    │
    └─────────┘      └─────────┘      └─────────┘
         │                 │                 │
         ▼                 ▼                 ▼
    Tool Queue        Tool Queue        Tool Queue
    (serial default)  (serial default)  (serial default)
```

## Neue Dateien

### `orchestration/lane_manager.py`

**Klassen:**
- `LaneStatus` - Enum: IDLE, BUSY, QUEUED, ERROR, CLOSED
- `ToolCallPriority` - Enum: LOW(0), NORMAL(5), HIGH(10), CRITICAL(20)
- `QueuedToolCall` - Dataclass für eingereihte Tool-Calls
- `ToolCallResult` - Dataclass für Ergebnisse
- `LaneStats` - Statistiken pro Lane
- `Lane` - Einzelne Lane mit Queue und Lock
- `LaneManager` - Zentraler Manager

**Features:**
- Session-basierte Isolation (jeder Task/Session bekommt eigene Lane)
- Pro-Lane Lock (Race-Condition-Schutz)
- Queue mit konfigurierbarer Größe
- Timeout pro Tool oder global
- Statistiken (total_calls, successful, failed, duration)
- Parallele Ausführung nur wenn `parallel_allowed=True`

## Änderungen

### 1. `tools/tool_registry_v2.py`

Erweiterte `ToolMetadata`:
```python
@dataclass
class ToolMetadata:
    # ... existing fields ...
    parallel_allowed: bool = False  # NEU
    timeout: Optional[float] = None  # NEU
    priority: int = 0  # NEU
```

Erweiterte `@tool` Decorator:
```python
@tool(
    name="search_web",
    description="Sucht im Web",
    parameters=[P("query", "string", "Suchbegriff")],
    capabilities=["search"],
    category=C.SEARCH,
    parallel_allowed=True,  # Parallele Ausführung erlaubt
    timeout=30.0,           # Timeout in Sekunden
    priority=5,             # Queue-Priorität
)
async def search_web(query: str):
    return {"results": [...]}
```

### 2. `agent/base_agent.py`

Neue Imports:
```python
from orchestration.lane_manager import lane_manager, Lane, LaneStatus
```

Neue Methoden:
- `_get_lane()` - Holt oder erstellt Lane für Agent
- `_call_tool()` erweitert mit Lane-Status-Logging

Neuer Parameter:
- `lane_id: Optional[str]` - Für explizite Lane-Zuweisung

### 3. `main_dispatcher.py`

Neue Imports:
```python
from orchestration.lane_manager import lane_manager, LaneStatus
from tools.tool_registry_v2 import registry_v2
import uuid
```

Erweiterte `run_agent()`:
```python
async def run_agent(agent_name, query, tools_description, session_id=None):
    effective_session_id = session_id or str(uuid.uuid4())[:8]
    lane_manager.set_registry(registry_v2)
    lane = await lane_manager.get_or_create_lane(effective_session_id)
    # ...
```

## Usage

### Einfache serielle Ausführung (Default)

```python
from orchestration.lane_manager import lane_manager

lane_manager.set_registry(registry_v2)
lane = await lane_manager.create_lane("my_session")

# Serielle Ausführung
result = await lane.execute_tool("search_web", {"query": "test"})
result2 = await lane.execute_tool("read_file", {"path": "/tmp/test.txt"})
```

### Parallele Ausführung (wenn erlaubt)

```python
# Mehrere parallele Suchen
results = await lane.execute_parallel([
    ("search_web", {"query": "python"}),
    ("search_web", {"query": "javascript"}),
    ("search_web", {"query": "rust"}),
], max_concurrent=3)

# Tools ohne parallel_allowed=True werden abgelehnt
```

### Status-Abfrage

```python
# Lane-Status
print(lane.status)  # LaneStatus.IDLE

# Statistiken
print(lane.stats.total_calls)
print(lane.stats.successful_calls)

# Full Report
report = lane.get_status_report()
```

## Tests

Neue Test-Datei: `tests/test_orchestration_lanes.py`

```
15 Tests, alle bestanden:
- TestLaneManager (6 Tests)
- TestLane (4 Tests)
- TestParallelExecution (2 Tests)
- TestToolMetadata (3 Tests)
```

Ausführen:
```bash
pytest tests/test_orchestration_lanes.py -v
```

## Ergebnis

- ✅ Default serial, explicit parallel
- ✅ Session-basierte Isolation
- ✅ Race-Condition-Schutz durch pro-Lane Locks
- ✅ Queue-Status Überwachung
- ✅ Timeout-Support pro Tool
- ✅ Sauberere Logs mit Lane-IDs
- ✅ Weniger Race Conditions

## Nächste Phase

Phase 3: Context-Window-Guard
