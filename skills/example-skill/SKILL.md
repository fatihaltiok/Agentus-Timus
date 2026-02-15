---
name: example-skill
description: Beispiel-Skill für Timus. Use when you want to learn how skills work or as a template for creating new skills.
version: 1.0.0
author: Timus System
tags: example, template, reference
---

# Example Skill

Dieser Skill demonstriert den OpenClaw-kompatiblen Standard für Timus Skills.

## Quick Start

### Was dieser Skill macht

Der Example Skill zeigt:
1. YAML Frontmatter (Metadata)
2. Markdown Body (Instructions)
3. Scripts (Wiederverwendbarer Code)
4. References (On-demand Dokumentation)
5. Progressive Disclosure (Context-Effizienz)

### Verwendung

```python
# Skill laden
from utils.skill_parser import parse_skill_md

skill = parse_skill_md(Path("skills/example-skill/SKILL.md"))

# Metadata (immer verfügbar)
print(skill.name)           # "example-skill"
print(skill.description)    # aus Frontmatter

# Body (bei Trigger geladen)
context = skill.get_full_context()
```

## Advanced

### Skill-Struktur

```
example-skill/
├── SKILL.md              # Diese Datei
├── scripts/
│   └── hello_world.py    # Beispiel-Script
└── references/
    ├── best-practices.md # Guidelines
    └── workflow-patterns.md # Patterns
```

### Progressive Disclosure

1. **Metadata** (~100 words): Name, Description, Tags
   - Wird IMMER in den Context geladen
   - Dient der Skill-Auswahl

2. **SKILL.md Body** (~500-5000 words): Instruktionen
   - Wird nur geladen wenn Skill triggert
   - Haupt-Workflow und Quick Start

3. **References** (unlimited): Detaillierte Docs
   - Werden on-demand geladen
   - Schemas, API-Dokumentation, etc.

### Script ausführen

```python
# Script aus dem Skill ausführen
result = skill.execute_script("hello_world.py")
print(result["stdout"])
```

### Reference laden

```python
# On-demand Reference laden
best_practices = skill.load_reference("best-practices.md")
```

## References

- **Best Practices**: Siehe [best-practices.md](references/best-practices.md)
- **Workflow Patterns**: Siehe [workflow-patterns.md](references/workflow-patterns.md)

---

## Available Resources

### Scripts
- `hello_world.py` - Beispiel Python Script

### References
- `best-practices.md` - OpenClaw Best Practices
- `workflow-patterns.md` - Common Workflow Patterns
