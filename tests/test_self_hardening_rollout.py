from __future__ import annotations

from orchestration.self_hardening_rollout import (
    evaluate_self_hardening_rollout,
    normalize_self_hardening_rollout_stage,
)


def test_normalize_self_hardening_rollout_stage_defaults_to_self_modify_safe() -> None:
    assert normalize_self_hardening_rollout_stage("weird") == "self_modify_safe"


def test_evaluate_self_hardening_rollout_observe_only_disables_task_bridge() -> None:
    decision = evaluate_self_hardening_rollout(
        requested_fix_mode="developer_task",
        rollout_stage="observe_only",
    )
    assert decision.allow_task_bridge is False
    assert decision.effective_fix_mode == "observe_only"


def test_evaluate_self_hardening_rollout_developer_only_degrades_self_modify() -> None:
    decision = evaluate_self_hardening_rollout(
        requested_fix_mode="self_modify_safe",
        rollout_stage="developer_only",
    )
    assert decision.allow_task_bridge is True
    assert decision.allow_self_modify is False
    assert decision.effective_fix_mode == "developer_task"


def test_evaluate_self_hardening_rollout_self_modify_stage_allows_safe_self_modify() -> None:
    decision = evaluate_self_hardening_rollout(
        requested_fix_mode="self_modify_safe",
        rollout_stage="self_modify_safe",
    )
    assert decision.allow_task_bridge is True
    assert decision.allow_self_modify is True
    assert decision.effective_fix_mode == "self_modify_safe"
