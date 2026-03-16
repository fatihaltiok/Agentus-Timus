from __future__ import annotations

from dataclasses import dataclass

from orchestration.self_modification_policy import evaluate_self_modification_policy
from orchestration.self_hardening_rollout import evaluate_self_hardening_rollout


_FIX_MODES = {"observe_only", "developer_task", "self_modify_safe", "human_only"}


def _normalize_text(value: str) -> str:
    return str(value or "").strip()


def _normalize_fix_mode(value: str) -> str:
    normalized = _normalize_text(value).lower()
    return normalized if normalized in _FIX_MODES else "observe_only"


@dataclass(frozen=True)
class SelfHardeningExecutionDecision:
    requested_fix_mode: str
    effective_fix_mode: str
    allow_task: bool
    allow_self_modify: bool
    route_target: str
    reason: str
    rollout_stage: str = ""
    rollout_reason: str = ""
    target_file_path: str = ""
    change_type: str = ""
    required_test_targets: tuple[str, ...] = ()
    required_checks: tuple[str, ...] = ()


def evaluate_self_hardening_execution(
    *,
    requested_fix_mode: str,
    recommended_agent: str,
    target_file_path: str = "",
    change_type: str = "auto",
    rollout_stage: str = "",
) -> SelfHardeningExecutionDecision:
    normalized_mode = _normalize_fix_mode(requested_fix_mode)
    safe_agent = _normalize_text(recommended_agent).lower() or "development"
    safe_path = _normalize_text(target_file_path)
    safe_change_type = _normalize_text(change_type) or "auto"
    rollout = evaluate_self_hardening_rollout(
        requested_fix_mode=normalized_mode,
        rollout_stage=rollout_stage,
    )

    if not rollout.allow_task_bridge:
        return SelfHardeningExecutionDecision(
            requested_fix_mode=normalized_mode,
            effective_fix_mode=rollout.effective_fix_mode,
            allow_task=False,
            allow_self_modify=False,
            route_target="",
            reason="no_task_bridge" if normalized_mode in {"observe_only", "human_only"} else rollout.reason,
            rollout_stage=rollout.stage,
            rollout_reason=rollout.reason,
            target_file_path=safe_path,
            change_type=safe_change_type,
        )

    if rollout.effective_fix_mode == "developer_task":
        return SelfHardeningExecutionDecision(
            requested_fix_mode=normalized_mode,
            effective_fix_mode="developer_task",
            allow_task=True,
            allow_self_modify=False,
            route_target=safe_agent,
            reason="developer_task" if normalized_mode == "developer_task" else rollout.reason,
            rollout_stage=rollout.stage,
            rollout_reason=rollout.reason,
            target_file_path=safe_path,
            change_type=safe_change_type,
        )

    if not safe_path:
        return SelfHardeningExecutionDecision(
            requested_fix_mode=normalized_mode,
            effective_fix_mode="developer_task",
            allow_task=True,
            allow_self_modify=False,
            route_target=safe_agent,
            reason="self_modify_missing_target_file",
            rollout_stage=rollout.stage,
            rollout_reason=rollout.reason,
            target_file_path=safe_path,
            change_type=safe_change_type,
        )

    policy = evaluate_self_modification_policy(safe_path, change_type=safe_change_type)
    if not policy.allowed:
        return SelfHardeningExecutionDecision(
            requested_fix_mode=normalized_mode,
            effective_fix_mode="developer_task",
            allow_task=True,
            allow_self_modify=False,
            route_target=safe_agent,
            reason=f"self_modify_policy_blocked:{policy.reason}",
            rollout_stage=rollout.stage,
            rollout_reason=rollout.reason,
            target_file_path=safe_path,
            change_type=safe_change_type,
            required_test_targets=policy.required_test_targets,
            required_checks=policy.required_checks,
        )

    if policy.require_approval:
        return SelfHardeningExecutionDecision(
            requested_fix_mode=normalized_mode,
            effective_fix_mode="developer_task",
            allow_task=True,
            allow_self_modify=False,
            route_target=safe_agent,
            reason="self_modify_requires_approval",
            rollout_stage=rollout.stage,
            rollout_reason=rollout.reason,
            target_file_path=safe_path,
            change_type=safe_change_type,
            required_test_targets=policy.required_test_targets,
            required_checks=policy.required_checks,
        )

    return SelfHardeningExecutionDecision(
        requested_fix_mode=normalized_mode,
        effective_fix_mode="self_modify_safe",
        allow_task=True,
        allow_self_modify=True,
        route_target="self_modify",
        reason="self_modify_allowed",
        rollout_stage=rollout.stage,
        rollout_reason=rollout.reason,
        target_file_path=safe_path,
        change_type=safe_change_type,
        required_test_targets=policy.required_test_targets,
        required_checks=policy.required_checks,
    )
