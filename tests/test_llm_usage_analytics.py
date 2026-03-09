from __future__ import annotations

from types import SimpleNamespace

import pytest

import main_dispatcher
from agent import base_agent as base_agent_mod
from agent.providers import ModelProvider
from orchestration.self_improvement_engine import LLMUsageRecord, SelfImprovementEngine


class _CaptureEngine:
    def __init__(self):
        self.records = []

    def record_llm_usage(self, record):
        self.records.append(record)


class _FakeOpenAIResponse:
    def __init__(self, content: str):
        self.usage = SimpleNamespace(
            prompt_tokens=120,
            completion_tokens=45,
            prompt_tokens_details=SimpleNamespace(cached_tokens=12),
        )
        self.choices = [SimpleNamespace(message=SimpleNamespace(content=content, reasoning_content=""))]


class _FakeOpenAIClient:
    def __init__(self, response):
        self.response = response
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))
        self.calls = []

    def _create(self, **kwargs):
        self.calls.append(kwargs)
        return self.response


class _FakeProviderClient:
    def __init__(self, response):
        self.response = response

    def get_client(self, _provider):
        return _FakeOpenAIClient(self.response)


def test_self_improvement_engine_summarizes_llm_usage(tmp_path):
    engine = SelfImprovementEngine(db_path=tmp_path / "usage.db")
    engine.record_llm_usage(
        LLMUsageRecord(
            trace_id="u1",
            session_id="sess-a",
            agent="dispatcher",
            provider="zai",
            model="glm-5",
            input_tokens=100,
            output_tokens=30,
            cached_tokens=10,
            cost_usd=0.0015,
            latency_ms=210,
            success=True,
        )
    )
    engine.record_llm_usage(
        LLMUsageRecord(
            trace_id="u2",
            session_id="sess-a",
            agent="meta",
            provider="openrouter",
            model="z-ai/glm-5",
            input_tokens=300,
            output_tokens=150,
            cached_tokens=0,
            cost_usd=0.012,
            latency_ms=420,
            success=False,
        )
    )

    summary = engine.get_llm_usage_summary(days=7, session_id="sess-a", limit=3)

    assert summary["session_id"] == "sess-a"
    assert summary["total_requests"] == 2
    assert summary["successful_requests"] == 1
    assert summary["failed_requests"] == 1
    assert summary["input_tokens"] == 400
    assert summary["output_tokens"] == 180
    assert summary["cached_tokens"] == 10
    assert summary["total_cost_usd"] == 0.0135
    assert summary["top_agents"][0]["agent"] == "meta"
    assert summary["top_models"][0]["model"] == "z-ai/glm-5"


@pytest.mark.asyncio
async def test_base_agent_records_openai_compatible_usage(monkeypatch):
    capture_engine = _CaptureEngine()
    fake_response = _FakeOpenAIResponse("ok")
    fake_client = _FakeOpenAIClient(fake_response)

    class _ProviderClient:
        def get_client(self, _provider):
            return fake_client

    monkeypatch.setattr(base_agent_mod, "get_improvement_engine", lambda: capture_engine)

    agent = base_agent_mod.BaseAgent.__new__(base_agent_mod.BaseAgent)
    agent.provider_client = _ProviderClient()
    agent.provider = ModelProvider.OPENAI
    agent.model = "gpt-5.4-2026-03-05"
    agent.agent_type = "visual"
    agent.conversation_session_id = "sess-123"

    text = await base_agent_mod.BaseAgent._call_openai_compatible(
        agent,
        [{"role": "user", "content": "hello"}],
    )

    assert text == "ok"
    assert len(capture_engine.records) == 1
    record = capture_engine.records[0]
    assert record.session_id == "sess-123"
    assert record.agent == "visual"
    assert record.provider == "openai"
    assert record.input_tokens == 120
    assert record.output_tokens == 45
    assert record.cached_tokens == 12
    assert record.success is True


@pytest.mark.asyncio
async def test_dispatcher_records_openai_compatible_usage(monkeypatch):
    capture_engine = _CaptureEngine()
    fake_client = _FakeOpenAIClient(_FakeOpenAIResponse("meta"))

    class _DispatcherProviderClient:
        def validate_model_or_raise(self, provider, model, *, agent_type=""):
            del provider, model, agent_type

        def get_client(self, _provider):
            return fake_client

        def get_api_key(self, _provider):
            return "test-key"

        def get_base_url(self, _provider):
            return "https://example.test/v1"

    monkeypatch.setattr(main_dispatcher, "get_provider_client", lambda: _DispatcherProviderClient())
    monkeypatch.setattr(main_dispatcher, "get_improvement_engine", lambda: capture_engine)
    monkeypatch.setenv("DISPATCHER_MODEL_PROVIDER", "zai")
    monkeypatch.setenv("DISPATCHER_MODEL", "glm-5")

    result = await main_dispatcher._call_dispatcher_llm("plane diese aufgabe", session_id="sess-dispatch")

    assert result == "meta"
    assert len(capture_engine.records) == 1
    record = capture_engine.records[0]
    assert record.session_id == "sess-dispatch"
    assert record.agent == "dispatcher"
    assert record.provider == "zai"
    assert record.model == "glm-5"
    assert record.input_tokens == 120
    assert record.output_tokens == 45
