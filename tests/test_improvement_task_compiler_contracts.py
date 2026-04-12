from __future__ import annotations

import deal
from hypothesis import given, settings
from hypothesis import strategies as st

from orchestration.improvement_task_compiler import (
    compile_improvement_task,
    compile_improvement_tasks,
)


_CATEGORIES = {"routing", "context", "policy", "runtime", "tool", "specialist", "memory", "ux_handoff"}
_TASK_KINDS = {"developer_task", "shell_task", "config_change_candidate", "test_gap", "verification_needed", "do_not_autofix"}
_EXECUTION_HINTS = {"developer_task", "observe_only", "human_only"}
_FRESHNESS_STATES = {"", "fresh", "aging", "stale"}
_ROLLBACK_RISKS = {"low", "medium", "high"}


@deal.pre(lambda category, *_: category in _CATEGORIES)
@deal.pre(lambda _, __, ___, ____, source_count, freshness_state, _____: source_count >= 1 and freshness_state in _FRESHNESS_STATES)
@deal.post(lambda r: r in _TASK_KINDS)
def _contract_task_kind(
    category: str,
    target: str,
    problem: str,
    action: str,
    source_count: int,
    freshness_state: str,
    event_type: str,
) -> str:
    return compile_improvement_task(
        {
            "candidate_id": "contract:kind",
            "category": category,
            "target": target,
            "problem": problem,
            "proposed_action": action,
            "source_count": source_count,
            "freshness_state": freshness_state,
            "event_type": event_type,
        }
    )["task_kind"]


@deal.pre(lambda category, *_: category in _CATEGORIES)
@deal.post(lambda r: 0 <= r <= 4)
def _contract_target_file_count(
    category: str,
    target: str,
    problem: str,
    action: str,
) -> int:
    return len(
        compile_improvement_task(
            {
                "candidate_id": "contract:files",
                "category": category,
                "target": target,
                "problem": problem,
                "proposed_action": action,
            }
        )["target_files"]
    )


@deal.pre(lambda left, right: left >= 0.0 and right >= 0.0)
@deal.post(lambda r: r in {0, 1})
def _contract_priority_order(left: float, right: float) -> int:
    compiled = compile_improvement_tasks(
        [
            {"candidate_id": "left", "category": "runtime", "problem": "A", "proposed_action": "B", "priority_score": left},
            {"candidate_id": "right", "category": "runtime", "problem": "C", "proposed_action": "D", "priority_score": right},
        ]
    )
    return 1 if float(compiled[0].get("priority_score") or 0.0) >= float(compiled[1].get("priority_score") or 0.0) else 0


@deal.pre(lambda category, *_: category in _CATEGORIES)
@deal.post(lambda r: r in _EXECUTION_HINTS)
def _contract_execution_hint(category: str, problem: str, action: str) -> str:
    return compile_improvement_task(
        {
            "candidate_id": "contract:hint",
            "category": category,
            "problem": problem,
            "proposed_action": action,
        }
    )["execution_mode_hint"]


@deal.pre(lambda category, *_: category in _CATEGORIES)
@deal.post(lambda r: r in _ROLLBACK_RISKS)
def _contract_rollback_risk(category: str, problem: str, action: str) -> str:
    return compile_improvement_task(
        {
            "candidate_id": "contract:risk",
            "category": category,
            "problem": problem,
            "proposed_action": action,
        }
    )["rollback_risk"]


@given(
    category=st.sampled_from(["routing", "context", "policy", "runtime", "tool", "specialist", "memory", "ux_handoff"]),
    target=st.text(min_size=0, max_size=40),
    problem=st.text(min_size=1, max_size=120),
    action=st.text(min_size=1, max_size=120),
    priority=st.floats(min_value=0.0, max_value=2.0, allow_nan=False, allow_infinity=False),
)
@settings(max_examples=60)
def test_hypothesis_compile_improvement_task_returns_bounded_shape(category, target, problem, action, priority):
    result = compile_improvement_task(
        {
            "candidate_id": "hypo:1",
            "category": category,
            "target": target,
            "problem": problem,
            "proposed_action": action,
            "priority_score": priority,
        }
    )
    assert _contract_task_kind(category, target, problem, action, 1, "", "") in _TASK_KINDS
    assert isinstance(result["title"], str)
    assert len(result["target_files"]) <= 4


@given(
    left=st.floats(min_value=0.0, max_value=2.0, allow_nan=False, allow_infinity=False),
    right=st.floats(min_value=0.0, max_value=2.0, allow_nan=False, allow_infinity=False),
)
@settings(max_examples=60)
def test_hypothesis_compile_improvement_tasks_keeps_descending_priority(left, right):
    result = compile_improvement_tasks(
        [
            {"candidate_id": "left", "category": "runtime", "problem": "A", "proposed_action": "B", "priority_score": left},
            {"candidate_id": "right", "category": "runtime", "problem": "C", "proposed_action": "D", "priority_score": right},
        ]
    )
    assert _contract_priority_order(left, right) == 1
    assert len(result) == 2
