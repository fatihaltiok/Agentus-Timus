# memory/__init__.py
from .memory_system import (
    MemoryManager,
    memory_manager,
    get_memory_context,
    get_self_model_prompt,
    get_behavior_hooks,
    add_to_memory,
    remember,
    recall,
    end_session
)

__all__ = [
    "MemoryManager",
    "memory_manager", 
    "get_memory_context",
    "get_self_model_prompt",
    "get_behavior_hooks",
    "add_to_memory",
    "remember",
    "recall",
    "end_session"
]
