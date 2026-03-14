"""Lazy exports for the markdown store package."""

from importlib import import_module

__all__ = [
    "MarkdownStore",
    "UserProfile",
    "SoulProfile",
    "MemoryEntry",
    "markdown_store",
]


def __getattr__(name: str):
    if name in __all__:
        module = import_module(".store", __name__)
        return getattr(module, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(__all__))
