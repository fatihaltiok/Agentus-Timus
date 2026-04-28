from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import deal
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


@deal.post(lambda r: r in {"partial", "error"})
def timeout_status_for_agent(agent_name: str) -> str:
    from agent.agent_registry import AgentRegistry

    return AgentRegistry._timeout_status_for_agent(agent_name)


@deal.pre(lambda timeout_seconds, attempts: timeout_seconds > 0 and attempts >= 1)
@deal.post(lambda r: r["timed_out"] is True)
@deal.post(lambda r, timeout_seconds, attempts: r["timeout_seconds"] == timeout_seconds and r["attempts"] == attempts)
def timeout_metadata_for_agent(
    agent_name: str,
    timeout_seconds: float,
    attempts: int,
) -> dict:
    from agent.agent_registry import AgentRegistry

    return AgentRegistry._build_timeout_metadata(
        agent_name=agent_name,
        timeout_seconds=timeout_seconds,
        session_id="sess-x",
        attempts=attempts,
    )


@pytest.mark.asyncio
async def test_sequential_research_timeout_returns_partial(monkeypatch):
    from agent.agent_registry import AgentRegistry

    registry = AgentRegistry()

    async def _fake_tools():
        return "tools"

    class _SlowResearchAgent:
        conversation_session_id = None

        async def run(self, task: str) -> str:
            await asyncio.sleep(10)
            return "never"

    monkeypatch.setenv("RESEARCH_TIMEOUT", "0.05")
    monkeypatch.setenv("DELEGATION_MAX_RETRIES", "1")
    registry._get_tools_description = _fake_tools
    registry.register_spec("research", "research", ["research"], lambda tools_description_string: _SlowResearchAgent())

    result = await registry.delegate(from_agent="meta", to_agent="research", task="breite recherche")

    assert result["status"] == "partial"
    assert "Timeout" in result["error"]
    assert result["metadata"]["timed_out"] is True
    assert result["metadata"]["timeout_seconds"] == pytest.approx(0.05)
    assert "recovery_hint" in result["metadata"]


@pytest.mark.asyncio
async def test_sequential_non_research_timeout_stays_error(monkeypatch):
    from agent.agent_registry import AgentRegistry

    registry = AgentRegistry()

    async def _fake_tools():
        return "tools"

    class _SlowShellAgent:
        conversation_session_id = None

        async def run(self, task: str) -> str:
            await asyncio.sleep(10)
            return "never"

    monkeypatch.setenv("DELEGATION_TIMEOUT", "0.05")
    monkeypatch.setenv("DELEGATION_MAX_RETRIES", "1")
    registry._get_tools_description = _fake_tools
    registry.register_spec("shell", "shell", ["shell"], lambda tools_description_string: _SlowShellAgent())

    result = await registry.delegate(from_agent="meta", to_agent="shell", task="run ls")

    assert result["status"] == "error"
    assert "Timeout" in result["error"]
    assert result["metadata"]["timed_out"] is True


@pytest.mark.asyncio
async def test_research_model_configuration_error_is_typed(monkeypatch):
    from agent.agent_registry import AgentRegistry
    from agent.providers import ModelConfigurationError

    registry = AgentRegistry()
    events = []

    async def _fake_tools():
        return "tools"

    def _broken_factory(tools_description_string: str):
        del tools_description_string
        raise ModelConfigurationError("Konfiguriertes Modell 'deepseek-reasoner' existiert nicht")

    monkeypatch.setattr(
        "agent.agent_registry.record_autonomy_observation",
        lambda event_type, payload: events.append((event_type, payload)),
    )
    registry._get_tools_description = _fake_tools
    registry.register_spec("research", "research", ["research"], _broken_factory)

    result = await registry.delegate(from_agent="meta", to_agent="research", task="breite recherche")

    assert result["status"] == "error"
    assert result["metadata"]["error_class"] == "model_configuration"
    assert "nicht startbar" in result["error"]
    assert events[0][0] == "agent_model_configuration_failed"
    assert events[0][1]["retryable"] is False


def test_timeout_status_contract():
    assert timeout_status_for_agent("research") == "partial"
    assert timeout_status_for_agent("shell") == "error"


@given(agent_name=st.sampled_from(["research", "meta", "shell", "document"]))
@settings(deadline=None, max_examples=40)
def test_hypothesis_timeout_status_is_role_consistent(agent_name: str):
    expected = "partial" if agent_name == "research" else "error"
    assert timeout_status_for_agent(agent_name) == expected
