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


@deal.post(lambda r: isinstance(r, bool))
def should_trigger_research_fallback(
    agent_name: str,
    outcome_status: str,
    timed_out: bool = False,
    step_signal_reason: str = "",
    error_text: str = "",
) -> bool:
    from agent.agent_registry import AgentRegistry

    return AgentRegistry._should_trigger_research_fallback(
        agent_name,
        outcome_status,
        {"timed_out": timed_out} if timed_out else {},
        step_signal_reason=step_signal_reason,
        error_text=error_text,
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
async def test_sequential_research_timeout_uses_executor_fallback(monkeypatch):
    from agent.agent_registry import AgentRegistry

    registry = AgentRegistry()
    events = []
    captured_executor_task = {}

    async def _fake_tools():
        return "tools"

    class _SlowResearchAgent:
        conversation_session_id = None

        async def run(self, task: str) -> str:
            await asyncio.sleep(10)
            return "never"

    class _FallbackExecutorAgent:
        conversation_session_id = None

        async def run(self, task: str) -> str:
            captured_executor_task["task"] = task
            return "Fallback mit Quellen: Bundesnetzagentur https://www.bundesnetzagentur.de"

    monkeypatch.setenv("RESEARCH_TIMEOUT", "0.05")
    monkeypatch.setenv("DELEGATION_MAX_RETRIES", "1")
    monkeypatch.setenv("RESEARCH_EXECUTOR_FALLBACK_ENABLED", "true")
    monkeypatch.setattr(
        "agent.agent_registry.record_autonomy_observation",
        lambda event_type, payload: events.append((event_type, payload)),
    )
    registry._get_tools_description = _fake_tools
    registry.register_spec("research", "research", ["research"], lambda tools_description_string: _SlowResearchAgent())
    registry.register_spec("executor", "executor", ["execution"], lambda tools_description_string: _FallbackExecutorAgent())

    result = await registry.delegate(from_agent="meta", to_agent="research", task="Balkonkraftwerk Regeln 2026")

    assert result["status"] == "partial"
    assert "Fallback mit Quellen" in result["result"]
    assert result["metadata"]["fallback_used"] is True
    assert result["metadata"]["fallback_agent"] == "executor"
    assert "avoid_deep_research: yes" in captured_executor_task["task"]
    assert any(event == "agent_fallback_triggered" for event, _payload in events)
    assert any(event == "agent_fallback_completed" for event, _payload in events)


@pytest.mark.asyncio
async def test_deep_research_tool_timeout_returns_typed_error(monkeypatch):
    from agent.agents.research import DeepResearchAgent, _CURRENT_RESEARCH_TASK
    from agent.base_agent import BaseAgent

    events = []

    async def _slow_tool(self, method: str, params: dict):
        await asyncio.sleep(10)
        return {"status": "success"}

    monkeypatch.setenv("DEEP_RESEARCH_START_TIMEOUT", "0.01")
    monkeypatch.setattr(BaseAgent, "_call_tool", _slow_tool)
    monkeypatch.setattr(
        "agent.agents.research.record_autonomy_observation",
        lambda event_type, payload: events.append((event_type, payload)),
    )

    agent = DeepResearchAgent.__new__(DeepResearchAgent)
    agent.current_session_id = None
    token = _CURRENT_RESEARCH_TASK.set("Balkonkraftwerk Regeln Deutschland 2026")
    try:
        result = await DeepResearchAgent._call_tool(
            agent,
            "start_deep_research",
            {"query": "Balkonkraftwerk Regeln Deutschland 2026"},
        )
    finally:
        _CURRENT_RESEARCH_TASK.reset(token)

    assert result["timed_out"] is True
    assert result["error_class"] == "timeout"
    assert result["timeout_seconds"] == pytest.approx(0.01)
    assert events[0][0] == "research_tool_timeout"


def test_deep_research_tool_timeout_finalizes_as_step_blocked(monkeypatch):
    from agent.agents.research import DeepResearchAgent
    from orchestration.specialist_step_package import parse_specialist_step_signal_response

    monkeypatch.setenv("DEEP_RESEARCH_START_TIMEOUT", "0.01")
    agent = DeepResearchAgent.__new__(DeepResearchAgent)

    response = DeepResearchAgent._maybe_finalize_after_terminal_tool(
        agent,
        "start_deep_research",
        {"timed_out": True, "timeout_seconds": 0.01},
    )

    parsed = parse_specialist_step_signal_response(response)
    assert parsed["signal"] == "step_blocked"
    assert parsed["reason"] == "research_tool_timeout"
    assert "Fallback" in parsed["message"]


def test_deep_research_start_timeout_uses_research_runtime(monkeypatch):
    from agent.agents.research import DeepResearchAgent

    monkeypatch.delenv("DEEP_RESEARCH_START_TIMEOUT", raising=False)
    monkeypatch.setenv("RESEARCH_TIMEOUT", "2700")
    monkeypatch.setenv("DEEP_RESEARCH_QUICK_TOOL_TIMEOUT", "120")

    assert DeepResearchAgent._tool_timeout_seconds("start_deep_research") == pytest.approx(2700.0)


def test_deep_research_report_timeout_is_separate(monkeypatch):
    from agent.agents.research import DeepResearchAgent

    monkeypatch.setenv("DEEP_RESEARCH_REPORT_TIMEOUT", "900")
    monkeypatch.setenv("RESEARCH_TIMEOUT", "2700")

    assert DeepResearchAgent._tool_timeout_seconds("generate_research_report") == pytest.approx(900.0)


def test_deep_research_quick_tool_timeout_is_not_report_timeout(monkeypatch):
    from agent.agents.research import DeepResearchAgent

    monkeypatch.setenv("DEEP_RESEARCH_QUICK_TOOL_TIMEOUT", "120")
    monkeypatch.setenv("RESEARCH_TIMEOUT", "2700")

    assert DeepResearchAgent._tool_timeout_seconds("verify_fact") == pytest.approx(120.0)


@pytest.mark.asyncio
async def test_direct_research_timeout_step_signal_uses_executor_fallback(monkeypatch):
    import main_dispatcher
    from agent.agent_registry import agent_registry

    captured = {}

    async def _fake_fallback(**kwargs):
        captured.update(kwargs)
        return {
            "status": "partial",
            "result": "Deep Research war nicht rechtzeitig verfuegbar; kompakter Fallback mit Quellen.",
            "metadata": {"fallback_agent": "executor"},
        }

    monkeypatch.setattr(agent_registry, "_maybe_run_research_executor_fallback", _fake_fallback)

    runtime_metadata = {}
    result = await main_dispatcher._maybe_apply_direct_research_timeout_fallback(
        agent_name="research",
        final_answer=(
            "Specialist Step Signal: step_blocked | reason=research_tool_timeout\n\n"
            "Deep Research wurde nach 120.0s gestoppt."
        ),
        original_task="Balkonkraftwerk Regeln 2026",
        session_id="sess-direct-research-timeout",
        runtime_metadata=runtime_metadata,
    )

    assert "kompakter Fallback" in result
    assert captured["from_agent"] == "direct_chat"
    assert captured["reason"] == "research_tool_timeout"
    assert captured["original_task"] == "Balkonkraftwerk Regeln 2026"
    assert runtime_metadata["research_direct_fallback_used"] is True
    assert runtime_metadata["research_direct_fallback_agent"] == "executor"


@pytest.mark.asyncio
async def test_direct_research_non_timeout_step_signal_stays_unchanged(monkeypatch):
    import main_dispatcher

    runtime_metadata = {}
    answer = "Specialist Step Signal: step_blocked | reason=missing_credentials"
    result = await main_dispatcher._maybe_apply_direct_research_timeout_fallback(
        agent_name="research",
        final_answer=answer,
        original_task="Balkonkraftwerk Regeln 2026",
        session_id="sess-direct-research-timeout",
        runtime_metadata=runtime_metadata,
    )

    assert result == answer
    assert runtime_metadata == {}


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
    assert should_trigger_research_fallback("research", "partial", timed_out=True)
    assert should_trigger_research_fallback(
        "research",
        "partial",
        step_signal_reason="research_tool_timeout",
    )
    assert not should_trigger_research_fallback("shell", "partial", timed_out=True)
    assert not should_trigger_research_fallback("research", "success", timed_out=True)


@given(agent_name=st.sampled_from(["research", "meta", "shell", "document"]))
@settings(deadline=None, max_examples=40)
def test_hypothesis_timeout_status_is_role_consistent(agent_name: str):
    expected = "partial" if agent_name == "research" else "error"
    assert timeout_status_for_agent(agent_name) == expected


@given(
    agent_name=st.sampled_from(["research", "meta", "shell", "document"]),
    outcome_status=st.sampled_from(["success", "partial", "error"]),
    timed_out=st.booleans(),
)
@settings(deadline=None, max_examples=80)
def test_hypothesis_research_fallback_only_for_failed_research(
    agent_name: str,
    outcome_status: str,
    timed_out: bool,
):
    result = should_trigger_research_fallback(agent_name, outcome_status, timed_out=timed_out)
    if result:
        assert agent_name == "research"
        assert outcome_status in {"partial", "error"}
        assert timed_out is True
