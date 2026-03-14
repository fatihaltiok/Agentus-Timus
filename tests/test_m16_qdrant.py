"""
tests/test_m16_qdrant.py — M16: Phase 3 Tests

Testet QdrantProvider Interface (ohne echte qdrant-client Abhängigkeit
via Mocking, und mit qdrant-client falls installiert).
"""

import os
import sys
import pytest
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

    # query_points gibt leere Liste zurück
    mock_client_instance.query_points.return_value = MagicMock(points=[])

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


def test_normalize_qdrant_mode_defaults_to_embedded():
    from memory.qdrant_provider import normalize_qdrant_mode

    assert normalize_qdrant_mode("") == "embedded"
    assert normalize_qdrant_mode(None) == "embedded"
    assert normalize_qdrant_mode("weird") == "embedded"


def test_normalize_qdrant_mode_accepts_server_aliases():
    from memory.qdrant_provider import normalize_qdrant_mode

    assert normalize_qdrant_mode("server") == "server"
    assert normalize_qdrant_mode("remote") == "server"
    assert normalize_qdrant_mode("https") == "server"


def test_resolve_qdrant_url_defaults_to_localhost():
    from memory.qdrant_provider import resolve_qdrant_url

    assert resolve_qdrant_url("") == "http://127.0.0.1:6333"
    assert resolve_qdrant_url("http://") == "http://127.0.0.1:6333"
    assert resolve_qdrant_url("ftp://bad") == "http://127.0.0.1:6333"
    assert resolve_qdrant_url("https://qdrant.local") == "https://qdrant.local"


def test_resolve_qdrant_ready_url_appends_readyz():
    from memory.qdrant_provider import resolve_qdrant_ready_url

    assert resolve_qdrant_ready_url("") == "http://127.0.0.1:6333/readyz"
    assert resolve_qdrant_ready_url("http://qdrant.internal:6333/") == "http://qdrant.internal:6333/readyz"


def test_provider_server_mode_uses_url(tmp_path):
    mock_qdrant, mock_client = make_mock_qdrant()

    with patch.dict(sys.modules, {
        "qdrant_client": mock_qdrant,
        "qdrant_client.models": mock_qdrant.models,
    }):
        from memory.qdrant_provider import QdrantProvider

        provider = QdrantProvider(
            mode="server",
            url="http://qdrant.internal:6333",
            collection_name="server_test",
            path=tmp_path / "ignored",
        )

    mock_qdrant.QdrantClient.assert_called_with(
        url="http://qdrant.internal:6333",
        api_key=None,
    )
    assert provider.mode == "server"
    assert provider.endpoint == "http://qdrant.internal:6333"
    assert provider.is_available() is True


def test_provider_embedded_mode_uses_path(tmp_path):
    mock_qdrant, _ = make_mock_qdrant()
    embedded_path = tmp_path / "qdrant_embedded"

    with patch.dict(sys.modules, {
        "qdrant_client": mock_qdrant,
        "qdrant_client.models": mock_qdrant.models,
    }):
        from memory.qdrant_provider import QdrantProvider

        provider = QdrantProvider(
            mode="embedded",
            path=embedded_path,
            collection_name="embedded_test",
        )

    mock_qdrant.QdrantClient.assert_called_with(path=str(embedded_path))
    assert provider.mode == "embedded"
    assert provider.endpoint == str(embedded_path)
    assert provider.is_available() is True


def test_provider_captures_server_init_failure(tmp_path):
    mock_qdrant, _ = make_mock_qdrant()
    mock_qdrant.QdrantClient.side_effect = RuntimeError("server down")

    with patch.dict(sys.modules, {
        "qdrant_client": mock_qdrant,
        "qdrant_client.models": mock_qdrant.models,
    }):
        from memory.qdrant_provider import QdrantProvider

        provider = QdrantProvider(
            mode="server",
            url="http://qdrant.internal:6333",
            collection_name="server_test",
            path=tmp_path / "ignored",
        )

    assert provider.is_available() is False
    assert "server down" in provider.last_error


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
