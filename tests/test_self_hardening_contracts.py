from __future__ import annotations

import deal

from orchestration.self_hardening_engine import (
    HardeningProposal,
    SelfHardeningEngine,
    _normalize_fix_mode,
    _priority_for_hardening_severity,
    _should_bridge_fix_mode,
)


@deal.post(lambda r: r in {"observe_only", "developer_task", "self_modify_safe", "human_only"})
def _contract_normalize_fix_mode(raw: str) -> str:
    return _normalize_fix_mode(raw)


@deal.post(lambda r: isinstance(r, bool))
@deal.ensure(
    lambda fix_mode, result: result
    == (_normalize_fix_mode(fix_mode) in {"developer_task", "self_modify_safe"})
)
def _contract_should_bridge_fix_mode(fix_mode: str) -> bool:
    return _should_bridge_fix_mode(fix_mode)


@deal.post(lambda r: r in {1, 2, 3})
def _contract_priority_for_hardening_severity(severity: str) -> int:
    return _priority_for_hardening_severity(severity)


@deal.post(lambda r: r.get("source") == "self_hardening")
@deal.post(lambda r: r.get("fix_mode") in {"observe_only", "developer_task", "self_modify_safe", "human_only"})
@deal.post(lambda r: isinstance(r.get("hardening_dedup_key"), str) and bool(r.get("hardening_dedup_key")))
@deal.post(lambda r: isinstance(r.get("sample_lines"), list))
def _contract_build_hardening_task_metadata(goal_id: str) -> dict:
    proposal = HardeningProposal(
        pattern_name="executor_fallback_triggered",
        component="agent.agents.executor",
        suggestion="topic_recall-Fallback haerten",
        severity="medium",
        fix_mode="self_modify_safe",
        recommended_agent="development",
        verification_hint="py_compile + pytest tests/test_executor_smalltalk.py",
        occurrences=4,
        sample_lines=["executor fallback"],
    )
    return SelfHardeningEngine._build_hardening_task_metadata(proposal, goal_id=goal_id)


def test_contract_normalize_fix_mode():
    assert _contract_normalize_fix_mode("SELF_MODIFY_SAFE") == "self_modify_safe"


def test_contract_should_bridge_fix_mode():
    assert _contract_should_bridge_fix_mode("developer_task") is True
    assert _contract_should_bridge_fix_mode("observe_only") is False


def test_contract_priority_for_hardening_severity():
    assert _contract_priority_for_hardening_severity("high") == 1


def test_contract_build_hardening_task_metadata():
    result = _contract_build_hardening_task_metadata("goal-123")
    assert result["goal_id"] == "goal-123"
