# tools/init_skill_tool/tool.py
"""
Init Skill Tool - Erstellt neue Skills mit Template.

Basierend auf OpenClaw's init_skill.py
Usage: init_skill(name="my-skill", resources=["scripts"])
"""

import os
import re
import logging
from pathlib import Path
from typing import List, Optional, Dict
from dataclasses import dataclass

from tools.tool_registry_v2 import tool, ToolParameter as P, ToolCategory as C

log = logging.getLogger(__name__)

# Templates
SKILL_MD_TEMPLATE = '''---
name: {name}
description: {description}
version: 1.0.0
author: Timus
---

# {title}

## Quick Start

TODO: Füge eine kurze Anleitung hinzu.

## Usage

```python
# Beispiel-Code hier
print("Hello from {name}!")
```

## Advanced

TODO: Füge fortgeschrittene Features hinzu.

## References

- Siehe [REFERENCE.md](references/REFERENCE.md)
'''

REFERENCE_MD_TEMPLATE = '''# {title} Reference

Technische Dokumentation für {name}.

## Schema

TODO: Füge Schemas, API-Docs oder Policies hinzu.
'''

EXAMPLE_SCRIPT_TEMPLATE = '''#!/usr/bin/env python3
"""
Beispiel-Script für {name}.
"""

import sys

def main():
    print("Hello from {name}!")
    print("Dieses Script ist Teil des Skills und kann ausgeführt werden.")
    return 0

if __name__ == "__main__":
    sys.exit(main())
'''


@dataclass
class InitSkillResult:
    """Ergebnis der Skill-Initialisierung"""
    success: bool
    skill_name: str
    skill_path: Path
    created_files: List[str]
    error: Optional[str] = None


def _sanitize_name(name: str) -> str:
    """Bereinigt Skill-Namen"""
    name = name.lower().strip()
    name = re.sub(r'[^a-z0-9\-]', '-', name)  # Ungültige Chars -> Hyphen
    name = re.sub(r'-+', '-', name)          # Mehrere Hyphens -> Einzeln
    name = name.strip('-')                  # Trim
    return name


def _validate_name(name: str) -> tuple[bool, Optional[str]]:
    """Validiert Skill-Namen"""
    if not name or len(name) < 2:
        return False, "Name zu kurz (min. 2 Zeichen)"

    if len(name) > 64:
        return False, "Name zu lang (max. 64 Zeichen)"

    if not re.match(r'^[a-z][a-z0-9\-]*$', name):
        return False, "Name muss mit Buchstaben beginnen, nur Kleinbuchstaben, Zahlen, Hyphens"

    return True, None


def init_skill(
    name: str,
    description: Optional[str] = None,
    resources: Optional[List[str]] = None,
    examples: bool = False,
    base_path: Path = Path("skills")
) -> InitSkillResult:
    """
    Erstellt einen neuen Skill mit Template.
    """

    # 1. Validierung
    clean_name = _sanitize_name(name)
    is_valid, error = _validate_name(clean_name)

    if not is_valid:
        return InitSkillResult(
            success=False,
            skill_name=name,
            skill_path=Path(),
            created_files=[],
            error=f"Ungültiger Skill-Name: {error}"
        )

    # 2. Prüfe ob Skill bereits existiert
    skill_dir = base_path / clean_name
    if skill_dir.exists():
        return InitSkillResult(
            success=False,
            skill_name=clean_name,
            skill_path=skill_dir,
            created_files=[],
            error=f"Skill '{clean_name}' existiert bereits unter {skill_dir}"
        )

    # 3. Erstelle Verzeichnisse
    created_files = []

    try:
        skill_dir.mkdir(parents=True)
        created_files.append(str(skill_dir.relative_to(base_path.parent)))

        # 4. SKILL.md erstellen
        title = clean_name.replace('-', ' ').title()
        desc = description or f"Skill for {clean_name}. Use when you need to..."

        skill_md_content = SKILL_MD_TEMPLATE.format(
            name=clean_name,
            title=title,
            description=desc
        )

        skill_md_path = skill_dir / "SKILL.md"
        skill_md_path.write_text(skill_md_content, encoding='utf-8')
        created_files.append(str(skill_md_path.relative_to(base_path.parent)))

        # 5. Ressourcen-Verzeichnisse erstellen
        if resources:
            for resource in resources:
                resource_dir = skill_dir / resource
                resource_dir.mkdir(exist_ok=True)
                created_files.append(str(resource_dir.relative_to(base_path.parent)))

                # 6. Beispiel-Files erstellen (falls gewünscht)
                if examples:
                    if resource == "scripts":
                        script_path = resource_dir / "example.py"
                        script_content = EXAMPLE_SCRIPT_TEMPLATE.format(
                            name=clean_name,
                            title=title
                        )
                        script_path.write_text(script_content, encoding='utf-8')
                        # Make executable on Unix
                        if os.name != 'nt':
                            script_path.chmod(0o755)
                        created_files.append(str(script_path.relative_to(base_path.parent)))

                    elif resource == "references":
                        ref_path = resource_dir / "REFERENCE.md"
                        ref_content = REFERENCE_MD_TEMPLATE.format(
                            name=clean_name,
                            title=title
                        )
                        ref_path.write_text(ref_content, encoding='utf-8')
                        created_files.append(str(ref_path.relative_to(base_path.parent)))

        log.info(f"Skill '{clean_name}' erstellt unter {skill_dir}")

        return InitSkillResult(
            success=True,
            skill_name=clean_name,
            skill_path=skill_dir,
            created_files=created_files,
            error=None
        )

    except Exception as e:
        log.error(f"Fehler beim Erstellen des Skills: {e}")
        return InitSkillResult(
            success=False,
            skill_name=clean_name,
            skill_path=skill_dir,
            created_files=created_files,
            error=str(e)
        )


@tool(
    name="init_skill_tool",
    description="Erstellt einen neuen Skill mit Template-Struktur (SKILL.md, scripts/, references/).",
    parameters=[
        P("name", "string", "Name des Skills (z.B. 'pdf-processor')", required=True),
        P("description", "string", "Beschreibung wann der Skill verwendet wird", required=False, default=None),
        P("resources", "array", "Liste von Ressourcen: scripts, references, assets", required=False, default=None),
        P("examples", "boolean", "Ob Beispiel-Dateien erstellt werden sollen", required=False, default=False),
        P("path", "string", "Basis-Verzeichnis", required=False, default="skills"),
    ],
    capabilities=["system", "skills"],
    category=C.SYSTEM
)
async def init_skill_tool(
    name: str,
    description: Optional[str] = None,
    resources: Optional[List[str]] = None,
    examples: bool = False,
    path: str = "skills"
) -> dict:
    """
    Erstellt einen neuen Skill mit Template.
    """
    try:
        result = init_skill(
            name=name,
            description=description,
            resources=resources,
            examples=examples,
            base_path=Path(path)
        )

        if result.success:
            # Auto-Reload: Skills neu laden damit neuer Skill sofort verfügbar ist
            try:
                from utils.skill_types import SkillRegistry
                from utils.skill_parser import find_all_skills

                new_skills = find_all_skills(Path("skills"))

                log.info(f"Auto-Reload: {len(new_skills)} Skills gefunden (inkl. neuem Skill)")

                reload_info = {
                    "skills_total": len(new_skills),
                    "new_skill": result.skill_name,
                    "available_skills": list(new_skills.keys())
                }
            except Exception as e:
                log.warning(f"Auto-Reload fehlgeschlagen (nicht kritisch): {e}")
                reload_info = {"warning": "Auto-reload failed", "error": str(e)}

            return {
                "success": True,
                "skill_name": result.skill_name,
                "skill_path": str(result.skill_path),
                "created_files": result.created_files,
                "auto_reload": reload_info,
                "next_steps": [
                    f"Edit {result.skill_path}/SKILL.md",
                    "Add your scripts to scripts/",
                    "Add references to references/",
                    f"Skill is now available: {result.skill_name}",
                    "Use via MetaAgent or direct call"
                ]
            }
        else:
            raise Exception(result.error or "Unbekannter Fehler")

    except Exception as e:
        log.error(f"init_skill_tool Fehler: {e}")
        raise Exception(f"Fehler beim Erstellen des Skills: {str(e)}")
