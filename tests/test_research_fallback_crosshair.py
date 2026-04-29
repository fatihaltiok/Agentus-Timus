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
    from agent.agents.research import DeepResearchAgent
    import os

    previous = os.environ.get("DEEP_RESEARCH_TOOL_TIMEOUT")
    os.environ["DEEP_RESEARCH_TOOL_TIMEOUT"] = raw_value
    try:
        return DeepResearchAgent._tool_timeout_seconds()
    finally:
        if previous is None:
            os.environ.pop("DEEP_RESEARCH_TOOL_TIMEOUT", None)
        else:
            os.environ["DEEP_RESEARCH_TOOL_TIMEOUT"] = previous


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
    assert research_tool_timeout_contract("invalid") == 120.0
