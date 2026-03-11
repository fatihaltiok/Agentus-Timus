"""Contracts for structured browser workflow planning."""

from __future__ import annotations

import deal
from hypothesis import given, settings
from hypothesis import strategies as st

from orchestration.browser_workflow_plan import (
    build_browser_workflow_plan,
    build_structured_browser_workflow_plan,
)


@deal.post(lambda r: len(r) >= 1)
@deal.post(lambda r: r[-1] == "Beende Task und berichte Ergebnisse")
def _contract_build_browser_workflow_plan(task: str, url: str) -> list[str]:
    return build_browser_workflow_plan(task, url)


@given(st.text(max_size=120), st.text(max_size=80))
@settings(max_examples=60)
def test_hypothesis_browser_workflow_plan_has_terminal_step(task: str, url: str):
    steps = _contract_build_browser_workflow_plan(task, url)
    assert steps[-1] == "Beende Task und berichte Ergebnisse"


@deal.post(lambda r: len(r.steps) >= 1)
@deal.post(lambda r: all(step.success_signal for step in r.steps))
def _contract_build_structured_browser_workflow_plan(task: str, url: str):
    return build_structured_browser_workflow_plan(task, url)


@given(st.text(max_size=120), st.text(max_size=80))
@settings(max_examples=60)
def test_hypothesis_structured_browser_workflow_plan_has_success_signals(task: str, url: str):
    plan = _contract_build_structured_browser_workflow_plan(task, url)
    assert plan.steps
    assert all(step.success_signal for step in plan.steps)
