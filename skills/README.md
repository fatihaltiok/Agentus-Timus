# Timus Skills

Modulares Skill-System für Timus - inspiriert von OpenClaw.

---

## Ordner-Struktur

```
skills/
├── README.md                   # Diese Datei
├── {skill-name}/               # Ein Ordner pro Skill
│   ├── SKILL.md               # YAML Frontmatter + Markdown Body (REQUIRED)
│   ├── scripts/               # Python/Bash Scripts (optional)
│   ├── references/            # Dokumentation, Schemas (optional)
│   └── assets/                # Templates, Bilder (optional)
```

---

## SKILL.md Format

Jede SKILL.md besteht aus:

1. **YAML Frontmatter** (am Anfang):
```yaml
---
name: skill-name
description: Wann dieser Skill verwendet wird. Sei spezifisch!
version: 1.0.0  # optional
author: Dein Name  # optional
tags: tag1, tag2  # optional
---
```

2. **Markdown Body** (Instruktionen):
```markdown
# Skill Name

## Quick Start
Grundlegende Nutzung...

## Advanced
Fortgeschrittene Features...

## References
- Schema: Siehe [SCHEMA.md](references/SCHEMA.md)
- API: Siehe [API.md](references/API.md)
```

---

## Regeln

### ✅ DO
- **Concise is Key**: Nur Kontext den Codex wirklich braucht
- **Progressive Disclosure**: 
  - Metadata (~100 words) - immer geladen
  - SKILL.md Body (<5k words) - nur bei Trigger
  - References (unlimited) - on-demand geladen
- **Scripts**: Für deterministische, wiederholbare Aufgaben
- **References**: Für Schemas, API-Docs, Policies

### ❌ DON'T
- Keine README.md, CHANGELOG.md, etc. (erzeugt Clutter)
- Keine tief verschachtelten Ordner (max 1 Level)
- Keine duplizierten Informationen (entweder SKILL.md oder References)
- Keine langen Beschreibungen (max 500 chars)

---

## Beispiel-Skill erstellen

```bash
# Nutze das init_skill Tool (coming soon)
python -m tools.init_skill \
    name=my-skill \
    resources=scripts,references \
    path=skills/
```

Oder manuell:

```bash
mkdir -p skills/my-skill/{scripts,references}
cat > skills/my-skill/SKILL.md << 'EOF'
---
name: my-skill
description: Does something useful. Use when you need to...
---

# My Skill

## Quick Start
Instructions here...
EOF
```

---

## Skills laden

```python
from utils.skill_parser import parse_skill_md
from utils.skill_types import SkillRegistry

# Einzelner Skill
skill = parse_skill_md(Path("skills/my-skill/SKILL.md"))

# Alle Skills laden
registry = SkillRegistry()
registry.load_all_from_directory(Path("skills"))

# Skill auswählen
task = "do something"
selected = registry.select_for_task(task, top_k=3)
```

---

## Vorhandene Skills

| Skill | Beschreibung | Status |
|-------|-------------|--------|
| `square` | Beispiel-Skill (Mathe) | Legacy |
| `example-skill` | Beispiel nach OpenClaw Standard | ✅ |

---

## Weiterentwicklung

Geplant:
- [ ] `init_skill.py` Tool
- [ ] `package_skill.py` Tool  
- [ ] Skill-Creator Skill
- [ ] MetaAgent Skill-Orchestrierung
