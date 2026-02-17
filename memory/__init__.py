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
    end_session,
    # NEW v2.0: Hybrid Search
    find_related_memories,
    get_enhanced_context,
    sync_memory_to_markdown,
    sync_markdown_to_memory,
    store_memory_item,
    MemoryItem,
    SemanticSearchResult
)

# Reflection Engine
from .reflection_engine import (
    ReflectionEngine,
    ReflectionResult,
    get_reflection_engine,
    init_reflection_engine,
    reflect_on_task
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
    "end_session",
    # NEW v2.0
    "find_related_memories",
    "get_enhanced_context",
    "sync_memory_to_markdown",
    "sync_markdown_to_memory",
    "store_memory_item",
    "MemoryItem",
    "SemanticSearchResult",
    # Reflection Engine
    "ReflectionEngine",
    "ReflectionResult",
    "get_reflection_engine",
    "init_reflection_engine",
    "reflect_on_task"
]
