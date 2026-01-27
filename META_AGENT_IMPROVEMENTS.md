# Meta-Agent Verbesserungen

## ✅ Implementierte Features

### **1. Visual Agent Integration**

Der Meta-Agent kann jetzt visuelle Aufgaben direkt an den Visual Agent delegieren.

**Neue Funktion:**
```python
execute_visual_task(task, max_iterations=20, monitor=1)
```

**Beispiele:**
```python
# Im Meta-Agent
Action: {"method": "execute_visual_task", "params": {
    "task": "Öffne ChatGPT und frage 'Wie geht es dir?'",
    "max_iterations": 20,
    "monitor": 1
}}
```

**CLI:**
```bash
python agent/meta_agent.py "Öffne Firefox und gehe zu google.com"
```

---

### **2. Tool Discovery (Dynamische Tool-Liste)**

Der Meta-Agent lädt beim Start automatisch alle verfügbaren Tools vom MCP-Server.

**Funktion:**
```python
get_available_tools() -> str
```

**Was passiert:**
1. Bei jedem Task-Start: GET `/get_tool_descriptions`
2. Server liefert formatierte Tool-Liste
3. Meta-Agent bekommt aktuelle Tools in System Prompt
4. LLM weiß welche Tools verfügbar sind

**Vorteil:**
- Keine veralteten Tool-Listen im Prompt
- Neue Tools sofort verfügbar
- Dynamische Anpassung an Server-Konfiguration

---

## 🔧 Technische Details

### **Geänderte Dateien:**

**`agent/meta_agent.py`:**
- ✅ `get_available_tools()` - Tool Discovery
- ✅ `execute_visual_task()` - Visual Agent Delegation
- ✅ `build_system_prompt()` - Dynamischer System Prompt
- ✅ `run_meta_task_async()` - Tool Discovery beim Start
- ✅ System Prompt erweitert mit Visual-Beispielen

### **Neue Features im System Prompt:**

**Visuelle Automation:**
```
- execute_visual_task(task, max_iterations, monitor)
  Delegiert an Visual Agent

Beispiele:
- "Öffne ChatGPT und frage 'Wie geht es dir?'"
- "Klicke auf den Login-Button und gib Credentials ein"
- "Suche in Google nach 'Python Tutorials'"
```

**Manuelle UI-Interaktion (Fallback):**
```
- scan_ui_elements(element_types, use_zoom)
- hybrid_find_element(text, element_type, refine)
- click_at(x, y)
- type_text(text, press_enter)
```

---

## 📊 Workflow-Beispiele

### **Beispiel 1: Browser-Automation**

**User:** "Öffne ChatGPT und stelle eine Frage"

**Meta-Agent:**
```
Thought: Das ist eine visuelle UI-Aufgabe. Ich delegiere an den Visual Agent.
Action: {"method": "execute_visual_task", "params": {
    "task": "Öffne Firefox, navigiere zu chatgpt.com und frage 'Wie geht es dir?'",
    "max_iterations": 20
}}

Observation: {"status": "success", "result": "Visual Agent hat die Aufgabe erfolgreich abgeschlossen"}

Thought: Visual Agent war erfolgreich. Aufgabe erledigt.
Final Answer: Ich habe ChatGPT geöffnet und die Frage gestellt.
```

---

### **Beispiel 2: Tool-Liste anzeigen**

**User:** "Welche Tools sind verfügbar?"

**Meta-Agent:**
```
Thought: Ich liste die verfügbaren Tools auf.
Action: {"method": "list_tools"}

Observation: {"tools": [...116 Tools...]}

Final Answer: Es sind 116 Tools verfügbar, darunter:
- Visuelle Automation: scan_ui_elements, hybrid_find_element, click_at
- Browser: start_visual_browser, open_url
- Suche: search_web, search_images
- Memory: remember, recall
- Tasks: add_task, update_task
[...]
```

---

## 🚀 Verwendung

### **CLI:**
```bash
# Visuelle Aufgabe
python agent/meta_agent.py "Öffne Google und suche nach 'AI News'"

# Tool-Erstellung
python agent/meta_agent.py "Erstelle ein Tool für Wetter-Abfrage"

# Planung
python agent/meta_agent.py "Plane einen Workflow für tägliche Backups"
```

### **Programmatisch:**
```python
from agent.meta_agent import run_meta_task

result = run_meta_task("Öffne ChatGPT")
print(result)
```

### **Async:**
```python
import asyncio
from agent.meta_agent import run_meta_task_async

async def main():
    result = await run_meta_task_async("Deine Aufgabe", max_steps=10)
    print(result)

asyncio.run(main())
```

---

## 🧪 Tests

**Test-Script ausführen:**
```bash
python test_meta_agent.py
```

**Tests:**
1. ✅ Tool Discovery (lädt Tools vom Server)
2. ✅ Visual Agent Delegation
3. ⏸️ Echte visuelle Aufgabe (optional, wenn Server läuft)

---

## ⚙️ Konfiguration

**`.env`-Variablen:**
```bash
# Meta-Agent
ANTHROPIC_API_KEY=sk-...
PLANNING_MODEL=claude-sonnet-4-5-20250929
META_AGENT_DEBUG=1

# MCP Server
MCP_URL=http://127.0.0.1:5000
```

---

## 🔄 Nächste Schritte (Optional)

### **Noch nicht implementiert:**

**3. Native Tool Use API**
- Statt Regex-Parsing → Claude Official Tool Use
- Strukturierte Tool-Calls
- Besser für komplexe Parameter

**4. Memory Integration**
- Kontext zwischen Aufrufen speichern
- `remember(key, value)` vor Task
- `recall(query)` bei Task-Start

**5. Multi-Modal Screenshots**
- Screenshot als Vision Input für Claude
- "Sieh dir den Bildschirm an und..."

**6. Streaming Output**
- Live-Updates während Task-Ausführung
- Fortschrittsanzeige

---

## 📝 Changelog

**Version 2.1 (aktuell):**
- ✅ Visual Agent Integration
- ✅ Tool Discovery (dynamisch)
- ✅ Erweiterter System Prompt
- ✅ Beispiele für visuelle Aufgaben

**Version 2.0:**
- Claude Sonnet 4.5
- ReAct Loop
- Tool Calling
- Fehlertoleranz

---

## 🐛 Bekannte Einschränkungen

1. **Visual Agent Tool nicht als MCP-Tool:**
   - Derzeit Fallback: Manuelle Tool-Sequenz
   - Lösung: Visual Agent als MCP-Tool registrieren

2. **Tool-Beschreibungen können lang sein:**
   - Filter auf wichtigste Tools (max 200 Zeilen)
   - Könnte optimiert werden

3. **Keine Vision-Input:**
   - Meta-Agent "sieht" nicht was passiert
   - Verlässt sich auf Tool-Ergebnisse

---

## 💡 Tipps

**Best Practices:**
- Für UI-Aufgaben: Immer `execute_visual_task` nutzen
- Für Code: `implement_feature` + `register_new_tool_in_server`
- Für Planung: `add_task` an Spezialisten delegieren

**Debugging:**
- `META_AGENT_DEBUG=1` für detaillierte Logs
- Logs in Console ausgeben
- Tool-Aufrufe werden geloggt

**Performance:**
- Tool Discovery cached nicht → jedes Mal neu laden
- Bei vielen Schritten: `max_steps` erhöhen
- Bei Timeouts: `timeout` Parameter anpassen

---

## 📚 Weitere Dokumentation

- **Visual Agent:** `agent/visual_agent.py`
- **SoM Tool:** `tools/som_tool/tool.py`
- **Hybrid Detection:** `tools/hybrid_detection_tool/tool.py`
- **MCP Server:** `server/mcp_server.py`
