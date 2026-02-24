# Plan: Parallele Multi-Agenten-Delegation (Fan-Out / Fan-In)

**Erstellt:** 2026-02-24
**Basis:** Grok-Plan v2.0 (Timus-spezifisch angepasst)
**Status:** Bereit zur Ausführung
**Priorität:** Hoch — Kernarchitektur
**Erwartete Beschleunigung:** 3–6× bei Recherche- und Entwicklungsaufgaben

---

## Ziel

Timus arbeitet heute **sequenziell**: Meta wartet bis Research fertig ist, dann Developer,
dann Creative. Das soll sich ändern:

```
HEUTE:
Meta → Research (60s warten) → Developer (30s warten) → Creative (20s warten)
Gesamtzeit: 110s

NACH DIESER ÄNDERUNG:
Meta → Research  ┐
     → Developer ├── parallel → Ergebnisse bündeln → Meta wertet aus
     → Creative  ┘
Gesamtzeit: 60s (das längste dauert)
```

---

## Was vom Grok-Plan übernommen wird

- Fan-Out / Fan-In Konzept ✅
- `asyncio.gather()` als Engine ✅
- `asyncio.Semaphore(5)` zur Lastbegrenzung ✅
- Trace-IDs für Observability ✅
- `ResultAggregator` Klasse (M4) ✅
- MetaAgent-Prompt-Erweiterung ✅

## Was angepasst werden muss (Timus-Inkompatibilitäten)

| Grok-Plan | Timus-Realität | Fix |
|-----------|----------------|-----|
| `memory/persistent_memory.py` | existiert nicht — alles in `memory/memory_system.py` | richtige Datei nutzen |
| `class BaseTool` | existiert nicht | `@tool` Decorator aus `tool_registry_v2` nutzen |
| `self.delegate_to_agent(isolated=True, trace_id=...)` | Methode heißt `delegate()`, kein `isolated`/`trace_id` | Signatur anpassen |
| `MemoryAccessGuard._read_only_mode` als Klassvariable | nicht thread-safe — Worker A setzt True, Worker B setzt False | `ContextVar` statt Klassvariable |
| `session_memory.add_message(metadata=...)` | `add_message()` hat keinen `metadata` Parameter | Parameter weglassen |
| Agenten-Instanz-Caching | `_instances` cached pro Typ — parallele Calls teilen eine Instanz | frische Instanz pro paralleler Delegation |

---

## Meilensteine

---

### Meilenstein 1 — Speicher- und Thread-Sicherheit (Fundament)

**Muss zuerst umgesetzt werden. M2/M3 bauen darauf auf.**

#### M1.1 — SQLite WAL-Modus aktivieren

**Datei:** `memory/memory_system.py` — Methode `PersistentMemory._init_db()` (ca. Zeile 507)

Timus öffnet SQLite per `with sqlite3.connect(self.db_path) as conn:` — jede
Verbindung ist kurzlebig. WAL muss einmalig permanent aktiviert werden:

```python
def _init_db(self):
    """Initialisiert die Datenbank-Tabellen."""
    with sqlite3.connect(self.db_path) as conn:
        # WAL-Modus einmalig aktivieren (bleibt permanent in der DB-Datei)
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        conn.execute("PRAGMA cache_size=-64000;")  # 64 MB Cache
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS facts (
            ...  # Rest unverändert
        """)
```

Vorteil: WAL erlaubt gleichzeitige Reads + einen Writer ohne Locks — exakt was
parallele Agenten brauchen.

#### M1.2 — `MemoryAccessGuard` mit ContextVar (thread-safe)

**Neue Datei:** `memory/memory_guard.py`

Problem beim Grok-Vorschlag: `_read_only_mode` als Klassvariable ist global.
Worker A setzt `True`, Worker B ist fertig und setzt `False` → Worker A läuft
unkontrolliert weiter.

**Fix:** `ContextVar` — jeder asyncio-Task hat seinen eigenen Wert:

```python
# memory/memory_guard.py
"""
MemoryAccessGuard — Thread-sicherer Schreibschutz für parallele Worker.

Nutzt ContextVar statt Klassvariable, damit jeder asyncio-Task seinen
eigenen read_only-Status hat (kein globaler Zustand).
"""
import asyncio
from contextvars import ContextVar

_read_only_ctx: ContextVar[bool] = ContextVar("timus_read_only", default=False)
_write_lock = asyncio.Lock()


class MemoryAccessGuard:

    @staticmethod
    def set_read_only(enabled: bool) -> None:
        """Setzt read-only für den aktuellen asyncio-Task (nicht global)."""
        _read_only_ctx.set(enabled)

    @staticmethod
    def is_read_only() -> bool:
        return _read_only_ctx.get()

    @staticmethod
    def check_write_permission() -> None:
        """Wirft PermissionError wenn aktueller Task read-only ist."""
        if _read_only_ctx.get():
            raise PermissionError(
                "Worker sind read-only. Ergebnisse nur via JSON-Return zurückgeben."
            )

    @staticmethod
    async def acquire_write_lock() -> None:
        await _write_lock.acquire()

    @staticmethod
    def release_write_lock() -> None:
        _write_lock.release()
```

#### M1.3 — Guard in Memory-Schreiboperationen einbinden

**Datei:** `memory/memory_system.py`

In `PersistentMemory.store_fact()`, `store_memory_item()`, `store_summary()`,
`store_conversation()` und `remember()` (Zeilen ~576, ~655, ~736, ~771, ~2418):

```python
from memory.memory_guard import MemoryAccessGuard

def store_fact(self, fact: Fact):
    MemoryAccessGuard.check_write_permission()  # NEU — wirft bei read-only Worker
    with sqlite3.connect(self.db_path) as conn:
        ...  # Rest unverändert
```

In `SemanticMemoryStore.store_embedding()` (Zeile ~139):
```python
def store_embedding(self, item: MemoryItem) -> Optional[str]:
    MemoryAccessGuard.check_write_permission()  # NEU
    ...  # Rest unverändert
```

---

### Meilenstein 2 — Batch-Delegations-Tool

**Neue Datei:** `tools/delegation_tool/parallel_delegation_tool.py`

Timus nutzt `@tool` Decorator aus `tool_registry_v2` — kein `BaseTool`:

```python
# tools/delegation_tool/parallel_delegation_tool.py
"""
Parallel-Delegation-Tool — Fan-Out für parallele Agent-Ausführung.
Registriert sich automatisch über @tool Decorator.
"""
import logging
from typing import List, Dict, Any
from tools.tool_registry_v2 import tool, P, C

log = logging.getLogger("ParallelDelegation")


@tool(
    name="delegate_multiple_agents",
    description=(
        "Führt mehrere UNABHÄNGIGE Aufgaben PARALLEL an verschiedene Agenten aus. "
        "Jeder Worker läuft isoliert. Ergebnisse werden gebündelt zurückgeliefert. "
        "NUR verwenden wenn Teilaufgaben wirklich voneinander unabhängig sind. "
        "Format: [{\"task_id\": \"t1\", \"agent\": \"research\", \"task\": \"...\", \"timeout\": 120}, ...]"
    ),
    parameters=[
        P("tasks", "array",
          "JSON-Array von Tasks: [{task_id, agent, task, timeout?}, ...]",
          required=True),
    ],
    capabilities=["orchestration"],
    category=C.SYSTEM,
)
async def delegate_multiple_agents(tasks: List[Dict[str, Any]]) -> Dict[str, Any]:
    from agent.agent_registry import agent_registry
    return await agent_registry.delegate_parallel(tasks)
```

**Keine `__init__.py` Anpassung nötig** — `tool_registry_v2` lädt alle `@tool`
Dekoratoren automatisch beim Server-Start.

---

### Meilenstein 3 — Async-Engine in `AgentRegistry`

**Datei:** `agent/agent_registry.py` — neue Methode `delegate_parallel()` am Ende
der `AgentRegistry` Klasse (nach `delegate()`, ca. Zeile 374)

Wichtigste Timus-Anpassung: `self.delegate()` statt `self.delegate_to_agent()`
(richtige Methode), kein `isolated`/`trace_id` Parameter, **frische Instanz**
pro parallelem Task (kein Singleton-Problem):

```python
async def delegate_parallel(
    self,
    tasks: List[Dict[str, Any]],
    from_agent: str = "meta",
    max_parallel: int = 5,
) -> Dict[str, Any]:
    """
    Fan-Out: Führt mehrere Tasks parallel aus.
    Fan-In:  Aggregiert strukturierte Ergebnisse.

    Jeder Task bekommt eine FRISCHE Agenten-Instanz (kein Singleton-Problem).
    MemoryAccessGuard setzt read-only pro asyncio-Task (ContextVar — thread-safe).
    """
    import uuid
    from memory.memory_guard import MemoryAccessGuard

    trace_id = uuid.uuid4().hex[:12]
    semaphore = asyncio.Semaphore(max_parallel)

    log.info(
        f"[ParallelDelegation] {len(tasks)} Tasks | TraceID: {trace_id} | "
        f"MaxParallel: {max_parallel}"
    )

    async def run_single(task: Dict[str, Any]) -> Dict[str, Any]:
        task_id  = task.get("task_id") or f"t{uuid.uuid4().hex[:6]}"
        agent_name = self.normalize_agent_name(task.get("agent", ""))
        task_desc  = task.get("task", "")
        timeout    = float(task.get("timeout", 120))

        if not agent_name or not task_desc:
            return {
                "task_id": task_id, "agent": agent_name,
                "status": "error", "error": "Fehlende 'agent' oder 'task' Felder"
            }

        async with semaphore:
            try:
                # read-only für diesen Task setzen (ContextVar — nur dieser Task)
                MemoryAccessGuard.set_read_only(True)

                # Frische Instanz erstellen (kein Singleton — verhindert Race Condition)
                spec = self._specs.get(agent_name)
                if not spec:
                    return {
                        "task_id": task_id, "agent": agent_name,
                        "status": "error",
                        "error": f"Agent '{agent_name}' nicht registriert"
                    }

                tools_desc = self._tools_description or ""
                fresh_agent = spec.factory(tools_desc, **spec.extra_kwargs)

                raw = await asyncio.wait_for(
                    fresh_agent.run(task_desc), timeout=timeout
                )

                MemoryAccessGuard.set_read_only(False)

                result_str = str(raw)
                status = "partial" if result_str in self._PARTIAL_MARKERS else "success"
                return {
                    "task_id": task_id,
                    "agent":   agent_name,
                    "status":  status,
                    "result":  result_str,
                    "trace":   f"{trace_id}-{task_id}",
                }

            except asyncio.TimeoutError:
                MemoryAccessGuard.set_read_only(False)
                log.warning(f"[ParallelDelegation] Timeout: {agent_name} (task_id={task_id})")
                return {
                    "task_id": task_id, "agent": agent_name,
                    "status": "partial", "error": f"Timeout nach {timeout}s",
                    "trace":  f"{trace_id}-{task_id}",
                }
            except Exception as e:
                MemoryAccessGuard.set_read_only(False)
                log.error(f"[ParallelDelegation] Fehler: {agent_name}: {e}")
                return {
                    "task_id": task_id, "agent": agent_name,
                    "status": "error", "error": str(e),
                    "trace":  f"{trace_id}-{task_id}",
                }

    # Fan-Out
    raw_results = await asyncio.gather(
        *[run_single(t) for t in tasks],
        return_exceptions=True
    )

    # Fan-In
    results = []
    success_count = partial_count = error_count = 0
    for r in raw_results:
        if isinstance(r, Exception):
            results.append({"status": "error", "error": str(r)})
            error_count += 1
        else:
            results.append(r)
            s = r.get("status")
            if s == "success":  success_count += 1
            elif s == "partial": partial_count += 1
            else:                error_count   += 1

    return {
        "trace_id":    trace_id,
        "total_tasks": len(tasks),
        "success":     success_count,
        "partial":     partial_count,
        "errors":      error_count,
        "results":     results,
        "summary":     (
            f"{success_count}/{len(tasks)} erfolgreich | "
            f"{partial_count} partiell | {error_count} Fehler"
        ),
    }
```

**Import ergänzen** — am Anfang von `agent_registry.py`:
```python
import uuid  # NEU
```

---

### Meilenstein 4 — ResultAggregator (Fan-In Formatierung)

**Neue Datei:** `agent/result_aggregator.py`

Timus-Anpassung: `add_message()` hat kein `metadata` Parameter:

```python
# agent/result_aggregator.py
"""
ResultAggregator — Formatiert und injiziert Fan-In-Ergebnisse.
Macht parallele Ergebnisse für den MetaAgenten lesbar.
"""
import json
from typing import Dict, Any, List


class ResultAggregator:

    @staticmethod
    def format_results(aggregated: Dict[str, Any]) -> str:
        """Erstellt LLM-lesbare Markdown-Zusammenfassung der parallelen Ergebnisse."""
        results: List[Dict] = aggregated.get("results", [])
        lines = [
            f"## Parallele Delegation — Ergebnisse",
            f"**TraceID:** {aggregated.get('trace_id', 'N/A')}",
            f"**Status:** {aggregated.get('summary', '')}",
            "",
        ]

        for r in results:
            task_id = r.get("task_id", "?")
            agent   = r.get("agent", "?")
            status  = r.get("status", "?").upper()
            result  = r.get("result", r.get("error", ""))

            lines.append(f"### [{task_id}] {agent} → {status}")
            if result:
                # Max 800 Zeichen pro Ergebnis — Context-Window schonen
                lines.append(str(result)[:800])
            lines.append("")

        return "\n".join(lines)

    @staticmethod
    def inject_into_session(session_memory, aggregated: Dict[str, Any]) -> None:
        """
        Injiziert Ergebnisse als EINEN Block ins SessionMemory.
        Timus SessionMemory.add_message() hat kein metadata-Parameter.
        """
        formatted = ResultAggregator.format_results(aggregated)
        session_memory.add_message(
            role="system",
            content=formatted,
        )
```

---

### Meilenstein 5 — MetaAgent-Prompt + Tests

#### M5.1 — `agent/prompts.py` — META_SYSTEM_PROMPT erweitern

In der DELEGATION-Sektion ergänzen:

```
## PARALLELE DELEGATION (bei unabhängigen Teilaufgaben)
Wenn eine Aufgabe mehrere UNABHÄNGIGE Teilschritte hat, nutze delegate_multiple_agents
statt mehrerer sequenzieller delegate_to_agent-Aufrufe.

WANN PARALLEL:
- Mehrere Recherche-Themen gleichzeitig → research + research
- Code schreiben WÄHREND Daten analysiert werden → developer + data
- Bild analysieren WÄHREND Fakten recherchiert werden → image + research

FORMAT:
Action: {"method": "delegate_multiple_agents", "params": {"tasks": [
  {"task_id": "t1", "agent": "research", "task": "Recherchiere X", "timeout": 120},
  {"task_id": "t2", "agent": "developer", "task": "Schreibe Skript für Y"}
]}}

Nach dem Aufruf erhältst du eine strukturierte Markdown-Zusammenfassung.
Integriere alle Ergebnisse in deine finale Antwort.

WICHTIG: Nur bei wirklich UNABHÄNGIGEN Teilaufgaben. Bei abhängigen Schritten
(Schritt 2 braucht Ergebnis von Schritt 1) weiterhin sequenziell delegieren.
```

#### M5.2 — Tests

**Neue Datei:** `tests/test_parallel_delegation.py`

```python
# tests/test_parallel_delegation.py
import asyncio
import pytest
from unittest.mock import AsyncMock, patch

# T1 — MemoryAccessGuard ist ContextVar-basiert (nicht global)
def test_memory_guard_per_task_isolation():
    from memory.memory_guard import MemoryAccessGuard
    MemoryAccessGuard.set_read_only(True)
    assert MemoryAccessGuard.is_read_only() is True
    MemoryAccessGuard.set_read_only(False)
    assert MemoryAccessGuard.is_read_only() is False

# T2 — check_write_permission wirft bei read-only
def test_memory_guard_blocks_write():
    from memory.memory_guard import MemoryAccessGuard
    MemoryAccessGuard.set_read_only(True)
    with pytest.raises(PermissionError):
        MemoryAccessGuard.check_write_permission()
    MemoryAccessGuard.set_read_only(False)

# T3 — delegate_parallel gibt strukturiertes Dict zurück
async def test_delegate_parallel_success():
    from agent.agent_registry import register_all_agents, agent_registry
    register_all_agents()
    # Mock: frische Agenten geben sofort Ergebnis
    # (Integrationstest — echte Agenten brauchen API-Key)
    result = await agent_registry.delegate_parallel([
        {"task_id": "t1", "agent": "executor", "task": "Sage Hallo", "timeout": 10},
    ])
    assert result["total_tasks"] == 1
    assert "trace_id" in result
    assert len(result["results"]) == 1

# T4 — Semaphore begrenzt parallele Ausführung
async def test_semaphore_limits_parallel():
    # 10 Tasks mit max_parallel=2 → max 2 gleichzeitig
    # Prüfe via Zähler
    ...

# T5 — Timeout liefert partial-Status (kein Absturz)
async def test_timeout_gives_partial():
    ...

# T6 — ResultAggregator formatiert korrekt
def test_result_aggregator_format():
    from agent.result_aggregator import ResultAggregator
    aggregated = {
        "trace_id": "abc123",
        "summary": "2/2 erfolgreich | 0 partiell | 0 Fehler",
        "results": [
            {"task_id": "t1", "agent": "research", "status": "success", "result": "Ergebnis A"},
            {"task_id": "t2", "agent": "developer", "status": "success", "result": "Ergebnis B"},
        ]
    }
    formatted = ResultAggregator.format_results(aggregated)
    assert "research" in formatted
    assert "developer" in formatted
    assert "abc123" in formatted
```

---

## Betroffene Dateien

| Datei | Aktion | Meilenstein |
|-------|--------|-------------|
| `memory/memory_system.py` | WAL-Pragma + Guard-Checks | M1.1 + M1.3 |
| `memory/memory_guard.py` | Neu anlegen | M1.2 |
| `tools/delegation_tool/parallel_delegation_tool.py` | Neu anlegen | M2 |
| `agent/agent_registry.py` | `delegate_parallel()` + `import uuid` | M3 |
| `agent/result_aggregator.py` | Neu anlegen | M4 |
| `agent/prompts.py` | META_SYSTEM_PROMPT Erweiterung | M5.1 |
| `tests/test_parallel_delegation.py` | Neu anlegen | M5.2 |

---

## Verifikation

```bash
# Syntax aller neuen/geänderten Dateien
python -m py_compile memory/memory_guard.py
python -m py_compile memory/memory_system.py
python -m py_compile tools/delegation_tool/parallel_delegation_tool.py
python -m py_compile agent/agent_registry.py
python -m py_compile agent/result_aggregator.py
python -m py_compile agent/prompts.py

# Tests
pytest tests/test_parallel_delegation.py -v

# Bestehende Tests weiterhin grün
pytest tests/ -q --ignore=tests/vision --ignore=tests/e2e
```

---

## Ausführungsreihenfolge (strikt einhalten)

```
M1.1 → M1.2 → M1.3    (Fundament — Pflicht vor allem anderen)
→ M2                   (Tool registrieren)
→ M3                   (Engine in Registry)
→ M4                   (ResultAggregator)
→ M5.1 → M5.2         (Prompt + Tests)
→ Verifikation
```

---

## Wichtige Constraints

- `asyncio.wait_for` statt `asyncio.timeout` (konsistent mit bestehendem Code)
- Keine neuen Dependencies — nur stdlib (`asyncio`, `uuid`, `contextvars`)
- Frische Agenten-Instanz pro parallelem Task — kein Singleton-Problem
- `ContextVar` für read-only Flag — kein globaler Zustand
- Rückwärtskompatibel: `delegate()` bleibt unverändert, `delegate_parallel()` ist neu
