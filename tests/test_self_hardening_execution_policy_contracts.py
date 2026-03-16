from __future__ import annotations

import deal

from orchestration.self_hardening_execution_policy import (
    SelfHardeningExecutionDecision,
    evaluate_self_hardening_execution,
)


@deal.post(lambda r: r.route_target in {"", "development", "self_modify"})
@deal.post(lambda r: r.effective_fix_mode in {"observe_only", "developer_task", "self_modify_safe", "human_only"})
@deal.post(lambda r: r.rollout_stage in {"observe_only", "developer_only", "self_modify_safe"})
def _contract_evaluate_self_hardening_execution(
    requested_fix_mode: str,
    recommended_agent: str,
    target_file_path: str,
    change_type: str,
    rollout_stage: str = "",
) -> SelfHardeningExecutionDecision:
    return evaluate_self_hardening_execution(
        requested_fix_mode=requested_fix_mode,
        recommended_agent=recommended_agent,
        target_file_path=target_file_path,
        change_type=change_type,
        rollout_stage=rollout_stage,
    )


def test_contract_self_hardening_execution_for_allowed_self_modify() -> None:
    result = _contract_evaluate_self_hardening_execution(
        "self_modify_safe",
        "development",
        "tools/deep_research/tool.py",
        "report_quality_guardrails",
    )
    assert result.allow_self_modify is True
    assert result.route_target == "self_modify"


def test_contract_self_hardening_execution_for_blocked_self_modify() -> None:
    result = _contract_evaluate_self_hardening_execution(
        "self_modify_safe",
        "development",
        "agent/agents/executor.py",
        "orchestration_policy",
    )
    assert result.allow_self_modify is False
    assert result.route_target == "development"


def test_contract_self_hardening_execution_observe_rollout_disables_task() -> None:
    result = _contract_evaluate_self_hardening_execution(
        "developer_task",
        "development",
        "agent/base_agent.py",
        "orchestration_policy",
        "observe_only",
    )
    assert result.allow_task is False
