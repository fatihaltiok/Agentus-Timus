import importlib


def test_conversation_qdrant_uses_server_mode(monkeypatch):
    monkeypatch.setenv("MEMORY_BACKEND", "qdrant")
    monkeypatch.setenv("QDRANT_MODE", "server")
    monkeypatch.setenv("QDRANT_URL", "http://127.0.0.1:6333")
    monkeypatch.setenv("TIMUS_CHAT_QDRANT_ENABLED", "true")
    monkeypatch.setenv("TIMUS_CHAT_QDRANT_COLLECTION", "timus_conversations")

    import server.conversation_qdrant as module
    importlib.reload(module)

    seen = {}

    class FakeProvider:
        def __init__(self, **kwargs):
            seen.update(kwargs)
            self.mode = kwargs.get("mode")
            self.endpoint = "http://127.0.0.1:6333"
            self.last_error = ""

        def is_available(self):
            return True

        def _get_embedding_fn(self):
            return object()

    monkeypatch.setattr(module, "QdrantProvider", FakeProvider)
    module._STORE = None
    module._STORE_FAILED = False

    store = module._get_store()

    assert store is not None
    assert seen["mode"] == "server"
    assert seen["collection_name"] == "timus_conversations"
    assert "path" not in seen


def test_conversation_qdrant_embedded_mode_uses_path(monkeypatch, tmp_path):
    monkeypatch.setenv("MEMORY_BACKEND", "qdrant")
    monkeypatch.setenv("QDRANT_MODE", "embedded")
    monkeypatch.setenv("TIMUS_CHAT_QDRANT_ENABLED", "true")
    monkeypatch.setenv("TIMUS_CHAT_QDRANT_COLLECTION", "timus_conversations")
    monkeypatch.setenv("TIMUS_CHAT_QDRANT_PATH", str(tmp_path / "chat_store"))

    import server.conversation_qdrant as module
    importlib.reload(module)

    seen = {}

    class FakeProvider:
        def __init__(self, **kwargs):
            seen.update(kwargs)
            self.mode = kwargs.get("mode")
            self.endpoint = str(kwargs.get("path"))
            self.last_error = ""

        def is_available(self):
            return True

        def _get_embedding_fn(self):
            return object()

    monkeypatch.setattr(module, "QdrantProvider", FakeProvider)
    module._STORE = None
    module._STORE_FAILED = False

    store = module._get_store()

    assert store is not None
    assert seen["mode"] == "embedded"
    assert seen["collection_name"] == "timus_conversations"
    assert str(seen["path"]).endswith("chat_store")
