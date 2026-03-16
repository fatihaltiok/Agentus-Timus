from __future__ import annotations

import os
from dataclasses import dataclass


_ROLLOUT_STAGES = {"observe_only", "developer_only", "self_modify_safe"}


def normalize_self_hardening_rollout_stage(value: str) -> str:
    normalized = str(value or "").strip().lower()
    if normalized in _ROLLOUT_STAGES:
        return normalized
    return "self_modify_safe"


@dataclass(frozen=True)
class SelfHardeningRolloutDecision:
    stage: str
    allow_task_bridge: bool
    allow_self_modify: bool
    effective_fix_mode: str
    reason: str
    source: str


def get_self_hardening_rollout_stage() -> str:
    return normalize_self_hardening_rollout_stage(
        os.getenv("AUTONOMY_SELF_HARDENING_ROLLOUT_STAGE", "self_modify_safe")
    )


def evaluate_self_hardening_rollout(
    *,
    requested_fix_mode: str,
    rollout_stage: str = "",
) -> SelfHardeningRolloutDecision:
    stage = normalize_self_hardening_rollout_stage(rollout_stage or get_self_hardening_rollout_stage())
    requested = str(requested_fix_mode or "").strip().lower()

    if requested in {"observe_only", "human_only"}:
        return SelfHardeningRolloutDecision(
            stage=stage,
            allow_task_bridge=False,
            allow_self_modify=False,
            effective_fix_mode=requested if requested in {"observe_only", "human_only"} else "observe_only",
            reason="requested_fix_mode",
            source="rollout_stage",
        )

    if stage == "observe_only":
        return SelfHardeningRolloutDecision(
            stage=stage,
            allow_task_bridge=False,
            allow_self_modify=False,
            effective_fix_mode="observe_only",
            reason="rollout_observe_only",
            source="env",
        )

    if stage == "developer_only":
        return SelfHardeningRolloutDecision(
            stage=stage,
            allow_task_bridge=True,
            allow_self_modify=False,
            effective_fix_mode="developer_task",
            reason="rollout_developer_only",
            source="env",
        )

    return SelfHardeningRolloutDecision(
        stage=stage,
        allow_task_bridge=True,
        allow_self_modify=requested == "self_modify_safe",
        effective_fix_mode="self_modify_safe" if requested == "self_modify_safe" else "developer_task",
        reason="rollout_self_modify_safe",
        source="env",
    )
