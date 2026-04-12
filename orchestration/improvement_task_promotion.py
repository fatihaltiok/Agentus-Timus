"""Phase E E2.3: decide which compiled improvement tasks may advance toward E3."""

from __future__ import annotations

from typing import Any, Iterable, Mapping

from orchestration.self_hardening_rollout import evaluate_self_hardening_rollout


_SAFE_E3_CATEGORIES = {"routing", "context", "runtime", "tool", "specialist", "ux_handoff"}
_SELF_MODIFY_TASK_KINDS = {"developer_task", "config_change_candidate", "test_gap"}
_PROMOTION_STATES = {
    "human_only",
    "observe_only",
    "developer_only",
    "deferred_by_rollout",
    "eligible_for_e3",
}


def _text(value: Any, *, limit: int = 160) -> str:
    text = str(value or "").strip()
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "..."


def _list_text(*values: Any, limit: int = 160) -> list[str]:
    items: list[str] = []
    for value in values:
        if isinstance(value, (list, tuple, set)):
            raw_items = value
        elif value:
            raw_items = [value]
        else:
            raw_items = []
        for raw in raw_items:
            text = _text(raw, limit=limit)
            if text and text not in items:
                items.append(text)
    return items


def _evidence(task: Mapping[str, Any]) -> Mapping[str, Any]:
    payload = task.get("evidence")
    return payload if isinstance(payload, Mapping) else {}


def _has_strong_evidence(task: Mapping[str, Any]) -> bool:
    evidence = _evidence(task)
    freshness = _text(evidence.get("freshness_state"), limit=32).lower()
    if freshness == "stale":
        return False
    verified_paths = _list_text(evidence.get("verified_paths"))
    verified_functions = _list_text(evidence.get("verified_functions"))
    event_types = _list_text(evidence.get("event_types"))
    try:
        source_count = max(1, int(evidence.get("source_count") or 1))
    except Exception:
        source_count = 1
    try:
        occurrence_count = max(1, int(evidence.get("occurrence_count") or 1))
    except Exception:
        occurrence_count = 1

    if verified_paths or verified_functions:
        return True
    if source_count >= 2:
        return True
    if occurrence_count >= 3 and freshness in {"", "fresh", "aging"}:
        return True
    if len(event_types) >= 2 and freshness in {"fresh", "aging"}:
        return True
    return False


def _requested_fix_mode(task: Mapping[str, Any]) -> tuple[str, list[str], list[str]]:
    task_kind = _text(task.get("task_kind"), limit=64).lower()
    category = _text(task.get("category"), limit=64).lower()
    rollback_risk = _text(task.get("rollback_risk"), limit=32).lower()
    safe_fix_class = _text(task.get("safe_fix_class"), limit=64).lower()
    target_files = _list_text(task.get("target_files"))
    reasons: list[str] = []
    blocked_by: list[str] = []

    if task_kind == "do_not_autofix":
        blocked_by.append("sensitive_or_human_mediated")
        reasons.append("task_kind_do_not_autofix")
        return "human_only", reasons, blocked_by

    if task_kind == "verification_needed":
        blocked_by.append("needs_stronger_evidence")
        reasons.append("task_kind_verification_needed")
        return "observe_only", reasons, blocked_by

    if task_kind == "shell_task":
        blocked_by.append("shell_execution_not_in_e3_safe_subset")
        reasons.append("task_kind_shell_task")
        return "developer_task", reasons, blocked_by

    if task_kind not in _SELF_MODIFY_TASK_KINDS:
        blocked_by.append("task_kind_not_promotable")
        reasons.append("task_kind_outside_self_modify_subset")
        return "developer_task", reasons, blocked_by

    if category not in _SAFE_E3_CATEGORIES:
        blocked_by.append("category_outside_e3_safe_subset")
        reasons.append(f"category:{category or 'runtime'}")
        return "developer_task", reasons, blocked_by

    if rollback_risk == "high":
        blocked_by.append("rollback_risk_high")
        reasons.append("rollback_risk_high")
        return "developer_task", reasons, blocked_by

    if safe_fix_class in {"human_mediated_only", "needs_stronger_evidence"}:
        blocked_by.append(f"safe_fix_class:{safe_fix_class or 'unknown'}")
        reasons.append("safe_fix_class_not_promotable")
        return "developer_task", reasons, blocked_by

    if not target_files:
        blocked_by.append("no_target_files")
        reasons.append("missing_target_files")
        return "developer_task", reasons, blocked_by

    if not _has_strong_evidence(task):
        blocked_by.append("insufficient_compiler_evidence")
        reasons.append("evidence_not_strong_enough")
        return "developer_task", reasons, blocked_by

    reasons.append("safe_subset_and_strong_evidence")
    return "self_modify_safe", reasons, blocked_by


def evaluate_compiled_task_promotion(
    task: Mapping[str, Any],
    *,
    rollout_stage: str = "",
) -> dict[str, Any]:
    requested_fix_mode, reasons, blocked_by = _requested_fix_mode(task)
    rollout = evaluate_self_hardening_rollout(
        requested_fix_mode=requested_fix_mode,
        rollout_stage=rollout_stage,
    )
    effective_fix_mode = str(rollout.effective_fix_mode or "observe_only")
    e3_eligible = requested_fix_mode == "self_modify_safe"
    e3_ready = e3_eligible and effective_fix_mode == "self_modify_safe"

    if requested_fix_mode == "human_only":
        promotion_state = "human_only"
    elif effective_fix_mode == "observe_only":
        promotion_state = "observe_only"
        if requested_fix_mode == "self_modify_safe":
            blocked_by = [*blocked_by, f"rollout_stage:{rollout.stage}"]
    elif e3_ready:
        promotion_state = "eligible_for_e3"
    elif requested_fix_mode == "self_modify_safe":
        promotion_state = "deferred_by_rollout"
        blocked_by = [*blocked_by, f"rollout_stage:{rollout.stage}"]
    else:
        promotion_state = "developer_only"

    if promotion_state not in _PROMOTION_STATES:
        promotion_state = "observe_only"

    return {
        "task_id": _text(task.get("task_id"), limit=80),
        "candidate_id": _text(task.get("candidate_id"), limit=80),
        "title": _text(task.get("title"), limit=120),
        "category": _text(task.get("category"), limit=64),
        "task_kind": _text(task.get("task_kind"), limit=64),
        "priority_score": round(float(task.get("priority_score") or 0.0), 3),
        "requested_fix_mode": requested_fix_mode,
        "effective_fix_mode": effective_fix_mode,
        "promotion_state": promotion_state,
        "e3_eligible": e3_eligible,
        "e3_ready": e3_ready,
        "rollout_stage": str(rollout.stage),
        "allow_task_bridge": bool(rollout.allow_task_bridge),
        "allow_self_modify": bool(rollout.allow_self_modify),
        "promotion_reasons": reasons,
        "blocked_by": blocked_by,
    }


def evaluate_compiled_task_promotions(
    tasks: Iterable[Mapping[str, Any]],
    *,
    limit: int | None = None,
    rollout_stage: str = "",
) -> list[dict[str, Any]]:
    decisions = [
        evaluate_compiled_task_promotion(task, rollout_stage=rollout_stage)
        for task in tasks
    ]
    if limit is None:
        return decisions
    return decisions[: max(0, int(limit))]
