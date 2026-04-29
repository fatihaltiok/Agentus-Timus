from __future__ import annotations

import deal


@deal.post(lambda r: isinstance(r, bool))
def research_fallback_decision_contract(
    agent_name: str,
    outcome_status: str,
    timed_out: bool,
    step_signal_reason: str,
    error_text: str,
) -> bool:
    from agent.agent_registry import AgentRegistry

    return AgentRegistry._should_trigger_research_fallback(
        agent_name,
        outcome_status,
        {"timed_out": timed_out} if timed_out else {},
        step_signal_reason=step_signal_reason,
        error_text=error_text,
    )


@deal.post(lambda r: r >= 0.0)
def research_tool_timeout_contract(raw_value: str) -> float:
    try:
        parsed = float(str(raw_value or "").strip())
    except ValueError:
        parsed = 2700.0
    return max(0.0, parsed)


def test_research_tool_timeout_contract_matches_agent_examples(monkeypatch) -> None:
    from agent.agents.research import DeepResearchAgent

    monkeypatch.setenv("DEEP_RESEARCH_START_TIMEOUT", "0.01")
    assert DeepResearchAgent._tool_timeout_seconds("start_deep_research") == 0.01
    monkeypatch.setenv("DEEP_RESEARCH_START_TIMEOUT", "-5")
    assert DeepResearchAgent._tool_timeout_seconds("start_deep_research") == 0.0
    monkeypatch.setenv("DEEP_RESEARCH_START_TIMEOUT", "invalid")
    try:
        assert DeepResearchAgent._tool_timeout_seconds("start_deep_research") == 2700.0
    finally:
        monkeypatch.delenv("DEEP_RESEARCH_START_TIMEOUT", raising=False)


def test_research_fallback_decision_contract_examples() -> None:
    assert research_fallback_decision_contract("research", "partial", True, "", "")
    assert research_fallback_decision_contract(
        "research",
        "partial",
        False,
        "research_tool_timeout",
        "",
    )
    assert not research_fallback_decision_contract("executor", "partial", True, "", "")


def test_research_tool_timeout_contract_examples() -> None:
    assert research_tool_timeout_contract("0.01") == 0.01
    assert research_tool_timeout_contract("-5") == 0.0
    assert research_tool_timeout_contract("invalid") == 2700.0
