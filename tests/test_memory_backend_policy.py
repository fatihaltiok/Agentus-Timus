from __future__ import annotations

from memory.semantic_backend_policy import (
    normalize_semantic_memory_backend,
    resolve_semantic_memory_backend,
)


def test_normalize_semantic_memory_backend_defaults_to_qdrant():
    assert normalize_semantic_memory_backend("") == "qdrant"
    assert normalize_semantic_memory_backend("auto") == "qdrant"
    assert normalize_semantic_memory_backend("weird-backend") == "qdrant"


def test_normalize_semantic_memory_backend_supports_none_aliases():
    assert normalize_semantic_memory_backend("none") == "none"
    assert normalize_semantic_memory_backend("off") == "none"
    assert normalize_semantic_memory_backend("fts5") == "none"


def test_resolve_semantic_memory_backend_never_falls_back_to_chromadb():
    assert resolve_semantic_memory_backend("qdrant", qdrant_available=False, chromadb_available=True) == (
        "none",
        "qdrant_unavailable",
    )


def test_resolve_semantic_memory_backend_respects_explicit_chromadb():
    assert resolve_semantic_memory_backend("chromadb", qdrant_available=True, chromadb_available=True) == (
        "chromadb",
        "chromadb_ready",
    )
