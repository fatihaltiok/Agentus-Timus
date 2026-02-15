# Skill Loading Mechanismus

Wie werden Skills geladen nachdem sie erstellt wurden?

---

## 🔄 **Szenarien**

### 1. **Initial Loading** (MetaAgent Start)

```python
# Beim MetaAgent-Start (einmalig)
class MetaAgent(BaseAgent):
    def __init__(self, ...):
        self.skill_registry = SkillRegistry()
        self._init_skill_system()  # ← Lädt alle Skills

    def _init_skill_system(self):
        skills_base = Path("skills")
        self.skill_registry.load_all_from_directory(skills_base)
        # Ergebnis: Alle vorhandenen Skills geladen
```

**Wann:** Einmal beim Server/Agent Start

---

### 2. **Dynamisches Nachladen** (Nach Skill-Erstellung)

**Problem:**
```python
# 1. MetaAgent startet
agent = MetaAgent()
#    → Lädt 3 Skills (example, skill-creator, square)

# 2. Neuer Skill wird erstellt
init_skill_tool(name="csv-processor")
#    → Erstellt: skills/csv-processor/SKILL.md

# 3. MetaAgent kennt neuen Skill NICHT!
#    → Registry hat noch nur 3 Skills
```

**Lösungen:**

#### Option A: Automatisches Reload nach init_skill

```python
# In init_skill_tool:
result = init_skill(...)  # Skill erstellen

# Dann: Registry neu laden
if self.meta_agent.skill_registry:
    self.meta_agent.skill_registry.load_all_from_directory(Path("skills"))
    log.info("✅ Skills neu geladen (inkl. neuer Skill)")
```

#### Option B: Manuelles Reload via Tool

```python
@method
async def reload_skills_tool() -> Success | Error:
    """
    Lädt alle Skills neu (nach Erstellung neuer Skills).
    
    Usage:
        1. Create skill with init_skill_tool
        2. Call reload_skills_tool
        3. New skill is available immediately
    """
    try:
        from utils.skill_types import SkillRegistry
        
        registry = SkillRegistry()
        registry.load_all_from_directory(Path("skills"))
        
        # Update MetaAgent
        if hasattr(meta_agent, 'skill_registry'):
            meta_agent.skill_registry = registry
        
        return Success({
            "success": True,
            "skills_count": len(registry.skills),
            "skills": registry.list_all()
        })
    except Exception as e:
        return Error(code=-32200, message=str(e))
```

#### Option C: File Watcher (Automatisch)

```python
# In MCP-Server oder MetaAgent:
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

class SkillFileHandler(FileSystemEventHandler):
    def on_created(self, event):
        if event.src_path.endswith("SKILL.md"):
            log.info(f"🆕 Neue SKILL.md erkannt: {event.src_path}")
            # Reload skills
            skill_registry.load_all_from_directory(Path("skills"))

# Setup
observer = Observer()
observer.schedule(SkillFileHandler(), path="skills", recursive=True)
observer.start()
```

---

## 🎯 **Empfohlene Lösung: Auto-Reload in init_skill_tool**

```python
# tools/init_skill_tool/tool.py

def init_skill(...):
    """Erstellt Skill + lädt Registry neu"""
    
    # 1. Skill erstellen
    result = _create_skill_files(...)
    
    if result.success:
        # 2. Globalen Registry neu laden
        from utils.skill_types import SkillRegistry
        
        # Singleton-Pattern: Globale Registry aktualisieren
        if hasattr(init_skill, '_global_registry'):
            init_skill._global_registry.load_all_from_directory(Path("skills"))
            log.info(f"✅ Skills neu geladen: {len(init_skill._global_registry.skills)} total")
    
    return result
```

---

## 📊 **Vergleich**

| Methode | Automatisch | Latenz | Komplexität | Empfohlung |
|---------|-------------|--------|-------------|------------|
| **A: Auto-Reload** | ✅ Ja | Gering | Niedrig | ⭐⭐⭐ |
| **B: Manuelles Tool** | ❌ Nein | N/A | Niedrig | ⭐⭐ |
| **C: File Watcher** | ✅ Ja | Sehr gering | Mittel | ⭐⭐⭐ |
| **D: Neustart** | ❌ Nein | Hoch | Niedrig | ⭐ |

---

## 🔧 **Quick Fix implementieren**

Soll ich die **Auto-Reload** Funktion in `init_skill_tool` implementieren?

Dann würde der Flow so aussehen:

```bash
Du> create a skill for CSV processing

MetaAgent:
  1. Load skill-creator Skill ✅
  2. Run init_skill_tool ✅
  3. Auto-reload all skills ✅
  4. New skill immediately available ✅

Result: "csv-processor skill created and loaded!"
```

**Soll ich das implementieren?** 🚀
