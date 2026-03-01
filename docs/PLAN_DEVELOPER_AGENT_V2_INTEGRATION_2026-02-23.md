# Plan: Developer Agent V2 Integration

**Erstellt:** 2026-02-23
**Status:** Bereit zur Ausführung
**Priorität:** Mittel
**Aufwand:** Klein (~3 Dateien, ~10 Zeilen)

---

## Ziel

`DeveloperAgentV2` aus `agent/developer_agent_v2.py` ersetzt den aktuellen
minimalen `DeveloperAgent` in der Registry. Die v2-Features (Kontext-Sammlung,
AST-Validierung, Code-Cache, Recovery-Strategien) stehen damit im gesamten
Multi-Agent-System zur Verfügung.

---

## Ist-Zustand

```
agent/agents/developer.py         ← aktuelle Registrierung
  └── DeveloperAgent(BaseAgent)   ← nur DEVELOPER_SYSTEM_PROMPT + max_iterations=15

agent/developer_agent_v2.py       ← liegt lose im agent/-Ordner, wird nicht genutzt
  └── DeveloperAgentV2            ← hat async run(), ist registry-kompatibel
```

---

## Geplante Änderungen

### 1. `agent/developer_agent_v2.py` verschieben

Datei an den richtigen Ort verschieben:

```
agent/developer_agent_v2.py  →  agent/agents/developer_v2.py
```

Damit liegt sie konsistent bei den anderen Agenten.

### 2. `agent/agent_registry.py` — Import + Registrierung tauschen

**Zeile ~408** — Import ergänzen:
```python
# Vorher:
from agent.agents import (
    ExecutorAgent, DeepResearchAgent, ReasoningAgent,
    CreativeAgent, DeveloperAgent, MetaAgent, VisualAgent,
    DataAgent, DocumentAgent, CommunicationAgent, SystemAgent, ShellAgent,
)

# Nachher: DeveloperAgent bleibt im Import (Fallback), v2 separat laden
from agent.agents import (
    ExecutorAgent, DeepResearchAgent, ReasoningAgent,
    CreativeAgent, DeveloperAgent, MetaAgent, VisualAgent,
    DataAgent, DocumentAgent, CommunicationAgent, SystemAgent, ShellAgent,
)
from agent.agents.developer_v2 import DeveloperAgentV2
```

**Zeile ~436** — Registrierung tauschen:
```python
# Vorher:
registry.register_spec(
    "developer", "developer",
    ["code", "development", "files", "refactoring"],
    DeveloperAgent,
)

# Nachher:
registry.register_spec(
    "developer", "developer",
    ["code", "development", "files", "refactoring", "implement", "script"],
    DeveloperAgentV2,
)
```

### 3. `agent/agents/developer_v2.py` — Hardcoded Konfiguration anpassen (optional)

In `developer_agent_v2.py` sind diese Werte hardcoded:
```python
TEXT_MODEL = os.getenv("MAIN_LLM_MODEL", "gpt-5")        # GPT-5 für Planung
REQUIRE_INCEPTION = os.getenv("REQUIRE_INCEPTION", "1")   # Inception für Code-Gen
```

Das ist bereits ENV-konfigurierbar — keine Änderung zwingend nötig.
Falls gewünscht: `MAIN_LLM_MODEL` in `.env` auf bevorzugtes Modell setzen.

---

## Was sich verbessert

| Feature | Vorher (v1) | Nachher (v2) |
|---------|-------------|--------------|
| Projekt-Kontext | ❌ kein | ✅ liest README, requirements.txt, Struktur |
| Code-Validierung | ❌ kein | ✅ AST-Syntax + Style + Sicherheitscheck |
| Auto-Context-Files | ❌ kein | ✅ findet verwandte Dateien automatisch |
| Fehler-Recovery | ❌ kein | ✅ erkennt syntax/context/logic Fehler, wechselt Strategie |
| Code-Cache | ❌ kein | ✅ generierter Code wird gecacht, dann separat geschrieben |
| Learning-Logging | ❌ kein | ✅ Erfolg/Fehler wird via log_learning_entry geloggt |
| max_iterations | 15 | 12 (effizienter durch bessere Planung) |

---

## Was wegfällt → Phase 2 nachrüsten

| Feature | Status | Phase |
|---------|--------|-------|
| BaseAgent Policy-Gate | ⚠️ fehlt — nachzurüsten | Phase 2 |
| BugLogger | ⚠️ fehlt — nachzurüsten | Phase 2 |
| Multi-Provider via providers.py | v2 nutzt `MAIN_LLM_MODEL` ENV (konfigurierbar) | akzeptabel |

---

## Phase 2 — Policy-Gate + BugLogger nachrüsten

Nachdem Phase 1 (Drop-in) läuft und stabil ist, werden Policy-Gate und
BugLogger in `DeveloperAgentV2` nachgerüstet — ohne den v2-Loop anzutasten.

### P2.1 — BugLogger einbinden

In `agent/agents/developer_v2.py` — in `run_developer_task()`:

```python
# Lazy-Init am Anfang der Funktion
from utils.bug_logger import BugLogger
_bug_logger = BugLogger()

# Bei Tool-Fehler (Zeile ~676):
if isinstance(obs, dict) and obs.get("error"):
    _bug_logger.log_bug(
        bug_id=f"developer_tool_error_{method}",
        severity="medium",
        agent="developer",
        error_msg=str(obs.get("error")),
        context={"method": method, "params": list(params.keys()), "step": step}
    )

# Bei Max-Steps (Zeile ~766):
_bug_logger.log_bug(
    bug_id="developer_max_steps",
    severity="low",
    agent="developer",
    error_msg="Max steps erreicht ohne finale Antwort",
    context={"query": user_query[:100], "dest_folder": dest_folder}
)
```

### P2.2 — Policy-Gate einbinden

In `run_developer_task()` — vor dem `call_tool(method, params)` Aufruf (~Zeile 672):

```python
# POLICY-GATE: gefährliche Methoden blockieren
_BLOCKED_METHODS = {
    "run_command", "run_script", "add_cron",   # Shell-Aufgaben → shell-Agent
    "delete_file", "rm", "shutdown",            # destruktiv
}
if method in _BLOCKED_METHODS:
    obs = {
        "error": f"Tool '{method}' ist für developer-Agent gesperrt. "
                 f"Nutze delegate_to_agent('shell', ...) für Shell-Aufgaben."
    }
    messages.append({"role": "user", "content": f"Observation: {json.dumps(obs)}"})
    failures += 1
    continue
```

Ergänzend: `ALLOWED_TOOLS` Liste in der Datei um die blockierten Methoden
bereinigen (sie sollten dort gar nicht auftauchen).

### P2.3 — Test

```python
# tests/test_developer_v2_policy.py

def test_buglogger_bei_tool_fehler():
    # Simuliere Tool-Fehler → BugLogger schreibt in logs/bugs/

def test_policy_gate_blockiert_run_command():
    # run_command als Action → sofort geblockt, Fehler-Observation

def test_policy_gate_erlaubt_implement_feature():
    # implement_feature → nicht geblockt, läuft durch
```

---

## Betroffene Dateien

| Datei | Aktion |
|-------|--------|
| `agent/developer_agent_v2.py` | Verschieben nach `agent/agents/developer_v2.py` |
| `agent/agent_registry.py` | Import + Registrierung tauschen (~5 Zeilen) |
| `.env` (optional) | `MAIN_LLM_MODEL` setzen falls nötig |

---

## Verifikation nach Ausführung

```bash
# 1. Syntax
python -m py_compile agent/agents/developer_v2.py
python -m py_compile agent/agent_registry.py

# 2. Registry-Test
python -c "
from agent.agent_registry import register_all_agents, agent_registry
register_all_agents()
agents = agent_registry.list_agents()
print('developer' in agents, agents)
"

# 3. Bestehende Tests
pytest tests/ -q -k "developer or registry" --tb=short
```

---

## Ausführungsreihenfolge

```
Phase 1 — Drop-in Integration:
1. agent/developer_agent_v2.py → agent/agents/developer_v2.py (mv)
2. agent/agent_registry.py → Import + register_spec anpassen
3. python -m py_compile (beide Dateien)
4. Registry-Test
5. pytest

Phase 2 — Policy-Gate + BugLogger (nach Phase 1 stabil):
6. agent/agents/developer_v2.py → BugLogger Lazy-Init + log_bug Aufrufe
7. agent/agents/developer_v2.py → _BLOCKED_METHODS Policy-Gate vor call_tool
8. tests/test_developer_v2_policy.py anlegen
9. pytest tests/test_developer_v2_policy.py
```
