from __future__ import annotations

import tools.shared_context as shared_context


class _FakeUnavailableQdrant:
    def __init__(self, *args, **kwargs):
        self._client = None

    def is_available(self) -> bool:
        return False


class _FakeChromaCollection:
    name = "fake_chroma"

    def upsert(self, *args, **kwargs):
        return None

    def query(self, *args, **kwargs):
        return {"ids": [[]], "documents": [[]], "metadatas": [[]], "distances": [[]]}

    def get(self, *args, **kwargs):
        return {"ids": [], "documents": [], "metadatas": []}

    def count(self) -> int:
        return 0


def test_memory_manager_does_not_fallback_from_qdrant_to_shared_chroma(monkeypatch):
    from memory import qdrant_provider
    from memory.memory_system import MemoryManager

    monkeypatch.setenv("MEMORY_BACKEND", "qdrant")
    monkeypatch.setattr(qdrant_provider, "QdrantProvider", _FakeUnavailableQdrant)
    monkeypatch.setattr(shared_context, "memory_collection", _FakeChromaCollection(), raising=False)
    monkeypatch.setattr(MemoryManager, "_load_self_model_state", lambda self: None)

    manager = MemoryManager()

    assert manager.semantic_backend_requested == "qdrant"
    assert manager.semantic_backend_active == "none"
    assert manager.semantic_backend_reason == "qdrant_unavailable"
    assert manager.semantic_store is None


def test_memory_manager_uses_shared_chroma_only_when_explicit(monkeypatch):
    from memory.memory_system import MemoryManager

    monkeypatch.setenv("MEMORY_BACKEND", "chromadb")
    monkeypatch.setattr(shared_context, "memory_collection", _FakeChromaCollection(), raising=False)
    monkeypatch.setattr(MemoryManager, "_load_self_model_state", lambda self: None)

    manager = MemoryManager()

    assert manager.semantic_backend_requested == "chromadb"
    assert manager.semantic_backend_active == "chromadb"
    assert manager.semantic_backend_reason == "chromadb_ready_shared_context"
    assert manager.semantic_store is not None
    assert manager.semantic_store.is_available() is True


def test_working_memory_stats_expose_backend_status(monkeypatch):
    from memory.memory_system import MemoryManager

    monkeypatch.setenv("MEMORY_BACKEND", "none")
    monkeypatch.setattr(shared_context, "memory_collection", None, raising=False)
    monkeypatch.setattr(MemoryManager, "_load_self_model_state", lambda self: None)

    manager = MemoryManager()
    manager.build_working_memory_context("grafikkarten", max_chars=800, max_related=2, max_recent_events=2)
    stats = manager.get_last_working_memory_stats()

    assert stats["semantic_backend_requested"] == "none"
    assert stats["semantic_backend_active"] == "none"
    assert stats["semantic_backend_reason"] == "disabled_by_config"


def test_working_memory_context_respects_allowed_sections_and_classes(monkeypatch):
    from memory.memory_system import MemoryManager

    monkeypatch.setenv("MEMORY_BACKEND", "none")
    monkeypatch.setattr(shared_context, "memory_collection", None, raising=False)
    monkeypatch.setattr(MemoryManager, "_load_self_model_state", lambda self: None)

    manager = MemoryManager()
    manager.log_interaction_event(
        user_input="ich ueberlege noch meinen tagesplan",
        assistant_response="Wir koennen zuerst Prioritaeten sortieren.",
        agent_name="meta",
        status="completed",
        metadata={"source": "test"},
    )
    monkeypatch.setattr(
        manager,
        "find_related_memories",
        lambda query, n_results=5, category_filter=None: [
            {
                "content": "Twilio zuerst behandeln.",
                "category": "user_profile",
                "importance": 0.9,
                "relevance": 0.91,
                "source": "semantic",
            },
            {
                "content": "PDF-Quelle mit Berichtsauszug.",
                "category": "document_memory",
                "importance": 0.7,
                "relevance": 0.83,
                "source": "semantic",
            },
        ],
    )
    monkeypatch.setattr(manager, "get_self_model_prompt", lambda: "Der Nutzer mag knappe Antworten.")
    monkeypatch.setattr(manager, "get_behavior_hooks", lambda: ["Bleibe knapp"])

    context = manager.build_working_memory_context(
        "plane meinen tag",
        max_chars=900,
        max_related=3,
        max_recent_events=3,
        allowed_sections=("KURZZEITKONTEXT", "LANGZEITKONTEXT"),
        allowed_context_classes=("conversation_state",),
        query_mode="objective_only",
    )
    stats = manager.get_last_working_memory_stats()

    assert "KURZZEITKONTEXT" in context
    assert "LANGZEITKONTEXT" not in context
    assert "STABILER_KONTEXT" not in context
    assert stats["allowed_sections"] == ["KURZZEITKONTEXT", "LANGZEITKONTEXT"]
    assert stats["allowed_context_classes"] == ["conversation_state"]
    assert stats["query_mode"] == "objective_only"
    assert stats["filtered_related_memories"] >= 2
