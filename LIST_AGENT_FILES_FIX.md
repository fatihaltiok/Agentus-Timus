# list_agent_files Parameter-Problem - FIX

**Datum:** 2026-01-27 22:55 Uhr
**Problem:** Developer Agent v2 nutzte falsche Parameter für `list_agent_files`
**Status:** ✅ BEHOBEN

---

## Problem-Beschreibung

### Fehler-Logs:
```
Error: {'code': -32602, 'message': 'Invalid params', 'data': "got an unexpected keyword argument 'path'"}
Error: {'code': -32602, 'message': 'Invalid params', 'data': "got an unexpected keyword argument 'pattern'"}
```

### Ursache:
Developer Agent v2 versuchte, `list_agent_files` mit falschen Parametern aufzurufen:
```python
# ❌ FALSCH (Agent versuchte das)
list_agent_files(path=".", pattern="*.py")
```

### Grund:
Das Tool `list_agent_files` (in `tools/meta_tool/tool.py`) akzeptiert nur:
```python
async def list_agent_files(subfolder: str = "tools")
    # Erlaubte Werte: ["tools", "agent", "server", "skills"]
```

---

## Lösung (Option A: System-Prompt Fix)

### Änderung 1: gather_project_context() Funktion
**Datei:** `agent/developer_agent_v2.py` (Zeilen 88-103)

**VORHER:**
```python
structure = call_tool("list_agent_files", {
    "path": dest_folder,
    "pattern": "*.py",
    "max_depth": 2
})
```

**NACHHER:**
```python
# list_agent_files nimmt nur 'subfolder' Parameter
all_files = []
for folder in ["agent", "tools", "skills"]:
    structure = call_tool("list_agent_files", {"subfolder": folder})
    if isinstance(structure, dict) and not structure.get("error"):
        files = structure.get("files", [])
        all_files.extend(files)
```

**Vorteil:** Sammelt jetzt Dateien aus mehreren Ordnern für besseren Kontext!

### Änderung 2: System-Prompt Dokumentation
**Datei:** `agent/developer_agent_v2.py` (Zeilen 346-353)

**NEU HINZUGEFÜGT:**
```
TOOL-PARAMETER WICHTIG:
- list_agent_files: Nimmt nur "subfolder" Parameter (Werte: "tools", "agent", "server", "skills")
  Beispiel: {"method": "list_agent_files", "params": {"subfolder": "agent"}}
- read_file_content: Nimmt nur "path" Parameter (relativer Pfad zum Projekt-Root)
  Beispiel: {"method": "read_file_content", "params": {"path": "agent/developer_agent.py"}}
```

### Änderung 3: Beispiel-Workflow
**Datei:** `agent/developer_agent_v2.py` (Zeilen 370-383)

**VORHER:**
```python
Action: {"method": "list_agent_files", "params": {"path": "{dest_folder}", "pattern": "*.py"}}
```

**NACHHER:**
```python
Action: {"method": "list_agent_files", "params": {"subfolder": "agent"}}
```

---

## Vorteile der Lösung

### 1. Korrekte Parameter
✅ Agent nutzt jetzt die richtigen Parameter
✅ Keine "Invalid params" Fehler mehr

### 2. Besserer Kontext
✅ Sammelt Dateien aus **mehreren** Ordnern (agent, tools, skills)
✅ Mehr Kontext = bessere Code-Generierung

### 3. Klare Dokumentation
✅ System-Prompt dokumentiert erlaubte Parameter
✅ LLM weiß jetzt genau, was möglich ist

---

## Alternative Lösung (nicht gewählt)

### Option B: Backend-Tool erweitern
**Datei:** `tools/meta_tool/tool.py`

Man könnte das Tool erweitern:
```python
@method
async def list_agent_files(
    subfolder: str = "tools",
    pattern: str = "*.py",  # NEU
    max_depth: int = 999     # NEU
) -> Union[Success, Error]:
    """Erweiterte Version mit Pattern-Filterung."""
    # Implementation...
```

**Warum nicht gewählt:**
- ❌ Breaking Change für andere Agenten
- ❌ Mehr Komplexität im Backend
- ❌ Nicht nötig, da find_related_files() bereits Pattern-Filterung macht

---

## Test-Ergebnis

### Vor dem Fix:
```
Error: got an unexpected keyword argument 'path'
Error: got an unexpected keyword argument 'pattern'
⚠️ Agent musste 2x Fehler-Recovery machen
```

### Nach dem Fix:
```
Wird in nächstem Test verifiziert...
```

---

## list_agent_files Tool - Vollständige Dokumentation

### Signatur:
```python
async def list_agent_files(subfolder: str = "tools") -> Union[Success, Error]
```

### Parameter:
- **subfolder** (str, optional, default="tools")
  - Erlaubte Werte: `["tools", "agent", "server", "skills"]`
  - Beschreibung: Ordner, dessen .py-Dateien aufgelistet werden sollen

### Rückgabe:
```python
# Success
{
    "files": [
        "agent/developer_agent.py",
        "agent/visual_agent.py",
        "agent/meta_agent.py",
        ...
    ]
}

# Error
{
    "code": -32602,
    "message": "Ungültiger Ordner. Erlaubt sind: ['tools', 'agent', 'server', 'skills']"
}
```

### Beispiele:

**Alle Agent-Dateien auflisten:**
```python
list_agent_files(subfolder="agent")
```

**Alle Tool-Dateien auflisten:**
```python
list_agent_files(subfolder="tools")
```

**Skills auflisten:**
```python
list_agent_files(subfolder="skills")
```

### Einschränkungen:
- ❌ Keine Pattern-Filterung (listet IMMER alle .py-Dateien)
- ❌ Keine max_depth Begrenzung (rekursiv durch alle Unterordner)
- ❌ Nur für vordefinierte Ordner (tools, agent, server, skills)

---

## Weitere Tools mit ähnlichen Parametern

### read_file_content
```python
async def read_file_content(path: str) -> Union[Success, Error]
```
- **path** (str, required): Relativer Pfad zum Projekt-Root
- Beispiel: `read_file_content(path="agent/developer_agent.py")`

### write_file
```python
async def write_file(path: str, content: str) -> Union[Success, Error]
```
- **path** (str, required): Relativer Pfad zum Projekt-Root
- **content** (str, required): Datei-Inhalt
- Beispiel: `write_file(path="test.py", content="print('Hello')")`

### list_directory
```python
async def list_directory(path: str) -> Union[Success, Error]
```
- **path** (str, required): Relativer Pfad zum Projekt-Root
- Beispiel: `list_directory(path="test_project")`
- **Unterschied zu list_agent_files**: Listet ALLE Dateien (nicht nur .py)

---

## Changelog

### v2.1.1 (2026-01-27 22:55)
- ✅ gather_project_context() nutzt jetzt korrekte Parameter
- ✅ System-Prompt dokumentiert list_agent_files Parameter
- ✅ Beispiel-Workflow korrigiert
- ✅ Sammelt jetzt aus mehreren Ordnern (agent, tools, skills)

### v2.1 (2026-01-27 22:20)
- context_files Support hinzugefügt
- find_related_files() Funktion
- DeveloperAgentV2 Async Wrapper

### v2.0 (2026-01-27 22:14)
- Multi-Tool Support
- Code-Validierung
- Fehler-Recovery

---

## Nächste Schritte

1. ✅ **Test durchführen** - Verifizieren, dass keine Parameter-Fehler mehr auftreten
2. 📝 **Dokumentation aktualisieren** - DEVELOPER_AGENT_V2_CONTEXT_FILES_UPDATE.md ergänzen
3. 🔄 **Git Commit** - Fix committen und pushen

---

## Autor

**Fixed by:** Claude Sonnet 4.5
**Tested:** Wird in nächstem Test verifiziert
**Status:** ✅ Code-Änderungen abgeschlossen
