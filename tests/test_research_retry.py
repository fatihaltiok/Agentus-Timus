from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


@pytest.mark.asyncio
async def test_research_run_retries_on_empty_result(monkeypatch):
    from agent.agents.research import DeepResearchAgent
    from agent.base_agent import BaseAgent

    calls: list[str] = []
    sleeps: list[float] = []
    responses = ["", "Research ok"]

    async def _fake_base_run(self, task: str) -> str:
        calls.append(task)
        return responses.pop(0)

    async def _fake_context(self, task: str, policy: dict | None = None) -> str:
        return ""

    async def _fake_sleep(delay: float) -> None:
        sleeps.append(delay)

    monkeypatch.setattr(BaseAgent, "run", _fake_base_run)
    monkeypatch.setattr(DeepResearchAgent, "_build_research_context", _fake_context)
    monkeypatch.setattr(DeepResearchAgent, "_build_delegation_research_context", lambda self, handoff: "")
    monkeypatch.setattr("agent.agents.research.asyncio.sleep", _fake_sleep)
    monkeypatch.setenv("RESEARCH_RUN_MAX_RETRIES", "2")
    monkeypatch.setenv("RESEARCH_RETRY_BACKOFF_BASE_SECONDS", "0.25")

    agent = DeepResearchAgent.__new__(DeepResearchAgent)
    agent.current_session_id = None

    result = await DeepResearchAgent.run(agent, "Recherchiere KI-Agenten")

    assert result == "Research ok"
    assert len(calls) == 2
    assert "# RETRY-HINWEIS" in calls[1]
    assert sleeps == [0.25]


@pytest.mark.asyncio
async def test_research_run_retries_on_retryable_error_text(monkeypatch):
    from agent.agents.research import DeepResearchAgent
    from agent.base_agent import BaseAgent

    calls = 0

    async def _fake_base_run(self, task: str) -> str:
        nonlocal calls
        calls += 1
        return "Recovered" if calls == 2 else "Error: timeout from provider"

    async def _fake_context(self, task: str, policy: dict | None = None) -> str:
        return ""

    async def _fake_sleep(delay: float) -> None:
        return None

    monkeypatch.setattr(BaseAgent, "run", _fake_base_run)
    monkeypatch.setattr(DeepResearchAgent, "_build_research_context", _fake_context)
    monkeypatch.setattr(DeepResearchAgent, "_build_delegation_research_context", lambda self, handoff: "")
    monkeypatch.setattr("agent.agents.research.asyncio.sleep", _fake_sleep)
    monkeypatch.setenv("RESEARCH_RUN_MAX_RETRIES", "2")

    agent = DeepResearchAgent.__new__(DeepResearchAgent)
    agent.current_session_id = None

    result = await DeepResearchAgent.run(agent, "Recherchiere aktuelle Entwicklungen")

    assert result == "Recovered"
    assert calls == 2


@pytest.mark.asyncio
async def test_research_run_does_not_retry_on_non_retryable_error(monkeypatch):
    from agent.agents.research import DeepResearchAgent
    from agent.base_agent import BaseAgent

    calls = 0

    async def _fake_base_run(self, task: str) -> str:
        nonlocal calls
        calls += 1
        return "Error: invalid api key"

    async def _fake_context(self, task: str, policy: dict | None = None) -> str:
        return ""

    async def _fake_sleep(delay: float) -> None:
        raise AssertionError("sleep should not be called for non-retryable errors")

    monkeypatch.setattr(BaseAgent, "run", _fake_base_run)
    monkeypatch.setattr(DeepResearchAgent, "_build_research_context", _fake_context)
    monkeypatch.setattr(DeepResearchAgent, "_build_delegation_research_context", lambda self, handoff: "")
    monkeypatch.setattr("agent.agents.research.asyncio.sleep", _fake_sleep)
    monkeypatch.setenv("RESEARCH_RUN_MAX_RETRIES", "3")

    agent = DeepResearchAgent.__new__(DeepResearchAgent)
    agent.current_session_id = None

    result = await DeepResearchAgent.run(agent, "Recherchiere KI-Agenten")

    assert result == "Error: invalid api key"
    assert calls == 1


@pytest.mark.asyncio
async def test_research_run_adds_evidence_guard_for_career_followup(monkeypatch):
    from agent.agents.research import DeepResearchAgent
    from agent.base_agent import BaseAgent

    captured: dict[str, str] = {}

    async def _fake_base_run(self, task: str) -> str:
        captured["task"] = task
        return "ok"

    async def _fake_context(self, task: str, policy: dict | None = None) -> str:
        return ""

    monkeypatch.setattr(BaseAgent, "run", _fake_base_run)
    monkeypatch.setattr(DeepResearchAgent, "_build_research_context", _fake_context)
    monkeypatch.setattr(DeepResearchAgent, "_build_delegation_research_context", lambda self, handoff: "")
    monkeypatch.setattr(DeepResearchAgent, "_build_specialist_strategy_context", lambda self, handoff, payload: "")

    agent = DeepResearchAgent.__new__(DeepResearchAgent)
    agent.current_session_id = None

    result = await DeepResearchAgent.run(
        agent,
        "Wo in Europa kann ich mit KI am besten Karriere machen und wie kann ich am schnellsten ein Zertifikat erlangen?",
    )

    assert result == "ok"
    assert "# EVIDENZ-ANTWORT-GUARD" in captured["task"]
