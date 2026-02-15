# tools/skill_manager_tool/reload_tool.py
"""
Reload Skills Tool - Lädt Skills neu (nach Erstellung).

Usage: reload_skills_tool()
"""

import logging
from pathlib import Path

from tools.tool_registry_v2 import tool, ToolParameter as P, ToolCategory as C

log = logging.getLogger(__name__)


@tool(
    name="reload_skills_tool",
    description="Laedt alle Skills neu (nach Erstellung neuer Skills).",
    parameters=[],
    capabilities=["system", "skills"],
    category=C.SYSTEM
)
async def reload_skills_tool() -> dict:
    """
    Lädt alle Skills neu (nach Erstellung neuer Skills).

    Dieses Tool sollte aufgerufen werden nachdem ein neuer Skill
    erstellt wurde, damit er sofort verfügbar ist.
    """
    try:
        from utils.skill_types import SkillRegistry
        from utils.skill_parser import find_all_skills

        # Alle Skills finden
        all_skills = find_all_skills(Path("skills"))

        if not all_skills:
            return {
                "success": True,
                "skills_count": 0,
                "skills": [],
                "message": "No skills found in skills/ directory"
            }

        # Neue Registry erstellen
        registry = SkillRegistry()
        registry.load_all_from_directory(Path("skills"))

        # Skills auflisten mit Info
        skills_info = []
        for name in registry.list_all():
            skill = registry.get(name)
            if skill:
                skills_info.append({
                    "name": name,
                    "description": skill.description[:80] + "..." if len(skill.description) > 80 else skill.description,
                    "scripts_count": len(skill.get_scripts()),
                    "references_count": len(skill.get_references())
                })

        log.info(f"Skills neu geladen: {len(registry.skills)} Skills verfügbar")

        return {
            "success": True,
            "skills_count": len(registry.skills),
            "skills": skills_info,
            "message": f"Successfully reloaded {len(registry.skills)} skills"
        }

    except Exception as e:
        log.error(f"Fehler beim Reload: {e}")
        raise Exception(f"Failed to reload skills: {str(e)}")
