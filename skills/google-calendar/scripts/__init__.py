from __future__ import annotations
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

"""Exports for the google-calendar script helpers.

This module supports both package-style imports and direct script loading.
"""

try:
    from .calendar_client import (
        create_event,
        delete_event,
        get_status,
        list_events,
        update_event,
    )
except ImportError:
    from calendar_client import (  # type: ignore[no-redef]
        create_event,
        delete_event,
        get_status,
        list_events,
        update_event,
    )

__all__ = [
    "create_event",
    "delete_event",
    "get_status",
    "list_events",
    "update_event",
]
