"""Pure backend selection helpers for semantic memory."""

from __future__ import annotations


def normalize_semantic_memory_backend(raw_backend: str | None) -> str:
    raw = str(raw_backend or "").strip().lower()
    if raw in {"", "auto", "default"}:
        return "qdrant"
    if raw in {"qdrant", "vector", "semantic"}:
        return "qdrant"
    if raw in {"chromadb", "chroma", "chroma_db"}:
        return "chromadb"
    if raw in {"none", "disabled", "off", "false", "fts5", "sqlite", "keyword_only"}:
        return "none"
    return "qdrant"


def resolve_semantic_memory_backend(
    requested_backend: str | None,
    *,
    qdrant_available: bool,
    chromadb_available: bool,
) -> tuple[str, str]:
    normalized = normalize_semantic_memory_backend(requested_backend)
    if normalized == "none":
        return ("none", "disabled_by_config")
    if normalized == "qdrant":
        if qdrant_available:
            return ("qdrant", "qdrant_ready")
        return ("none", "qdrant_unavailable")
    if chromadb_available:
        return ("chromadb", "chromadb_ready")
    return ("none", "chromadb_unavailable")
