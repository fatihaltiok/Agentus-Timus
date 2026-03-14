"""CrossHair contracts for semantic memory backend resolution."""

from __future__ import annotations

import deal

from memory.semantic_backend_policy import (
    normalize_semantic_memory_backend,
    resolve_semantic_memory_backend,
)


@deal.post(lambda r: r in {"qdrant", "chromadb", "none"})
def _contract_normalize_semantic_memory_backend(raw_backend: str) -> str:
    return normalize_semantic_memory_backend(raw_backend)


@deal.post(lambda r: r[0] in {"qdrant", "chromadb", "none"})
@deal.post(lambda r: r[0] != "chromadb" or "chromadb" in r[1])
@deal.post(lambda r: r[0] != "qdrant" or "qdrant" in r[1])
def _contract_resolve_semantic_memory_backend(
    requested_backend: str,
    qdrant_available: bool,
    chromadb_available: bool,
) -> tuple[str, str]:
    return resolve_semantic_memory_backend(
        requested_backend,
        qdrant_available=qdrant_available,
        chromadb_available=chromadb_available,
    )
