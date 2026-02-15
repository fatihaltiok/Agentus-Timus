# Bugfix: search_web JSON-RPC Error + add_interaction Loop

**Datum:** 2026-02-15
**Symptom:** `search_web` liefert Ergebnisse, aber Agent bekommt Error zurueck. Agent faellt in `add_interaction`-Endlosschleife. Finale Antwort: "Limit erreicht."

---

## Problem 1: search_web gibt ungueltige JSON-RPC Response

### Ursache

`tools/tool_registry_v2.py` Zeile 236 — der JSON-RPC Wrapper prueft nur auf `dict`:

```python
if isinstance(result, dict):
    return Success(result)
# Alles andere wird RAW zurueckgegeben!
return result
```

`search_web` gibt aber eine **Liste** zurueck (`List[Dict]`). Diese wird roh an `jsonrpcserver` durchgereicht, was sie ablehnt:

```
AssertionError: The method did not return a valid Result (returned [{...}, {...}])
```

### Fix

`tools/tool_registry_v2.py` — Wrapper wrapped jetzt **alle** Rueckgabetypen in `Success()`:

```python
from oslash.either import Right, Left

async def jsonrpc_wrapper(*args, **kwargs):
    try:
        result = await fn(*args, **kwargs)
        # Bereits ein Success/Error (Right/Left) Objekt
        if isinstance(result, (Right, Left)):
            return result
        # Alles (dict, list, str, int, None) in Success wrappen
        return Success(result)
    except Exception as e:
        return Error(code=-32000, message=str(e))
```

### Betroffene Tools

Alle Tools die Listen zurueckgeben profitieren:
- `search_web`, `search_news`, `search_images`, `search_scholar`
- Weitere Tools mit List-Returns (som_tool, fact_corroborator, etc.)

---

## Problem 2: add_interaction Endlosschleife

### Ursache

Der ExecutorAgent sieht `add_interaction` in seiner Tool-Liste und ruft es auf um Interaktionen zu "speichern". Nach jedem erfolgreichen `add_interaction` will er die *neue* Interaktion auch speichern — Endlosschleife:

```
12:54:16 | add_interaction -> {"user_input": "Observation: ...", "assistant_response": "..."}
12:54:27 | add_interaction -> {"user_input": "Observation: ...", "assistant_response": "..."}
12:54:32 | add_interaction -> {"user_input": "Observation: ...", "assistant_response": "..."}
... (12x wiederholt bis Loop-Detection greift)
```

### Fix

`agent/base_agent.py` — System-Tools werden sofort blockiert:

```python
SYSTEM_ONLY_TOOLS = {
    "add_interaction", "end_session", "get_memory_stats",
}

def should_skip_action(self, action_name, params):
    if action_name in self.SYSTEM_ONLY_TOOLS:
        return True, "System-Tool, konzentriere dich auf die Aufgabe"
    ...
```

Der Agent bekommt eine klare Anweisung statt endlos zu loopen:
> "Konzentriere dich auf die eigentliche Aufgabe. Wenn du fertig bist: Final Answer: ..."

---

## Verifizierung

```bash
# Syntax-Check
python -m py_compile tools/tool_registry_v2.py  # OK
python -m py_compile agent/base_agent.py         # OK

# Funktionstest: Liste wird korrekt gewrapped
python -c "
from tools.tool_registry_v2 import tool, ToolParameter as P, ToolCategory as C
from jsonrpcserver.methods import global_methods
from oslash.either import Right
import asyncio

@tool(name='test', description='t', parameters=[P('q','string','q')],
      capabilities=['test'], category=C.SEARCH)
async def test(q): return [{'a': 1}]

async def check():
    r = await global_methods['test'](q='x')
    assert isinstance(r, Right), 'Nicht Right!'
    print('OK')
asyncio.run(check())
"
```

## Geaenderte Dateien

| Datei | Aenderung |
|-------|-----------|
| `tools/tool_registry_v2.py` | Import `oslash.either.Right/Left`, Wrapper wrapped alle Typen in `Success()` |
| `agent/base_agent.py` | `SYSTEM_ONLY_TOOLS` Blacklist, blockiert `add_interaction`/`end_session` |
