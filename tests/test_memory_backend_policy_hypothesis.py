from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from tests.test_memory_backend_policy_contracts import (
    _contract_normalize_semantic_memory_backend,
    _contract_resolve_semantic_memory_backend,
)


@given(st.text(max_size=40))
@settings(max_examples=80)
def test_hypothesis_normalize_semantic_memory_backend_is_bounded(raw_backend: str):
    result = _contract_normalize_semantic_memory_backend(raw_backend)
    assert result in {"qdrant", "chromadb", "none"}


@given(st.text(max_size=40), st.booleans(), st.booleans())
@settings(max_examples=100)
def test_hypothesis_resolve_semantic_memory_backend_has_known_states(
    requested_backend: str,
    qdrant_available: bool,
    chromadb_available: bool,
):
    backend, reason = _contract_resolve_semantic_memory_backend(
        requested_backend,
        qdrant_available,
        chromadb_available,
    )
    assert backend in {"qdrant", "chromadb", "none"}
    assert isinstance(reason, str) and reason
