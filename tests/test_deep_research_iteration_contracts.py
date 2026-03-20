"""CrossHair + Hypothesis contracts for DeepResearch iteration budgeting.

Lean 4 Bezug (CiSpecs.lean):
  - deep_research_iteration_lower
  - deep_research_iteration_upper
  - deep_research_default_iteration_budget_supports_guardrails
"""

from __future__ import annotations

import deal
from hypothesis import given, settings
from hypothesis import strategies as st

from agent.agents.research import (
    DeepResearchAgent,
    DeepResearchLoopLimits,
    build_deep_research_system_prompt,
    normalize_deep_research_max_iterations,
    resolve_deep_research_loop_limits,
)


@deal.post(lambda r: 6 <= r <= 48)
def _contract_normalize_deep_research_max_iterations(raw_value: str | None) -> int:
    return normalize_deep_research_max_iterations(raw_value)


@deal.post(lambda r: 6 <= r.max_iterations <= 48)
@deal.post(lambda r: 1 <= r.max_research_passes <= 3)
@deal.post(lambda r: 1 <= r.max_report_attempts <= 2)
@deal.ensure(
    lambda raw_value, result: (
        result.max_research_passes + result.max_report_attempts + 1
    ) <= result.max_iterations
)
def _contract_resolve_deep_research_loop_limits(
    raw_value: str | None,
) -> DeepResearchLoopLimits:
    return resolve_deep_research_loop_limits(raw_value)


def test_normalize_deep_research_max_iterations_defaults_to_24() -> None:
    assert _contract_normalize_deep_research_max_iterations(None) == 24
    assert _contract_normalize_deep_research_max_iterations("") == 24
    assert _contract_normalize_deep_research_max_iterations("invalid") == 24


def test_normalize_deep_research_max_iterations_clamps_bounds() -> None:
    assert _contract_normalize_deep_research_max_iterations("1") == 6
    assert _contract_normalize_deep_research_max_iterations("96") == 48


def test_resolve_deep_research_loop_limits_supports_default_guardrails() -> None:
    limits = _contract_resolve_deep_research_loop_limits("24")
    assert limits.max_iterations == 24
    assert limits.max_research_passes == 3
    assert limits.max_report_attempts == 2
    assert limits.max_research_passes + limits.max_report_attempts + 1 <= limits.max_iterations


def test_build_deep_research_prompt_injects_loop_limits() -> None:
    prompt = build_deep_research_system_prompt(
        DeepResearchLoopLimits(
            max_iterations=24,
            max_research_passes=3,
            max_report_attempts=2,
        )
    )
    assert "max 24 Iterationen" in prompt
    assert "hoechstens 3x `start_deep_research`" in prompt
    assert "hoechstens 2x `generate_research_report`" in prompt
    assert "{deep_research_max_iterations}" not in prompt


def test_runtime_loop_limits_follow_env_override(monkeypatch) -> None:
    monkeypatch.delenv("DEEP_RESEARCH_MAX_ITERATIONS", raising=False)
    assert DeepResearchAgent._runtime_loop_limits().max_iterations == 24

    monkeypatch.setenv("DEEP_RESEARCH_MAX_ITERATIONS", "18")
    limits = DeepResearchAgent._runtime_loop_limits()
    assert limits.max_iterations == 18
    assert limits.max_research_passes == 2
    assert limits.max_report_attempts == 2


@given(raw_value=st.one_of(st.none(), st.text(min_size=0, max_size=16)))
@settings(max_examples=200)
def test_hypothesis_normalize_deep_research_max_iterations_is_bounded(
    raw_value: str | None,
) -> None:
    result = _contract_normalize_deep_research_max_iterations(raw_value)
    assert 6 <= result <= 48


@given(raw_value=st.one_of(st.none(), st.text(min_size=0, max_size=16)))
@settings(max_examples=200)
def test_hypothesis_resolve_deep_research_loop_limits_stay_consistent(
    raw_value: str | None,
) -> None:
    limits = _contract_resolve_deep_research_loop_limits(raw_value)
    assert 6 <= limits.max_iterations <= 48
    assert 1 <= limits.max_research_passes <= 3
    assert 1 <= limits.max_report_attempts <= 2
    assert limits.max_research_passes + limits.max_report_attempts + 1 <= limits.max_iterations


@given(max_iterations=st.integers(min_value=6, max_value=48))
@settings(max_examples=100)
def test_hypothesis_prompt_builder_eliminates_iteration_placeholders(
    max_iterations: int,
) -> None:
    limits = resolve_deep_research_loop_limits(str(max_iterations))
    prompt = build_deep_research_system_prompt(limits)
    assert "{deep_research_max_iterations}" not in prompt
    assert "{deep_research_max_research_passes}" not in prompt
    assert "{deep_research_max_report_attempts}" not in prompt
    assert f"max {limits.max_iterations} Iterationen" in prompt
