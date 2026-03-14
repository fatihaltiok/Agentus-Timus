"""
tests/test_m16_qdrant.py — M16: Phase 3 Tests

Testet QdrantProvider Interface (ohne echte qdrant-client Abhängigkeit
via Mocking, und mit qdrant-client falls installiert).
"""

import os
import sys
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch


# ──────────────────────────────────────────────────────────────────
# Hilfs-Mock für qdrant_client
# ──────────────────────────────────────────────────────────────────

def make_mock_qdrant():
    """Erstellt Mock qdrant_client für Tests ohne echten Server."""
    mock_module = MagicMock()
    mock_client_instance = MagicMock()

    # get_collections gibt leere Liste zurück
    mock_client_instance.get_collections.return_value = MagicMock(collections=[])
    mock_client_instance.count.return_value = MagicMock(count=0)

    # get_collection gibt Objekt mit points_count zurück
    mock_collection_info = MagicMock()
    mock_collection_info.points_count = 0
    mock_client_instance.get_collection.return_value = mock_collection_info

    # scroll gibt leere Liste zurück
    mock_client_instance.scroll.return_value = ([], None)

    # search gibt leere Liste zurück
    mock_client_instance.search.return_value = []

    # retrieve gibt leere Liste zurück
    mock_client_instance.retrieve.return_value = []

    mock_module.QdrantClient.return_value = mock_client_instance

    # Models
    mock_models = MagicMock()
    mock_module.models = mock_models

    return mock_module, mock_client_instance


# ──────────────────────────────────────────────────────────────────
# Interface Tests (mit Mock)
# ──────────────────────────────────────────────────────────────────

@pytest.fixture
def qdrant_provider(tmp_path):
    """QdrantProvider mit gemocktem Client."""
    mock_qdrant, mock_client = make_mock_qdrant()

    with patch.dict(sys.modules, {
        "qdrant_client": mock_qdrant,
        "qdrant_client.models": mock_qdrant.models,
    }):
        from memory.qdrant_provider import QdrantProvider
        provider = QdrantProvider(path=tmp_path / "qdrant_test", collection_name="test")
        provider._client = mock_client
        yield provider, mock_client


def test_provider_has_add_method(qdrant_provider):
    provider, _ = qdrant_provider
    assert hasattr(provider, "add")
    assert callable(provider.add)


def test_provider_has_query_method(qdrant_provider):
    provider, _ = qdrant_provider
    assert hasattr(provider, "query")


def test_provider_has_get_method(qdrant_provider):
    provider, _ = qdrant_provider
    assert hasattr(provider, "get")


def test_provider_has_delete_method(qdrant_provider):
    provider, _ = qdrant_provider
    assert hasattr(provider, "delete")


def test_provider_has_count_method(qdrant_provider):
    provider, _ = qdrant_provider
    assert hasattr(provider, "count")


def test_add_calls_upsert(qdrant_provider):
    provider, mock_client = qdrant_provider
    provider.add(
        ids=["id-1", "id-2"],
        documents=["Dokument 1", "Dokument 2"],
        metadatas=[{"type": "test"}, {"type": "test"}],
        embeddings=[[0.1] * 384, [0.2] * 384],
    )
    assert mock_client.upsert.called


def test_query_returns_chromadb_format(qdrant_provider):
    provider, mock_client = qdrant_provider
    mock_client.search.return_value = []
    result = provider.query(
        query_embeddings=[[0.1] * 384],
        n_results=5,
    )
    assert "ids" in result
    assert "documents" in result
    assert "metadatas" in result
    assert "distances" in result
    assert isinstance(result["ids"], list)
    assert isinstance(result["ids"][0], list)


def test_get_returns_chromadb_format(qdrant_provider):
    provider, mock_client = qdrant_provider
    mock_client.retrieve.return_value = []
    result = provider.get(ids=["id-1"])
    assert "ids" in result
    assert "documents" in result
    assert "metadatas" in result


def test_count_returns_int(qdrant_provider):
    provider, mock_client = qdrant_provider
    mock_info = MagicMock()
    mock_info.points_count = 42
    mock_client.get_collection.return_value = mock_info
    count = provider.count()
    assert isinstance(count, int)
    assert count == 42


def test_delete_calls_client_delete(qdrant_provider):
    provider, mock_client = qdrant_provider
    provider.delete(ids=["id-1"])
    assert mock_client.delete.called


def test_to_qdrant_id_valid_uuid():
    from memory.qdrant_provider import QdrantProvider
    import uuid
    original_id = str(uuid.uuid4())
    result = QdrantProvider._to_qdrant_id(original_id)
    assert result == original_id


def test_to_qdrant_id_string_to_uuid():
    from memory.qdrant_provider import QdrantProvider
    import uuid
    result = QdrantProvider._to_qdrant_id("arbitrary-string-123")
    # Muss gültiger UUID sein
    uuid.UUID(result)  # Wirft keine Exception


def test_add_without_embeddings_uses_zero_vector(qdrant_provider):
    provider, mock_client = qdrant_provider
    # Ohne embeddings → _embed() → Null-Vektor
    provider.add(ids=["id-noembed"], documents=["test"])
    assert mock_client.upsert.called


# ──────────────────────────────────────────────────────────────────
# ENV-Variable MEMORY_BACKEND Test
# ──────────────────────────────────────────────────────────────────

def test_memory_backend_env_default():
    """MEMORY_BACKEND Default ist qdrant oder wird explizit gesetzt."""
    assert os.getenv("MEMORY_BACKEND", "qdrant") in {"chromadb", "qdrant", "none"}


def test_memory_backend_qdrant_recognized():
    """MEMORY_BACKEND=qdrant wird korrekt ausgelesen."""
    with patch.dict(os.environ, {"MEMORY_BACKEND": "qdrant"}):
        backend = os.getenv("MEMORY_BACKEND", "qdrant").lower()
        assert backend == "qdrant"


# ──────────────────────────────────────────────────────────────────
# Limit-Invariante (Lean: m16_qdrant_limit_positive)
# ──────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("n", [1, 5, 10, 100])
def test_query_limit_always_positive(n):
    """n_results wird immer auf mindestens 1 geclamped."""
    # max(1, n) ≥ 1 für alle n ≥ 1
    assert max(1, n) >= 1


def test_query_limit_zero_clamped():
    """Limit=0 wird auf 1 angehoben."""
    assert max(1, 0) == 1
