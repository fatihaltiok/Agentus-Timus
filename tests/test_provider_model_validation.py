from types import SimpleNamespace

import pytest

from agent import providers as providers_mod
from agent.providers import (
    AgentModelConfig,
    ModelConfigurationError,
    ModelProvider,
    MultiProviderClient,
)


class _FakeModel:
    def __init__(self, model_id: str):
        self.id = model_id


class _FakeModelsApi:
    def __init__(self, model_ids):
        self._model_ids = list(model_ids)
        self.calls = 0

    def list(self):
        self.calls += 1
        return SimpleNamespace(data=[_FakeModel(mid) for mid in self._model_ids])


class _FakeClient:
    def __init__(self, model_ids):
        self.models = _FakeModelsApi(model_ids)


@pytest.fixture(autouse=True)
def _reset_provider_singleton(monkeypatch):
    monkeypatch.setenv("TIMUS_VALIDATE_CONFIGURED_MODELS", "true")
    providers_mod._provider_client = None
    yield
    providers_mod._provider_client = None


def test_validate_model_or_raise_accepts_known_openrouter_model():
    client = MultiProviderClient()
    client._api_keys[ModelProvider.OPENROUTER] = "test-key"
    fake = _FakeClient(["google/gemini-3.1-flash-lite-preview"])
    client._clients[ModelProvider.OPENROUTER] = fake

    client.validate_model_or_raise(
        ModelProvider.OPENROUTER,
        "google/gemini-3.1-flash-lite-preview",
        agent_type="communication",
    )

    assert fake.models.calls == 1


def test_validate_model_or_raise_caches_successful_lookup():
    client = MultiProviderClient()
    client._api_keys[ModelProvider.OPENROUTER] = "test-key"
    fake = _FakeClient(["amazon/nova-2-lite-v1"])
    client._clients[ModelProvider.OPENROUTER] = fake

    client.validate_model_or_raise(
        ModelProvider.OPENROUTER,
        "amazon/nova-2-lite-v1",
        agent_type="document",
    )
    client.validate_model_or_raise(
        ModelProvider.OPENROUTER,
        "amazon/nova-2-lite-v1",
        agent_type="document",
    )

    assert fake.models.calls == 1


def test_validate_model_or_raise_rejects_unknown_model():
    client = MultiProviderClient()
    client._api_keys[ModelProvider.OPENROUTER] = "test-key"
    fake = _FakeClient(["google/gemini-3.1-flash-lite-preview"])
    client._clients[ModelProvider.OPENROUTER] = fake

    with pytest.raises(ModelConfigurationError) as exc:
        client.validate_model_or_raise(
            ModelProvider.OPENROUTER,
            "does/not-exist",
            agent_type="communication",
        )

    msg = str(exc.value)
    assert "does/not-exist" in msg
    assert "communication" in msg
    assert "google/gemini-3.1-flash-lite-preview" in msg


def test_agent_model_config_fails_fast_for_invalid_model(monkeypatch):
    fake_client = MultiProviderClient()
    fake_client._api_keys[ModelProvider.OPENROUTER] = "test-key"
    fake_client._clients[ModelProvider.OPENROUTER] = _FakeClient(["valid/model"])
    monkeypatch.setattr(providers_mod, "_provider_client", fake_client)
    monkeypatch.setenv("DOCUMENT_MODEL", "invalid/model")
    monkeypatch.setenv("DOCUMENT_MODEL_PROVIDER", "openrouter")

    with pytest.raises(ModelConfigurationError) as exc:
        AgentModelConfig.get_model_and_provider("document")

    assert "invalid/model" in str(exc.value)
    assert "document" in str(exc.value)
