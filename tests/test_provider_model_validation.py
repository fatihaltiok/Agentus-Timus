from types import SimpleNamespace

import pytest

from agent import providers as providers_mod
from agent.providers import (
    AgentModelConfig,
    ModelConfigurationError,
    ModelProvider,
    MultiProviderClient,
    resolve_model_provider_env,
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
    client._api_keys[ModelProvider.OPENAI] = "test-key"
    fake = _FakeClient(["gpt-5.4-mini"])
    client._clients[ModelProvider.OPENAI] = fake

    client.validate_model_or_raise(
        ModelProvider.OPENAI,
        "gpt-5.4-mini",
        agent_type="communication",
    )

    assert fake.models.calls == 1


def test_validate_model_or_raise_accepts_known_zai_model():
    client = MultiProviderClient()
    client._api_keys[ModelProvider.ZAI] = "test-key"
    fake = _FakeClient(["glm-5"])
    client._clients[ModelProvider.ZAI] = fake

    client.validate_model_or_raise(
        ModelProvider.ZAI,
        "glm-5",
        agent_type="dispatcher",
    )

    assert fake.models.calls == 1


def test_validate_model_or_raise_caches_successful_lookup():
    client = MultiProviderClient()
    client._api_keys[ModelProvider.OPENAI] = "test-key"
    fake = _FakeClient(["gpt-5.4-mini"])
    client._clients[ModelProvider.OPENAI] = fake

    client.validate_model_or_raise(
        ModelProvider.OPENAI,
        "gpt-5.4-mini",
        agent_type="document",
    )
    client.validate_model_or_raise(
        ModelProvider.OPENAI,
        "gpt-5.4-mini",
        agent_type="document",
    )

    assert fake.models.calls == 1


def test_validate_model_or_raise_rejects_unknown_model():
    client = MultiProviderClient()
    client._api_keys[ModelProvider.OPENAI] = "test-key"
    fake = _FakeClient(["gpt-5.4-mini"])
    client._clients[ModelProvider.OPENAI] = fake

    with pytest.raises(ModelConfigurationError) as exc:
        client.validate_model_or_raise(
            ModelProvider.OPENAI,
            "does/not-exist",
            agent_type="communication",
        )

    msg = str(exc.value)
    assert "does/not-exist" in msg
    assert "communication" in msg
    assert "gpt-5.4-mini" in msg


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


def test_resolve_model_provider_env_uses_explicit_provider(monkeypatch):
    monkeypatch.setenv("REASONING_MODEL", "glm-5")
    monkeypatch.setenv("REASONING_MODEL_PROVIDER", "zai")

    model, provider = resolve_model_provider_env(
        model_env="REASONING_MODEL",
        provider_env="REASONING_MODEL_PROVIDER",
        fallback_model="qwen/qwq-32b",
        fallback_provider=ModelProvider.OPENROUTER,
    )

    assert model == "glm-5"
    assert provider == ModelProvider.ZAI


def test_agent_model_config_exposes_deep_research_fallback(monkeypatch):
    fake_client = MultiProviderClient()
    fake_client._api_keys[ModelProvider.OPENROUTER] = "test-key"
    fake_client._clients[ModelProvider.OPENROUTER] = _FakeClient(["deepseek/deepseek-v3.2"])
    monkeypatch.setattr(providers_mod, "_provider_client", fake_client)
    monkeypatch.delenv("RESEARCH_FALLBACK_MODEL", raising=False)
    monkeypatch.delenv("RESEARCH_FALLBACK_PROVIDER", raising=False)

    model, provider = AgentModelConfig.get_fallback_model_and_provider("deep_research")

    assert model == "deepseek/deepseek-v3.2"
    assert provider == ModelProvider.OPENROUTER


def test_agent_model_config_respects_explicit_deep_research_fallback_env(monkeypatch):
    fake_client = MultiProviderClient()
    fake_client._api_keys[ModelProvider.OPENAI] = "test-key"
    fake_client._clients[ModelProvider.OPENAI] = _FakeClient(["gpt-5-mini"])
    monkeypatch.setattr(providers_mod, "_provider_client", fake_client)
    monkeypatch.setenv("RESEARCH_FALLBACK_MODEL", "gpt-5-mini")
    monkeypatch.setenv("RESEARCH_FALLBACK_PROVIDER", "openai")

    model, provider = AgentModelConfig.get_fallback_model_and_provider("deep_research")

    assert model == "gpt-5-mini"
    assert provider == ModelProvider.OPENAI


@pytest.mark.parametrize("agent_type", ["executor", "document", "communication"])
def test_agent_model_config_defaults_selected_agents_to_gpt_5_4_mini(monkeypatch, agent_type):
    fake_client = MultiProviderClient()
    fake_client._api_keys[ModelProvider.OPENAI] = "test-key"
    fake_client._clients[ModelProvider.OPENAI] = _FakeClient(["gpt-5.4-mini"])
    monkeypatch.setattr(providers_mod, "_provider_client", fake_client)

    monkeypatch.delenv("FAST_MODEL", raising=False)
    monkeypatch.delenv("FAST_MODEL_PROVIDER", raising=False)
    monkeypatch.delenv("DOCUMENT_MODEL", raising=False)
    monkeypatch.delenv("DOCUMENT_MODEL_PROVIDER", raising=False)
    monkeypatch.delenv("COMMUNICATION_MODEL", raising=False)
    monkeypatch.delenv("COMMUNICATION_MODEL_PROVIDER", raising=False)

    model, provider = AgentModelConfig.get_model_and_provider(agent_type)

    assert model == "gpt-5.4-mini"
    assert provider == ModelProvider.OPENAI


def test_multi_provider_client_accepts_gemini_api_key_alias(monkeypatch):
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.setenv("GEMINI_API_KEY", "gem-test-key")

    client = MultiProviderClient()

    assert client.get_api_key(ModelProvider.GOOGLE) == "gem-test-key"


class TestGoogleProviderOpenAICompat:
    """GP1-Fix: ModelProvider.GOOGLE muss über OpenAI-kompatible Branch laufen."""

    def test_google_native_base_url_is_v1beta(self):
        """get_base_url(GOOGLE) zeigt auf den nativen v1beta-Endpunkt — für den Dispatcher."""
        client = MultiProviderClient()
        url = client.get_base_url(ModelProvider.GOOGLE)
        assert url == "https://generativelanguage.googleapis.com/v1beta", (
            f"Nativer GOOGLE-Endpunkt muss .../v1beta sein, ist: {url}"
        )

    def test_google_openai_compat_url_matches_official_example(self):
        """get_openai_compat_base_url(GOOGLE) entspricht der offiziellen Google-Doku inkl. trailing slash."""
        client = MultiProviderClient()
        url = client.get_openai_compat_base_url(ModelProvider.GOOGLE)
        assert url == "https://generativelanguage.googleapis.com/v1beta/openai/", (
            f"OpenAI-Compat-URL stimmt nicht mit Google-Beispiel überein: {url}"
        )

    def test_google_dispatcher_url_not_broken_by_openai_compat(self):
        """Dispatcher baut .../v1beta/models/{model}:generateContent — nicht .../openai/models/..."""
        client = MultiProviderClient()
        native_url = client.get_base_url(ModelProvider.GOOGLE).rstrip("/")
        model = "gemini-3-flash-preview"
        dispatcher_url = f"{native_url}/models/{model}:generateContent"
        assert "/openai/" not in dispatcher_url, (
            f"Dispatcher-URL darf kein /openai/ enthalten: {dispatcher_url}"
        )
        assert dispatcher_url == (
            f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
        )

    def test_google_get_client_returns_openai_client(self, monkeypatch):
        """get_client(GOOGLE) darf nicht mehr None zurückgeben (alter _init_google-Pfad)."""
        from openai import OpenAI

        monkeypatch.setenv("GOOGLE_API_KEY", "fake-google-key")
        client = MultiProviderClient()
        result = client.get_client(ModelProvider.GOOGLE)
        assert result is not None, "get_client(GOOGLE) darf nicht None zurückgeben"
        assert isinstance(result, OpenAI), (
            f"get_client(GOOGLE) muss OpenAI-Client zurückgeben, ist: {type(result)}"
        )

    def test_google_not_in_else_branch(self):
        """ModelProvider.GOOGLE darf nicht mehr in der else-Branch landen (kein 'nicht unterstuetzt')."""
        openai_compat = {
            "openai", "zai", "deepseek", "inception", "nvidia", "openrouter", "google"
        }
        assert "google" in openai_compat, "GOOGLE fehlt in openai_compat_set"
        assert "google" != "anthropic", "GOOGLE ist kein Anthropic-Provider"

    def test_google_validate_skips_model_listing(self):
        """GOOGLE unterstützt kein Model-Listing → validate_model_or_raise überspringt den Check."""
        client = MultiProviderClient()
        client._api_keys[ModelProvider.GOOGLE] = "fake-key"

        # kein Fehler, kein Netzwerk-Call
        client.validate_model_or_raise(
            ModelProvider.GOOGLE,
            "gemini-3-flash-preview",
            agent_type="executor",
        )
        # Model landet im validated-Cache trotzdem
        assert (ModelProvider.GOOGLE, "gemini-3-flash-preview") in client._validated_models
