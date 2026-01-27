# config/__init__.py
"""
Timus Configuration Module

Enthält:
- personality_loader: Dynamische Persönlichkeits-Verwaltung
"""

from .personality_loader import (
    get_system_prompt_prefix,
    get_greeting,
    get_reaction,
    set_user_name,
    get_personality_info,
    reload_personality,
)

__all__ = [
    "get_system_prompt_prefix",
    "get_greeting", 
    "get_reaction",
    "set_user_name",
    "get_personality_info",
    "reload_personality",
]
