# Timus Skill-System Implementierungsplan

Basierend auf OpenClaw Best Practices

---

## Phase 1: SKILL.md Parser (2h) ✅ COMPLETE

**Ziel:** Parser für YAML Frontmatter + Markdown Body

**Dateien:**
- `utils/skill_parser.py` - Hauptparser
- `utils/skill_types.py` - Dataclasses
- `tests/test_skill_parser.py` - Tests

**Akzeptanzkriterien:**
- [ ] YAML Frontmatter wird korrekt geparst
- [ ] Markdown Body wird extrahiert
- [ ] Fehlerbehandlung für ungültige Dateien
- [ ] Tests mit Beispiel-SKILL.md

---

## Phase 2: Skill-Ordner-Struktur (1h) ✅ COMPLETE

**Ziel:** Standardisierte Ordnerstruktur wie OpenClaw

**Dateien:**
- `skills/__init__.py` - Erweitern
- `skills/README.md` - Dokumentation
- `skills/example-skill/SKILL.md` - Beispiel

**Struktur pro Skill:**
```
skills/{skill-name}/
├── SKILL.md              # YAML + Markdown (required)
├── scripts/              # Python/Bash (optional)
├── references/           # Docs, Schemas (optional)
└── assets/               # Templates, Bilder (optional)
```

**Akzeptanzkriterien:**
- [ ] Ordnerstruktur automatisch erstellbar
- [ ] Beispiel-Skill vorhanden
- [ ] README mit Konventionen

---

## Phase 3: init_skill Tool (3h)

**Ziel:** Automatische Skill-Erstellung

**Dateien:**
- `tools/init_skill_tool/tool.py` - Tool-Logik
- `tools/init_skill_tool/templates/SKILL.md.template` - Template
- `tools/init_skill_tool/__init__.py`

**Features:**
```python
init_skill(
    name="pdf-processor",
    resources=["scripts", "references"],
    examples=True
)
```

**Akzeptanzkriterien:**
- [ ] Skill-Ordner wird erstellt
- [ ] SKILL.md Template wird generiert
- [ ] Optionale Ressourcen-Ordner werden erstellt
- [ ] Beispiel-Skripte werden hinzugefügt (optional)
- [ ] Validierung des Skill-Namens

---

## Phase 4: MetaAgent Erweiterung (4h) ✅ COMPLETE

**Ziel:** MetaAgent lädt und orchestriert Skills

**Dateien:**
- `agent/meta_agent.py` - Erweitern
- `utils/skill_orchestrator.py` - Neue Datei

**Features:**
```python
class MetaAgent(BaseAgent):
    def __init__(self, ...):
        self.skills = self._load_all_skills()
        self.skill_selector = SkillSelector(self.skills)
    
    async def run(self, task):
        # 1. Skill auswählen basierend auf Task
        skill = self.skill_selector.select(task)
        
        # 2. Skill-Metadaten laden (YAML Frontmatter)
        context = skill.get_metadata()
        
        # 3. Bei Trigger: SKILL.md Body laden
        if skill.should_trigger(task):
            context += skill.get_body()
        
        # 4. Bei Bedarf: References laden
        if skill.needs_reference(task):
            context += skill.load_reference("schema.md")
        
        # 5. Task mit Skill-Kontext ausführen
        return await self.execute_with_context(task, context)
```

**Akzeptanzkriterien:**
- [ ] Alle Skills werden beim Start geladen
- [ ] Skill-Auswahl basierend auf Keywords
- [ ] Progressive Disclosure funktioniert
- [ ] References werden on-demand geladen
- [ ] Skill-Cross-Referenzen funktionieren

---

## Phase 5: Skill-Creator Skill (3h) ✅ COMPLETE

**Ziel:** Ein Skill, der Skills erstellt (Meta!)

**Dateien:**
- `skills/skill-creator/SKILL.md` - Der Skill selbst
- `skills/skill-creator/references/best-practices.md`
- `skills/skill-creator/references/workflow-patterns.md`

**Inhalt SKILL.md:**
```yaml
---
name: skill-creator
description: Create or update Skills for Timus. Use when designing, 
             structuring, or packaging skills with scripts, references, 
             and assets.
---

# Skill Creator for Timus

## Step 1: Understand with Examples
- Ask user: "What should this skill do?"
- Ask user: "Give me 3 concrete examples"

## Step 2: Plan Resources
Analyze examples:
1. What scripts are needed?
2. What references? (schemas, docs)
3. What assets? (templates, images)

## Step 3: Initialize
Run: `init_skill_tool.init_skill(name, resources)`

## Step 4: Edit SKILL.md
- Write YAML frontmatter
- Add quick start examples
- Link references when needed

## Step 5: Package
Run: `package_skill_tool.package_skill(path)`
```

**Akzeptanzkriterien:**
- [ ] Skill-Creator kann andere Skills erstellen
- [ ] Best-Practices Referenz vorhanden
- [ ] Workflow-Patterns Referenz vorhanden
- [ ] Getestet mit Beispiel-Skill

---

## Gesamt-Zeit: ~13 Stunden

| Phase | Zeit | Puffer |
|-------|------|--------|
| 1 | 2h | +1h |
| 2 | 1h | +0.5h |
| 3 | 3h | +1h |
| 4 | 4h | +2h |
| 5 | 3h | +1h |
| **Total** | **13h** | **~20h realistisch** |

---

## Start: Phase 1
