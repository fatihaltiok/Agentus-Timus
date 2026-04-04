from __future__ import annotations

from types import SimpleNamespace

import pytest

import main_dispatcher
from orchestration.feedback_engine import FeedbackEngine
from agent.providers import ModelProvider


class _FakeOpenAICompatClient:
    def __init__(self, content: str, *, reasoning_content: str = ""):
        self.calls = []
        self.chat = SimpleNamespace(
            completions=SimpleNamespace(create=self._create),
        )
        self._content = content
        self._reasoning_content = reasoning_content

    def _create(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(
                        content=self._content,
                        reasoning_content=self._reasoning_content,
                    ),
                )
            ]
        )


class _FakeAnthropicClient:
    def __init__(self, text: str):
        self.calls = []
        self._text = text
        self.messages = SimpleNamespace(create=self._create)

    def _create(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(content=[SimpleNamespace(text=self._text)])


class _FakeProviderClient:
    def __init__(self, *, compat_client=None, anthropic_client=None, google_key="g-test", google_base="https://google.example/v1beta"):
        self.compat_client = compat_client
        self.anthropic_client = anthropic_client
        self.google_key = google_key
        self.google_base = google_base
        self.validated = []

    def validate_model_or_raise(self, provider, model, *, agent_type=""):
        self.validated.append((provider, model, agent_type))

    def get_client(self, provider):
        if provider == ModelProvider.ANTHROPIC:
            return self.anthropic_client
        return self.compat_client

    def get_api_key(self, provider):
        if provider == ModelProvider.GOOGLE:
            return self.google_key
        if provider == ModelProvider.ANTHROPIC:
            return "anthropic-key"
        return "provider-key"

    def get_base_url(self, provider):
        if provider == ModelProvider.GOOGLE:
            return self.google_base
        return "https://provider.example/v1"


@pytest.fixture(autouse=True)
def _reset_dispatcher_env(monkeypatch):
    monkeypatch.delenv("DISPATCHER_MODEL_PROVIDER", raising=False)
    monkeypatch.delenv("DISPATCHER_MODEL", raising=False)


def test_normalize_dispatcher_provider_falls_back_to_openai():
    assert main_dispatcher._normalize_dispatcher_provider("openrouter") == ModelProvider.OPENROUTER
    assert main_dispatcher._normalize_dispatcher_provider("zai") == ModelProvider.ZAI
    assert main_dispatcher._normalize_dispatcher_provider("not-a-provider") == ModelProvider.OPENAI


def test_dispatcher_sync_call_is_inlined_under_pytest(monkeypatch):
    monkeypatch.setenv("PYTEST_CURRENT_TEST", "tests/test_dispatcher_provider_selection.py::test")

    assert main_dispatcher._should_inline_dispatcher_sync_call() is True


def test_extract_dispatcher_decision_handles_verbose_text():
    assert (
        main_dispatcher._extract_dispatcher_decision(
            "Analyse: allgemeine koordinationsaufgabe.\nFinale Entscheidung: meta"
        )
        == "meta"
    )


@pytest.mark.asyncio
async def test_call_dispatcher_llm_uses_openai_compatible_provider(monkeypatch):
    fake_client = _FakeOpenAICompatClient("meta")
    fake_provider_client = _FakeProviderClient(compat_client=fake_client)
    monkeypatch.setenv("DISPATCHER_MODEL_PROVIDER", "openrouter")
    monkeypatch.setenv("DISPATCHER_MODEL", "z-ai/glm-5")
    monkeypatch.setattr(main_dispatcher, "get_provider_client", lambda: fake_provider_client)

    result = await main_dispatcher._call_dispatcher_llm("komplexe allgemeine aufgabe")

    assert result == "meta"
    assert fake_provider_client.validated == [
        (ModelProvider.OPENROUTER, "z-ai/glm-5", "dispatcher")
    ]
    assert fake_client.calls
    assert fake_client.calls[0]["model"] == "z-ai/glm-5"
    assert fake_client.calls[0].get("max_completion_tokens", fake_client.calls[0].get("max_tokens")) == 20


@pytest.mark.asyncio
async def test_call_dispatcher_llm_uses_reasoning_content_fallback(monkeypatch):
    fake_client = _FakeOpenAICompatClient("", reasoning_content="<think>abwaegung</think>\nmeta")
    fake_provider_client = _FakeProviderClient(compat_client=fake_client)
    monkeypatch.setenv("DISPATCHER_MODEL_PROVIDER", "zai")
    monkeypatch.setenv("DISPATCHER_MODEL", "glm-5")
    monkeypatch.setattr(main_dispatcher, "get_provider_client", lambda: fake_provider_client)

    result = await main_dispatcher._call_dispatcher_llm("was kannst du alles")

    assert result == "abwaegung\nmeta"
    assert fake_provider_client.validated == [
        (ModelProvider.ZAI, "glm-5", "dispatcher")
    ]


@pytest.mark.asyncio
async def test_call_dispatcher_llm_uses_anthropic_when_configured(monkeypatch):
    fake_provider_client = _FakeProviderClient(anthropic_client=_FakeAnthropicClient("research"))
    monkeypatch.setenv("DISPATCHER_MODEL_PROVIDER", "anthropic")
    monkeypatch.setenv("DISPATCHER_MODEL", "claude-haiku-4-5-20251001")
    monkeypatch.setattr(main_dispatcher, "get_provider_client", lambda: fake_provider_client)

    result = await main_dispatcher._call_dispatcher_llm("recherchiere aktuelle daten")

    assert result == "research"
    assert fake_provider_client.validated == [
        (ModelProvider.ANTHROPIC, "claude-haiku-4-5-20251001", "dispatcher")
    ]


@pytest.mark.asyncio
async def test_call_dispatcher_llm_uses_google_generate_content(monkeypatch):
    captured = {}

    class _FakeAsyncClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url, params=None, json=None):
            captured["url"] = url
            captured["params"] = params
            captured["json"] = json
            return SimpleNamespace(
                raise_for_status=lambda: None,
                json=lambda: {
                    "candidates": [
                        {"content": {"parts": [{"text": "executor"}]}}
                    ]
                },
            )

    fake_provider_client = _FakeProviderClient()
    monkeypatch.setenv("DISPATCHER_MODEL_PROVIDER", "google")
    monkeypatch.setenv("DISPATCHER_MODEL", "gemini-2.5-flash")
    monkeypatch.setattr(main_dispatcher, "get_provider_client", lambda: fake_provider_client)
    monkeypatch.setattr(main_dispatcher.httpx, "AsyncClient", lambda timeout=30.0: _FakeAsyncClient())

    result = await main_dispatcher._call_dispatcher_llm("wie spaet ist es")

    assert result == "executor"
    assert captured["url"].endswith("/models/gemini-2.5-flash:generateContent")
    assert captured["params"] == {"key": "g-test"}
    assert captured["json"]["generationConfig"]["maxOutputTokens"] == 20


@pytest.mark.asyncio
async def test_call_dispatcher_llm_uses_dashscope_openai_compatible_provider(monkeypatch):
    fake_client = _FakeOpenAICompatClient("meta")
    fake_provider_client = _FakeProviderClient(compat_client=fake_client)
    monkeypatch.setenv("DISPATCHER_MODEL_PROVIDER", "dashscope")
    monkeypatch.setenv("DISPATCHER_MODEL", "qwen3.6-plus")
    monkeypatch.setattr(main_dispatcher, "get_provider_client", lambda: fake_provider_client)

    result = await main_dispatcher._call_dispatcher_llm("plane einen naechsten schritt")

    assert result == "meta"
    assert fake_provider_client.validated == [
        (ModelProvider.DASHSCOPE, "qwen3.6-plus", "dispatcher")
    ]
    assert fake_client.calls
    assert fake_client.calls[0]["model"] == "qwen3.6-plus"


@pytest.mark.asyncio
async def test_call_dispatcher_llm_uses_dashscope_native_generation_endpoint(monkeypatch):
    captured = {}

    class _FakeAsyncClient:
        def __init__(self, timeout):
            captured["timeout"] = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url, headers=None, json=None):
            captured["url"] = url
            captured["headers"] = headers
            captured["json"] = json
            return SimpleNamespace(
                raise_for_status=lambda: None,
                json=lambda: {
                    "output": {
                        "choices": [
                            {
                                "message": {
                                    "content": "meta",
                                    "reasoning_content": "",
                                }
                            }
                        ]
                    },
                    "usage": {
                        "input_tokens": 11,
                        "output_tokens": 3,
                        "input_tokens_details": {"cached_tokens": 0},
                    },
                },
            )

    fake_provider_client = _FakeProviderClient()
    monkeypatch.setenv("DISPATCHER_MODEL_PROVIDER", "dashscope_native")
    monkeypatch.setenv("DISPATCHER_MODEL", "qwen3.6-plus")
    monkeypatch.setattr(main_dispatcher, "get_provider_client", lambda: fake_provider_client)
    monkeypatch.setattr(main_dispatcher.httpx, "AsyncClient", _FakeAsyncClient)

    result = await main_dispatcher._call_dispatcher_llm("plane einen naechsten schritt")

    assert result == "meta"
    assert fake_provider_client.validated == [
        (ModelProvider.DASHSCOPE_NATIVE, "qwen3.6-plus", "dispatcher")
    ]
    assert captured["url"].endswith("/services/aigc/multimodal-generation/generation")
    assert captured["json"]["model"] == "qwen3.6-plus"
    assert captured["json"]["parameters"]["result_format"] == "message"
    assert captured["json"]["input"]["messages"][0]["role"] == "system"

@pytest.mark.asyncio
async def test_get_agent_decision_falls_back_to_meta_on_dispatcher_error(monkeypatch):
    async def _boom(_query: str) -> str:
        raise RuntimeError("provider down")

    observed = []
    monkeypatch.setattr(main_dispatcher, "_call_dispatcher_llm", _boom)
    monkeypatch.setattr(
        main_dispatcher,
        "record_autonomy_observation",
        lambda event_type, payload, observed_at="": observed.append(
            {"event_type": event_type, "payload": dict(payload), "observed_at": observed_at}
        )
        or True,
    )

    result = await main_dispatcher.get_agent_decision("vage anfrage ohne keyword")

    assert result == "meta"
    assert observed[0]["event_type"] == "dispatcher_meta_fallback"
    assert observed[0]["payload"]["reason"] == "dispatcher_exception"


@pytest.mark.asyncio
async def test_get_agent_decision_extracts_agent_from_verbose_dispatcher_response(monkeypatch):
    async def _verbose(_query: str, session_id: str = "") -> str:
        return "Ich wähle hier klar den Agenten meta."

    monkeypatch.setattr(main_dispatcher, "_call_dispatcher_llm", _verbose)

    result = await main_dispatcher.get_agent_decision("was kannst du alles")

    assert result == "meta"


@pytest.mark.asyncio
async def test_get_agent_decision_records_meta_fallback_on_empty_dispatcher_decision(monkeypatch):
    observed = []

    async def _empty(_query: str, session_id: str = "") -> str:
        return ""

    monkeypatch.setattr(main_dispatcher, "_call_dispatcher_llm", _empty)
    monkeypatch.setattr(
        main_dispatcher,
        "record_autonomy_observation",
        lambda event_type, payload, observed_at="": observed.append(
            {"event_type": event_type, "payload": dict(payload), "observed_at": observed_at}
        )
        or True,
    )

    result = await main_dispatcher.get_agent_decision("welches land passt besser zu mir")

    assert result == "meta"
    assert observed[0]["event_type"] == "dispatcher_meta_fallback"
    assert observed[0]["payload"]["reason"] == "empty_decision"


@pytest.mark.asyncio
async def test_get_agent_decision_skips_llm_for_blackboard_query(monkeypatch):
    async def _boom(_query: str, session_id: str = "") -> str:
        raise AssertionError("dispatcher llm should not be called")

    monkeypatch.setattr(main_dispatcher, "_call_dispatcher_llm", _boom)

    result = await main_dispatcher.get_agent_decision("was gibts auf dem blackboard")

    assert result == "meta"


def test_dispatcher_feedback_bias_promotes_meta_for_complex_queries(monkeypatch, tmp_path):
    engine = FeedbackEngine(db_path=tmp_path / "dispatcher_feedback.db")
    for idx in range(1, 4):
        engine.record_signal(
            f"disp-meta-{idx}",
            "positive",
            feedback_targets=[{"namespace": "dispatcher_agent", "key": "meta"}],
        )
        engine.record_signal(
            f"disp-shell-{idx}",
            "negative",
            feedback_targets=[{"namespace": "dispatcher_agent", "key": "shell"}],
        )
    monkeypatch.setattr("orchestration.feedback_engine.get_feedback_engine", lambda: engine)

    decision = main_dispatcher._apply_dispatcher_feedback_bias(
        "Starte den Browser, gehe auf booking.com, tippe Berlin, waehle Daten und klicke auf Suchen",
        "shell",
    )

    assert decision == "meta"


def test_dispatcher_feedback_bias_requires_enough_evidence(monkeypatch, tmp_path):
    engine = FeedbackEngine(db_path=tmp_path / "dispatcher_feedback_min_evidence.db")
    engine.record_signal(
        "disp-meta-low",
        "positive",
        feedback_targets=[{"namespace": "dispatcher_agent", "key": "meta"}],
    )
    engine.record_signal(
        "disp-shell-low",
        "negative",
        feedback_targets=[{"namespace": "dispatcher_agent", "key": "shell"}],
    )
    monkeypatch.setattr("orchestration.feedback_engine.get_feedback_engine", lambda: engine)

    decision = main_dispatcher._apply_dispatcher_feedback_bias(
        "Starte den Browser, gehe auf booking.com, tippe Berlin, waehle Daten und klicke auf Suchen",
        "shell",
    )

    assert decision == "shell"
