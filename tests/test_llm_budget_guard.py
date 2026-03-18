from __future__ import annotations

from types import SimpleNamespace

import pytest

import main_dispatcher
from agent import base_agent as base_agent_mod
from orchestration import llm_budget_guard
from agent.providers import ModelProvider


class _FakeEngine:
    def get_llm_usage_summary(self, *, days=7, session_id=None, agent=None, limit=5):
        del days, limit
        if session_id:
            return {"total_cost_usd": 1.25}
        if agent:
            return {"total_cost_usd": 0.6}
        return {"total_cost_usd": 2.5}


def test_evaluate_llm_budget_returns_soft_limit(monkeypatch):
    monkeypatch.setattr(llm_budget_guard, "get_improvement_engine", lambda: _FakeEngine())
    monkeypatch.setenv("TIMUS_LLM_BUDGET_GLOBAL_WARN_USD", "1.0")
    monkeypatch.setenv("TIMUS_LLM_BUDGET_GLOBAL_SOFT_LIMIT_USD", "2.0")
    monkeypatch.setenv("TIMUS_LLM_BUDGET_GLOBAL_HARD_LIMIT_USD", "3.0")
    monkeypatch.setenv("TIMUS_LLM_BUDGET_AGENT_WARN_USD", "0.5")
    monkeypatch.setenv("TIMUS_LLM_BUDGET_AGENT_SOFT_LIMIT_USD", "0.75")
    monkeypatch.setenv("TIMUS_LLM_BUDGET_AGENT_HARD_LIMIT_USD", "1.5")
    monkeypatch.setenv("TIMUS_LLM_BUDGET_SESSION_WARN_USD", "1.0")
    monkeypatch.setenv("TIMUS_LLM_BUDGET_SESSION_SOFT_LIMIT_USD", "1.2")
    monkeypatch.setenv("TIMUS_LLM_BUDGET_SESSION_HARD_LIMIT_USD", "2.0")
    monkeypatch.setenv("TIMUS_LLM_BUDGET_SOFT_MAX_TOKENS", "256")

    decision = llm_budget_guard.evaluate_llm_budget(
        agent="meta",
        session_id="sess-1",
        requested_max_tokens=2000,
    )

    assert decision.blocked is False
    assert decision.soft_limited is True
    assert decision.state == "soft_limit"
    assert decision.max_tokens_cap == 256


@pytest.mark.asyncio
async def test_base_agent_soft_budget_caps_max_tokens(monkeypatch):
    calls = []

    class _FakeClient:
        def __init__(self):
            self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

        def _create(self, **kwargs):
            calls.append(kwargs)
            return SimpleNamespace(
                usage=SimpleNamespace(prompt_tokens=5, completion_tokens=2, prompt_tokens_details=SimpleNamespace(cached_tokens=0)),
                choices=[SimpleNamespace(message=SimpleNamespace(content="ok", reasoning_content=""))],
            )

    class _ProviderClient:
        def get_client(self, _provider):
            return _FakeClient()

    monkeypatch.setattr(
        base_agent_mod,
        "evaluate_llm_budget",
        lambda **kwargs: llm_budget_guard.LLMBudgetDecision(
            blocked=False,
            warning=True,
            soft_limited=True,
            max_tokens_cap=111,
            state="soft_limit",
            scopes=[],
            message="soft active",
        ),
    )
    monkeypatch.setattr(base_agent_mod, "get_improvement_engine", lambda: SimpleNamespace(record_llm_usage=lambda record: None))

    agent = base_agent_mod.BaseAgent.__new__(base_agent_mod.BaseAgent)
    agent.provider_client = _ProviderClient()
    agent.provider = base_agent_mod.ModelProvider.OPENAI
    agent.model = "gpt-5.4-2026-03-05"
    agent.agent_type = "visual"
    agent.conversation_session_id = "sess-1"

    result = await base_agent_mod.BaseAgent._call_llm(agent, [{"role": "user", "content": "hello"}])

    assert result == "ok"
    sent = calls[0]
    assert sent.get("max_completion_tokens", sent.get("max_tokens")) == 111


@pytest.mark.asyncio
async def test_base_agent_soft_budget_uses_model_override(monkeypatch):
    calls = []

    class _FakeClient:
        def __init__(self):
            self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

        def _create(self, **kwargs):
            calls.append(kwargs)
            return SimpleNamespace(
                usage=SimpleNamespace(prompt_tokens=5, completion_tokens=2, prompt_tokens_details=SimpleNamespace(cached_tokens=0)),
                choices=[SimpleNamespace(message=SimpleNamespace(content="ok", reasoning_content=""))],
            )

    class _ProviderClient:
        def get_client(self, _provider):
            return _FakeClient()

    monkeypatch.setattr(
        base_agent_mod,
        "evaluate_llm_budget",
        lambda **kwargs: llm_budget_guard.LLMBudgetDecision(
            blocked=False,
            warning=True,
            soft_limited=True,
            max_tokens_cap=333,
            state="soft_limit",
            scopes=[],
            message="soft active",
        ),
    )
    monkeypatch.setattr(
        base_agent_mod,
        "resolve_soft_budget_model_override",
        lambda **kwargs: llm_budget_guard.BudgetModelOverride(
            provider=ModelProvider.OPENROUTER,
            model="google/gemini-3.1-flash-lite-preview",
        ),
    )
    monkeypatch.setattr(base_agent_mod, "get_improvement_engine", lambda: SimpleNamespace(record_llm_usage=lambda record: None))

    agent = base_agent_mod.BaseAgent.__new__(base_agent_mod.BaseAgent)
    agent.provider_client = _ProviderClient()
    agent.provider = base_agent_mod.ModelProvider.OPENAI
    agent.model = "gpt-5.4-2026-03-05"
    agent.agent_type = "visual"
    agent.conversation_session_id = "sess-2"

    result = await base_agent_mod.BaseAgent._call_llm(agent, [{"role": "user", "content": "hello"}])

    assert result == "ok"
    assert calls[0]["model"] == "google/gemini-3.1-flash-lite-preview"


@pytest.mark.asyncio
async def test_base_agent_runtime_fallback_switches_provider_on_retryable_error(monkeypatch):
    calls = []

    class _BrokenClient:
        def __init__(self):
            self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

        def _create(self, **kwargs):
            calls.append((ModelProvider.DEEPSEEK, kwargs["model"]))
            raise RuntimeError("connection error to deepseek")

    class _FallbackClient:
        def __init__(self):
            self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

        def _create(self, **kwargs):
            calls.append((ModelProvider.OPENROUTER, kwargs["model"]))
            return SimpleNamespace(
                usage=SimpleNamespace(prompt_tokens=5, completion_tokens=2, prompt_tokens_details=SimpleNamespace(cached_tokens=0)),
                choices=[SimpleNamespace(message=SimpleNamespace(content="fallback ok", reasoning_content=""))],
            )

    class _ProviderClient:
        def get_client(self, provider):
            if provider == ModelProvider.DEEPSEEK:
                return _BrokenClient()
            if provider == ModelProvider.OPENROUTER:
                return _FallbackClient()
            raise AssertionError(f"unexpected provider {provider}")

    monkeypatch.setattr(
        base_agent_mod,
        "evaluate_llm_budget",
        lambda **kwargs: llm_budget_guard.LLMBudgetDecision(
            blocked=False,
            warning=False,
            soft_limited=False,
            max_tokens_cap=None,
            state="ok",
            scopes=[],
            message="ok",
        ),
    )
    monkeypatch.setattr(
        base_agent_mod,
        "resolve_soft_budget_model_override",
        lambda **kwargs: None,
    )
    monkeypatch.setattr(base_agent_mod, "get_improvement_engine", lambda: SimpleNamespace(record_llm_usage=lambda record: None))

    agent = base_agent_mod.BaseAgent.__new__(base_agent_mod.BaseAgent)
    agent.provider_client = _ProviderClient()
    agent.provider = base_agent_mod.ModelProvider.DEEPSEEK
    agent.model = "deepseek-reasoner"
    agent.fallback_provider = base_agent_mod.ModelProvider.OPENROUTER
    agent.fallback_model = "deepseek/deepseek-v3.2"
    agent.agent_type = "deep_research"
    agent.conversation_session_id = "sess-fallback"

    result = await base_agent_mod.BaseAgent._call_llm(agent, [{"role": "user", "content": "hello"}])

    assert result == "fallback ok"
    assert calls == [
        (ModelProvider.DEEPSEEK, "deepseek-reasoner"),
        (ModelProvider.OPENROUTER, "deepseek/deepseek-v3.2"),
    ]


@pytest.mark.asyncio
async def test_dispatcher_hard_budget_falls_back_to_meta(monkeypatch):
    monkeypatch.setenv("DISPATCHER_MODEL_PROVIDER", "zai")
    monkeypatch.setenv("DISPATCHER_MODEL", "glm-5")

    class _ProviderClient:
        def validate_model_or_raise(self, provider, model, *, agent_type=""):
            del provider, model, agent_type

    monkeypatch.setattr(main_dispatcher, "get_provider_client", lambda: _ProviderClient())
    monkeypatch.setattr(
        main_dispatcher,
        "evaluate_llm_budget",
        lambda **kwargs: llm_budget_guard.LLMBudgetDecision(
            blocked=True,
            warning=True,
            soft_limited=True,
            max_tokens_cap=None,
            state="hard_limit",
            scopes=[],
            message="hard active",
        ),
    )

    result = await main_dispatcher._call_dispatcher_llm("unklare anfrage", session_id="sess-77")

    assert result == "meta"


def test_resolve_soft_budget_model_override_uses_agent_specific_env(monkeypatch):
    monkeypatch.setenv("TIMUS_LLM_BUDGET_META_SOFT_PROVIDER", "openrouter")
    monkeypatch.setenv("TIMUS_LLM_BUDGET_META_SOFT_MODEL", "google/gemini-3.1-flash-lite-preview")

    override = llm_budget_guard.resolve_soft_budget_model_override(
        agent="meta",
        provider=ModelProvider.OPENAI,
        model="gpt-5.4-2026-03-05",
        decision=llm_budget_guard.LLMBudgetDecision(
            blocked=False,
            warning=True,
            soft_limited=True,
            max_tokens_cap=256,
            state="soft_limit",
            scopes=[],
            message="soft active",
        ),
    )

    assert override is not None
    assert override.provider == ModelProvider.OPENROUTER
    assert override.model == "google/gemini-3.1-flash-lite-preview"


def test_cap_parallelism_for_budget_reduces_soft_limit(monkeypatch):
    monkeypatch.setattr(
        llm_budget_guard,
        "evaluate_llm_budget",
        lambda **kwargs: llm_budget_guard.LLMBudgetDecision(
            blocked=False,
            warning=True,
            soft_limited=True,
            max_tokens_cap=256,
            state="soft_limit",
            scopes=[],
            message="soft active",
        ),
    )
    monkeypatch.setenv("TIMUS_LLM_BUDGET_SOFT_MAX_PARALLEL", "2")

    capped, decision = llm_budget_guard.cap_parallelism_for_budget(
        requested_parallel=6,
        agent="meta",
        session_id="sess-x",
    )

    assert capped == 2
    assert decision.state == "soft_limit"
