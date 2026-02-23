# Architektur-Analyse: Agenten-Kommunikation im Timus Multi-Agent-System

**Datum:** 2026-02-23
**Version:** Timus v4.4 — 13 Agenten
**Autor:** Analyse-Session (Claude Code)

---

## Executive Summary

Das Timus Multi-Agent-System ist funktional und solide strukturiert. Die 13 spezialisierten Agenten kommunizieren primär über einen **MCP HTTP-Server (JSON-RPC 2.0)** und ein **zentrales Delegations-System** (`agent_registry.py`). Es gibt jedoch **kritische Lücken**: Delegationen sind sequenziell und unidirektional, es fehlen Feedback-Loops, Timeouts und Retry-Mechanismen. Die aktive Agent-zu-Agent-Delegation beschränkt sich derzeit auf einen einzigen Pfad: **ImageAgent → ResearchAgent**.

---

## 1. Agenten-Beziehungen und Hierarchie

### 1.1 Agenten-Katalog

| Agent | Modell | Capabilities | Max-Iter | Registriert |
|-------|--------|--------------|----------|-------------|
| executor | gpt-5-mini | execution, tools, simple_tasks | 30 | ✅ |
| research | deepseek-reasoner | research, search, deep_analysis | 8 | ✅ |
| reasoning | Nemotron (OpenRouter) | reasoning, analysis, debugging | 12 | ✅ |
| creative | gpt-5.2 | creative, images, content_generation | 10 | ✅ |
| developer | mercury-coder | code, development, files | 15 | ✅ |
| visual | claude-sonnet-4-5 | vision, ui, browser, navigation | 30 | ✅ |
| meta | claude-sonnet-4-5 | orchestration, planning | 20 | ✅ |
| data | deepseek-v3.2 | data, file, analysis | 20 | ❌ fehlt |
| document | claude-sonnet-4-5 | document, pdf, docx | 12 | ❌ fehlt |
| communication | claude-sonnet-4-5 | communication, email | 12 | ❌ fehlt |
| system | qwen3.5-plus | system, monitoring | 12 | ❌ fehlt |
| shell | claude-sonnet-4-6 | shell | 10 | ❌ fehlt |
| image | qwen3.5-plus | image_analysis, vision | 1 | ✅ |

> **Befund:** Die M1–M4-Agenten (data, document, communication, system, shell) sind in `agent_registry.py` **nicht registriert**. Sie können nicht als Delegationsziel genutzt werden. Nur die 7 Kern-Agenten + ImageAgent sind im Registry eingetragen.

### 1.2 Hierarchie

```
MAIN_DISPATCHER (Routing-Zentrale)
│
├─→ quick_intent_check() — Keyword-Routing (ohne LLM)
│
└─→ LLM-Entscheidung (DISPATCHER_PROMPT) — 13 Agenten erkennbar
        │
        ├─ executor      — einfache Tasks, Dateioperationen
        ├─ research      — Tiefenrecherche
        ├─ reasoning     — Analyse, Debugging, Architektur
        ├─ creative      — Bildgenerierung, kreative Texte
        ├─ developer     — Code schreiben
        ├─ meta          — Orchestrierung (SOLL delegieren, tut es nicht)
        ├─ visual        — Desktop-/Browser-Automation
        ├─ data          — CSV/XLSX/JSON Analyse
        ├─ document      — Dokumente erstellen
        ├─ communication — E-Mails, Briefe
        ├─ system        — System-Monitoring (read-only)
        ├─ shell         — Shell-Befehle (5-Schicht-Policy)
        └─ image         — Bild-Analyse → delegiert an research ✓
```

**Einzige aktive Agent-zu-Agent-Delegation:**
```
ImageAgent ──→ ResearchAgent
(image.py:99)   (bei Suchintent)
```

---

## 2. Kommunikationskanäle zwischen Agenten

### 2.1 MCP HTTP-Server (Hauptkanal)

Alle Agenten kommunizieren mit dem MCP-Server über **JSON-RPC 2.0 HTTP POST** an `http://127.0.0.1:5000`.

```python
# base_agent.py:610-650 (_call_tool)
resp = await self.http_client.post(
    "http://127.0.0.1:5000",
    json={"jsonrpc": "2.0", "method": method, "params": params, "id": "1"}
)
```

- **Timeout:** 300 Sekunden
- **Protokoll:** Synchron Request-Response (kein Streaming zwischen Agenten)
- **Scope:** Jeder Agent ruft Tools über diesen Kanal auf

### 2.2 Delegations-Tool (`delegate_to_agent`)

Der einzige explizite Agent-zu-Agent-Kanal — auch über MCP:

```
Agent A
  └─→ _call_tool("delegate_to_agent", {agent_type, task, from_agent})
        └─→ MCP-Server
              └─→ delegation_tool.py:delegate_to_agent()
                    └─→ agent_registry.delegate()
                          └─→ target_agent.run(task)
                                └─→ Ergebnis zurück als dict
```

**Rückgabe-Struktur:**
```python
{"status": "success", "agent": "research", "result": "..."}
# oder
{"status": "error", "agent": "research", "error": "FEHLER: ..."}
```

### 2.3 Memory als Kommunikationskanal (indirekt)

Agenten können über ChromaDB und SQLite indirekt miteinander kommunizieren:

```python
# Agent A schreibt:
await remember(text="Nutzer bevorzugt Python", source="user_chat", agent_id="executor")

# Agent B liest:
result = await recall(query="Was bevorzugt der Nutzer?", agent_filter="executor")
```

**Drei Speicher-Layer:**

| Layer | Technologie | Scope | Isolation |
|-------|------------|-------|-----------|
| Session Memory | RAM (letzte 20 Nachrichten) | Pro Agent-Instanz | Vollständig |
| Langzeit-Semantisch | ChromaDB (Vektoren) | Global | Optional via `agent_filter` |
| Strukturierte Fakten | SQLite (facts-Tabelle) | Global | Keine |

> **Problem:** Memory ist kein *echter* Kommunikationskanal — es gibt keine Delivery-Guarantees, kein Ordering, keine Benachrichtigung wenn Agent B etwas geschrieben hat.

### 2.4 Canvas-Visualisierung (Logging-Kanal)

Delegationen werden in `canvas_store` als Nodes, Edges und Events geloggt:

```python
# agent_registry.py:69-135
canvas_store.upsert_node(canvas_id, "agent:image",    status="running")
canvas_store.upsert_node(canvas_id, "agent:research", status="completed")
canvas_store.add_edge(from="agent:image", to="agent:research", kind="delegation")
```

> **Problem:** Best-Effort — Fehler werden stumm ignoriert. Canvas kann desynchronisiert sein.

---

## 3. Delegations-Mechanismus im Detail

### 3.1 Vollständiger Flow

```
User: "Suche Informationen zu diesem Bild: /path/foto.jpg"
  │
  ▼
main_dispatcher.py — quick_intent_check()
  └─ _IMAGE_EXTENSIONS.search(query) → "image"
  │
  ▼
ImageAgent.run(task)
  ├─ Bild lesen + Base64-Encoding
  ├─ Qwen 3.5 Plus Vision → image_analysis
  └─ _wants_search(task)? → True
  │
  ▼
delegate_to_agent("research", task=research_task, from_agent="image")
  │
  ▼
agent_registry.delegate()
  ├─ VALIDIERUNG:
  │   ├─ "research" registriert? ✓
  │   ├─ Zirkulär? (Stack: ()) → Nein ✓
  │   └─ Max-Tiefe? (0 < 3) ✓
  ├─ Stack: () → ("research",)
  ├─ Lazy-Instantiierung ResearchAgent
  └─ await research_agent.run(research_task)
  │
  ▼
ResearchAgent Standard-Loop (max 8 Iterationen)
  ├─ search_web() → Ergebnisse
  ├─ summarize() → Bericht
  └─ "Final Answer: ..."
  │
  ▼
Rückgabe: {"status": "success", "result": "..."}
  │
  ▼
ImageAgent kombiniert:
  "## Bild-Analyse\n...\n---\n## Recherche-Ergebnisse\n..."
```

### 3.2 Loop-Prevention (Funktioniert korrekt)

```python
# agent_registry.py:53-55
self._delegation_stack_var: ContextVar[tuple[str, ...]] = ContextVar(
    "timus_delegation_stack", default=()
)
```

Task-lokaler Stack verhindert zirkuläre Delegationen (A→B→A) und begrenzt Tiefe auf 3.

### 3.3 Was passiert bei Teilerfüllung?

**Aktuelles Verhalten — kein "partial success":**

```python
# base_agent.py (sinngemäß)
if iteration >= max_iterations:
    return "Limit erreicht."  # ← das ist das Ergebnis

# agent_registry.py:262-272
result = await agent.run(task)
return result  # ← egal ob vollständig oder nicht
```

- Der aufrufende Agent bekommt immer einen String zurück
- Ob das Ergebnis vollständig ist, wird **nicht geprüft**
- Kein strukturiertes `{"status": "partial", "result": "...", "missing": [...]}`
- Der ImageAgent würde ein "Limit erreicht." genauso zurückgeben wie ein vollständiges Ergebnis

---

## 4. Identifizierte Schwachstellen

### 4.1 KRITISCH — Keine Feedback-Loops während Delegation

**Problem:** Delegation ist strikt sequenziell und unidirektional.

```
Agent A delegiert → Agent B läuft → Ergebnis zurück

Was fehlt:
Agent A: "Ich brauche eher Infos über X, nicht Y"
   ↑                                    ↓
   │←─────── KEIN RÜCKKANAL ────────────┘
```

Agent A kann nicht auf den laufenden Agent B reagieren. Wenn B in die falsche Richtung läuft, erfährt A es erst wenn B fertig ist — mit einem unbrauchbaren Ergebnis.

**Auswirkung:** Bei komplexen Delegationen entsteht Informationsverlust.

---

### 4.2 KRITISCH — M1–M4-Agenten nicht im Registry

**Problem:** `agent_registry.py:319-372` registriert nur 7 Kern-Agenten + ImageAgent.

`data`, `document`, `communication`, `system`, `shell` fehlen vollständig.

**Konsequenz:** Kein anderer Agent kann an DataAgent oder ShellAgent delegieren:

```python
# Würde fehlschlagen:
await delegate_to_agent(agent_type="data", task="Analysiere diese CSV")
# → "FEHLER: Agent 'data' nicht registriert. Verfügbar: ['executor', ...]"
```

---

### 4.3 KRITISCH — Meta-Agent orchestriert nicht

**Problem:** Der Meta-Agent hat `max_iterations=20` und sieht 68 Tools — darunter `delegate_to_agent`. Sein Prompt sagt er soll koordinieren. Aber sein System-Prompt enthält **keinen expliziten Hinweis** auf Delegation, und er tut es in der Praxis nicht.

```python
# agent/agents/meta.py — kein Aufruf von delegate_to_agent
# meta.py arbeitet mit Skills (YAML-Texte), nicht mit echten Agent-Delegationen
```

**Auswirkung:** Der Orchestrator ist funktionell kein echter Orchestrator — er löst Tasks selbst statt sie zu verteilen.

---

### 4.4 HOCH — Keine Timeouts für Delegationen

**Problem:** `agent_registry.delegate()` hat keinen Timeout-Parameter.

```python
result = await agent.run(task)  # kann ewig laufen
```

Wenn der delegierte Agent hängt (API-Timeout, Loop), hängt der aufrufende Agent mit.

**Worst-Case:** Image-Agent wartet auf Research-Agent, Research-Agent wartet auf externe API → System blockiert.

---

### 4.5 HOCH — Kein Retry bei Delegations-Fehler

**Problem:** Ein Delegations-Fehler führt sofort zum Abbruch:

```python
# agent_registry.py:273-284
except Exception as e:
    return f"FEHLER: Delegation an '{to_agent}' fehlgeschlagen: {e}"
    # Kein Retry, kein Fallback-Agent
```

Bei vorübergehenden API-Fehlern (Rate-Limit, Timeout) gibt es keine zweite Chance.

---

### 4.6 MITTEL — Memory-Isolation ist unvollständig

**Problem:** Agent-IDs in ChromaDB sind nicht authentifiziert.

```python
# Jeder Agent kann schreiben mit beliebiger agent_id:
await remember(text="...", agent_id="shell")  # kann auch executor aufrufen

# Jeder Agent kann ohne Filter alles lesen:
await recall(query="...", agent_filter="")  # sieht alle Memories aller Agenten
```

**Auswirkung:** Kein echter Schutz sensibler Daten zwischen Agenten.

---

### 4.7 MITTEL — Race-Condition bei parallelen async-Delegationen

**Problem:** ContextVar ist Task-safe, aber bei mehreren `await`s in einem asyncio-Task:

```python
# Theoretisch: Meta-Agent delegiert parallel
task1 = delegate_to_agent("research", "...")
task2 = delegate_to_agent("visual", "...")
results = await asyncio.gather(task1, task2)

# Stack: Was ist in Stack bei research? Gleichzeitig visual?
# ContextVar ist PER TASK — beide await-Chains laufen im selben Task
```

**Auswirkung:** Loop-Prevention kann bei paralleler Delegation fehlschlagen.

---

### 4.8 NIEDRIG — Session-Transfer fehlt bei Image→Research

**Problem:** `image.py` ruft `delegate_to_agent` ohne `session_id`:

```python
research_result = await delegate_to_agent(
    agent_type="research",
    task=research_task,
    from_agent="image",
    # session_id fehlt!
)
```

Research-Agent bekommt keinen Memory-Kontext der aktuellen Konversation.

---

## 5. Fehlender Kommunikationskanal — Analyse

### Was fehlt: Bidirektionaler Agent-Kommunikationskanal

**Aktueller Zustand:** Unidirektionales Request-Response
```
A ──→ B (task)
A ←── B (result)
```

**Was gebraucht wird für komplexe Aufgaben:**
```
A ──→ B ("Suche nach X")
A ←── B ("Ich finde nur Y und Z, reicht das?")
A ──→ B ("Ja, nimm Y")
A ←── B ("Fertig: Y-Ergebnis")
```

**Optionen für Implementierung:**

| Option | Aufwand | Qualität |
|--------|---------|----------|
| Memory als Message-Queue (kurzfristig) | niedrig | gering |
| Callback-Parameter in delegate() | mittel | gut |
| WebSocket-Kanal zwischen Agenten | hoch | sehr gut |
| Streaming-Ergebnis (AsyncGenerator) | mittel | gut |

---

## 6. Empfehlungen (priorisiert)

### Priorität 1 — Sofort umsetzbar

**A. M1–M4-Agenten im Registry registrieren**

```python
# agent_registry.py:register_all_agents()
from agent.agents.data import DataAgent
from agent.agents.shell import ShellAgent
# ...
registry.register_spec("data", "data", ["data", "csv", "analysis"], DataAgent)
registry.register_spec("shell", "shell", ["shell", "bash", "command"], ShellAgent)
```

**B. Session-ID an ImageAgent-Delegation übergeben**

```python
# image.py — session_id aus BaseAgent-Attribut weitergeben
research_result = await delegate_to_agent(
    agent_type="research",
    task=research_task,
    from_agent="image",
    session_id=getattr(self, "conversation_session_id", None),  # NEU
)
```

**C. Timeout für Delegationen hinzufügen**

```python
# agent_registry.py:delegate()
result = await asyncio.wait_for(
    agent.run(task),
    timeout=float(os.getenv("DELEGATION_TIMEOUT", "120"))
)
```

---

### Priorität 2 — Kurzfristig

**D. Meta-Agent-Prompt für aktive Delegation erweitern**

Der MetaAgent-Prompt sollte explizit Delegation in seinen Workflow einbauen:
- Bei Research-Tasks → delegate_to_agent("research", ...)
- Bei Code-Tasks → delegate_to_agent("developer", ...)
- Bei Daten-Tasks → delegate_to_agent("data", ...)

**E. Retry bei Delegations-Fehler**

```python
# agent_registry.py
for attempt in range(max_retries):
    try:
        result = await asyncio.wait_for(agent.run(task), timeout=120)
        break
    except (asyncio.TimeoutError, Exception) as e:
        if attempt == max_retries - 1:
            raise
        await asyncio.sleep(2 ** attempt)
```

**F. Partial-Result-Erkennung**

```python
# Nach agent.run():
if result in ("Limit erreicht.", "Max Iterationen.") or result.startswith("FEHLER:"):
    return {
        "status": "partial",
        "agent": to_agent,
        "result": result,
        "note": "Aufgabe nicht vollständig abgeschlossen"
    }
```

---

### Priorität 3 — Mittelfristig

**G. Bidirektionaler Kommunikationskanal via Memory**

Kurzfristiger Workaround: Memory als strukturierter Message-Channel:

```python
# Agent A vor Delegation:
await remember(
    text=f"@research: Falls keine direkten Ergebnisse zu X, suche Y als Alternative",
    source="delegation_hint",
    agent_id="image_to_research"
)

# Research-Agent liest Hint:
hints = await recall(query="delegation hints", agent_filter="image_to_research")
```

---

## 7. Gesamtbewertung

| Bereich | Status | Note |
|---------|--------|------|
| Loop-Prevention | ✅ Gut | ContextVar-Stack zuverlässig |
| Lazy-Instantiierung | ✅ Gut | Spart Ressourcen |
| Memory-Sharing | ⚠️ Teilweise | Kein echter Kanal, schwache Isolation |
| Delegations-Tiefe | ⚠️ Begrenzt | Nur Image→Research aktiv |
| Registry-Vollständigkeit | ❌ Lücke | 5 Agenten fehlen |
| Feedback-Loops | ❌ Fehlt | Kein Rückkanal während Delegation |
| Timeout/Retry | ❌ Fehlt | Delegationen können hängen |
| Meta-Orchestrierung | ❌ Inaktiv | MetaAgent delegiert nie |
| Partial-Result-Handling | ❌ Fehlt | Kein structured partial response |
| Session-Kontinuität | ⚠️ Teilweise | Fehlt bei Image→Research |

---

## Anhang: Code-Referenzen

| Konzept | Datei | Zeilen |
|---------|-------|--------|
| AgentRegistry | agent/agent_registry.py | 30–316 |
| Delegation-Methode | agent/agent_registry.py | 187–288 |
| Loop-Prevention | agent/agent_registry.py | 211–224 |
| ContextVar-Stack | agent/agent_registry.py | 53–55 |
| Canvas-Logging | agent/agent_registry.py | 69–135 |
| register_all_agents | agent/agent_registry.py | 319–372 |
| delegate_to_agent Tool | tools/delegation_tool/tool.py | 15–65 |
| BaseAgent Tool-Call | agent/base_agent.py | 610–650 |
| ImageAgent Delegation | agent/agents/image.py | 99–131 |
| Memory ChromaDB | tools/memory_tool/tool.py | 487–555 |
| Memory SQLite Fakten | tools/memory_tool/tool.py | 284–425 |
| Dispatcher Routing | main_dispatcher.py | 611–654 |
