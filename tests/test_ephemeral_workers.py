from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from agent.providers import ModelProvider
from orchestration import ephemeral_workers as workers
from orchestration import llm_budget_guard


@pytest.mark.asyncio
async def test_run_worker_returns_disabled_when_feature_flag_is_off(monkeypatch):
    monkeypatch.setenv("EPHEMERAL_WORKERS_ENABLED", "false")

    result = await workers.run_worker(
        workers.WorkerTask(
            worker_type="query_variants",
            system_prompt="JSON only",
            input_payload={"query": "industrial robotics ai"},
        ),
        profile_prefix="DR_WORKER_QUERY",
        agent="deep_research",
        session_id="sess-disabled",
    )

    assert result.status == "disabled"
    assert result.fallback_used is True


@pytest.mark.asyncio
async def test_run_worker_applies_budget_cap_and_parses_json(monkeypatch):
    calls = []
    usage_records = []

    class _FakeClient:
        def __init__(self):
            self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

        def _create(self, **kwargs):
            calls.append(kwargs)
            return SimpleNamespace(
                usage=SimpleNamespace(
                    prompt_tokens=14,
                    completion_tokens=9,
                    prompt_tokens_details=SimpleNamespace(cached_tokens=0),
                ),
                choices=[
                    SimpleNamespace(
                        message=SimpleNamespace(
                            content='{"query_variants":["industrial robotics ai architecture 2026 paper"]}'
                        )
                    )
                ],
            )

    class _ProviderClient:
        def get_client(self, provider):
            assert provider == ModelProvider.OPENAI
            return _FakeClient()

    monkeypatch.setenv("EPHEMERAL_WORKERS_ENABLED", "true")
    monkeypatch.setenv("EPHEMERAL_WORKER_PROVIDER", "openai")
    monkeypatch.setenv("EPHEMERAL_WORKER_MODEL", "gpt-5.4-mini")
    monkeypatch.setenv("DR_WORKER_QUERY_MAX_TOKENS", "1500")
    monkeypatch.setattr(workers, "get_provider_client", lambda: _ProviderClient())
    monkeypatch.setattr(workers, "validate_configured_model_or_raise", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        workers,
        "evaluate_llm_budget",
        lambda **kwargs: llm_budget_guard.LLMBudgetDecision(
            blocked=False,
            warning=True,
            soft_limited=True,
            max_tokens_cap=111,
            state="soft_limit",
            scopes=[],
            message="soft limit",
        ),
    )
    monkeypatch.setattr(workers, "resolve_soft_budget_model_override", lambda **kwargs: None)
    monkeypatch.setattr(
        workers,
        "get_improvement_engine",
        lambda: SimpleNamespace(record_llm_usage=lambda record: usage_records.append(record)),
    )

    result = await workers.run_worker(
        workers.WorkerTask(
            worker_type="query_variants",
            system_prompt="JSON only",
            input_payload={"query": "industrial robotics ai"},
            response_schema={"query_variants": ["<query>"]},
        ),
        profile_prefix="DR_WORKER_QUERY",
        agent="deep_research",
        session_id="sess-query",
    )

    assert result.status == "ok"
    assert result.payload["query_variants"] == ["industrial robotics ai architecture 2026 paper"]
    assert calls
    assert calls[0]["model"] == "gpt-5.4-mini"
    assert calls[0]["max_completion_tokens"] == 111
    assert usage_records
    assert usage_records[0].agent == "deep_research"
    assert usage_records[0].session_id == "sess-query"


@pytest.mark.asyncio
async def test_run_worker_returns_blocked_before_provider_init(monkeypatch):
    monkeypatch.setenv("EPHEMERAL_WORKERS_ENABLED", "true")
    monkeypatch.setattr(
        workers,
        "evaluate_llm_budget",
        lambda **kwargs: llm_budget_guard.LLMBudgetDecision(
            blocked=True,
            warning=True,
            soft_limited=True,
            max_tokens_cap=None,
            state="hard_limit",
            scopes=[],
            message="blocked",
        ),
    )
    monkeypatch.setattr(
        workers,
        "get_provider_client",
        lambda: SimpleNamespace(get_client=lambda provider: (_ for _ in ()).throw(AssertionError("must not init"))),
    )

    result = await workers.run_worker(
        workers.WorkerTask(
            worker_type="query_variants",
            system_prompt="JSON only",
            input_payload={"query": "industrial robotics ai"},
        ),
        profile_prefix="DR_WORKER_QUERY",
        agent="deep_research",
        session_id="sess-blocked",
    )

    assert result.status == "blocked"
    assert result.fallback_used is True


@pytest.mark.asyncio
async def test_run_worker_batch_respects_capped_parallelism(monkeypatch):
    active = 0
    max_active = 0

    async def _fake_run_worker(*args, **kwargs):
        nonlocal active, max_active
        active += 1
        max_active = max(max_active, active)
        await asyncio.sleep(0.01)
        active -= 1
        return workers.WorkerResult(worker_type="query_variants", status="ok")

    monkeypatch.setattr(workers, "run_worker", _fake_run_worker)
    monkeypatch.setattr(
        workers,
        "cap_parallelism_for_budget",
        lambda **kwargs: (
            1,
            llm_budget_guard.LLMBudgetDecision(
                blocked=False,
                warning=True,
                soft_limited=True,
                max_tokens_cap=1,
                state="soft_limit",
                scopes=[],
                message="soft limit",
            ),
        ),
    )

    tasks = [
        workers.WorkerTask(worker_type="query_variants", system_prompt="json", input_payload={"n": i})
        for i in range(3)
    ]
    results = await workers.run_worker_batch(
        tasks,
        profile_prefix="DR_WORKER_QUERY",
        agent="deep_research",
        session_id="sess-batch",
        requested_parallel=3,
    )

    assert len(results) == 3
    assert max_active == 1
