"""
Timus Skills - Modulares Skill-System.

Usage:
    from utils.skill_parser import parse_skill_md
    from utils.skill_types import SkillRegistry

    # Einzelner Skill
    skill = parse_skill_md(Path("skills/example-skill/SKILL.md"))

    # Alle Skills laden
    registry = SkillRegistry()
    registry.load_all_from_directory(Path("skills"))

Available Skills:
    - example-skill: Beispiel nach OpenClaw Standard
    - (weitere Skills hier registrieren)
"""

# Legacy Import (für Abwärtskompatibilität)
from .square import square

# Neue Skill-API
from utils.skill_types import Skill, SkillMetadata, SkillRegistry
from utils.skill_parser import parse_skill_md, validate_skill

__all__ = [
    # Legacy
    "square",
    # Neue API
    "Skill",
    "SkillMetadata",
    "SkillRegistry",
    "parse_skill_md",
    "validate_skill",
]