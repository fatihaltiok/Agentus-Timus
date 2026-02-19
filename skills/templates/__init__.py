# skills/templates/__init__.py
"""
Skill Templates Module.
"""

from .ui_patterns import (
    get_template,
    find_matching_templates,
    get_all_templates,
    get_template_as_context,
    TEMPLATES
)

__all__ = [
    "get_template",
    "find_matching_templates", 
    "get_all_templates",
    "get_template_as_context",
    "TEMPLATES"
]
