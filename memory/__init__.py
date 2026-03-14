"""Lazy exports for the memory package.

This keeps the public surface stable while avoiding heavyweight side effects
during import-time tooling such as CrossHair.
"""

from importlib import import_module

_MEMORY_EXPORTS = {
    "MemoryManager",
    "memory_manager",
    "get_memory_context",
    "get_self_model_prompt",
    "get_behavior_hooks",
    "add_to_memory",
    "remember",
    "recall",
    "end_session",
    "find_related_memories",
    "get_enhanced_context",
    "sync_memory_to_markdown",
    "sync_markdown_to_memory",
    "store_memory_item",
    "MemoryItem",
    "SemanticSearchResult",
}

_REFLECTION_EXPORTS = {
    "ReflectionEngine",
    "ReflectionResult",
    "get_reflection_engine",
    "init_reflection_engine",
    "reflect_on_task",
}

__all__ = sorted(_MEMORY_EXPORTS | _REFLECTION_EXPORTS)


def __getattr__(name: str):
    if name in _MEMORY_EXPORTS:
        module = import_module(".memory_system", __name__)
        return getattr(module, name)
    if name in _REFLECTION_EXPORTS:
        module = import_module(".reflection_engine", __name__)
        return getattr(module, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(__all__))
