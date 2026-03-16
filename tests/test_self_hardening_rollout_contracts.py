from __future__ import annotations

import deal

from orchestration.self_hardening_rollout import (
    SelfHardeningRolloutDecision,
    evaluate_self_hardening_rollout,
    normalize_self_hardening_rollout_stage,
)


@deal.post(lambda r: r in {"observe_only", "developer_only", "self_modify_safe"})
def _contract_normalize_self_hardening_rollout_stage(value: str) -> str:
    return normalize_self_hardening_rollout_stage(value)


@deal.post(
    lambda r: isinstance(r, SelfHardeningRolloutDecision)
    and r.stage in {"observe_only", "developer_only", "self_modify_safe"}
    and r.effective_fix_mode in {"observe_only", "developer_task", "self_modify_safe", "human_only"}
)
@deal.ensure(lambda requested_fix_mode, rollout_stage, result: (normalize_self_hardening_rollout_stage(rollout_stage) != "observe_only") or result.allow_task_bridge is False)
def _contract_evaluate_self_hardening_rollout(
    requested_fix_mode: str,
    rollout_stage: str,
) -> SelfHardeningRolloutDecision:
    return evaluate_self_hardening_rollout(
        requested_fix_mode=requested_fix_mode,
        rollout_stage=rollout_stage,
    )


def test_contract_normalize_self_hardening_rollout_stage() -> None:
    assert _contract_normalize_self_hardening_rollout_stage("observe_only") == "observe_only"


def test_contract_evaluate_self_hardening_rollout_developer_only_degrades_self_modify() -> None:
    decision = _contract_evaluate_self_hardening_rollout("self_modify_safe", "developer_only")
    assert decision.effective_fix_mode == "developer_task"
