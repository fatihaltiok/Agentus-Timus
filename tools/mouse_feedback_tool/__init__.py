# tools/mouse_feedback_tool/__init__.py
"""
Mouse Feedback Tool - Echtzeitige Hand-Auge-Koordination für Timus.

Exportiert:
- MouseFeedbackEngine: Hauptklasse für Maus-Feedback
- CursorType: Enum für Cursor-Typen
- CursorInfo: Dataclass für Cursor-Informationen

RPC Methoden (automatisch registriert):
- move_with_feedback(x, y)
- search_for_element(x, y, radius)
- get_cursor_at_position(x, y)
- click_with_verification(x, y)
- find_text_field_nearby(x, y, radius)
- get_mouse_position()
"""

from .tool import (
    MouseFeedbackEngine,
    CursorType,
    CursorInfo,
    MoveResult,
    get_engine,
    # RPC Methods
    move_with_feedback,
    search_for_element,
    get_cursor_at_position,
    click_with_verification,
    find_text_field_nearby,
    get_mouse_position,
)

__all__ = [
    "MouseFeedbackEngine",
    "CursorType", 
    "CursorInfo",
    "MoveResult",
    "get_engine",
    "move_with_feedback",
    "search_for_element",
    "get_cursor_at_position",
    "click_with_verification",
    "find_text_field_nearby",
    "get_mouse_position",
]

__version__ = "1.0.0"
