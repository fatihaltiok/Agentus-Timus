"""Phase E E3.1: bridge E2 task promotions into self-hardening execution preflight."""

from __future__ import annotations

from typing import Any, Iterable, Mapping

from orchestration.self_hardening_execution_policy import evaluate_self_hardening_execution


_BRIDGE_STATES = {
    "not_e3_eligible",
    "deferred_by_promotion",
    "developer_bridge_ready",
    "self_modify_ready",
    "bridge_blocked",
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


def _target_file_path(task: Mapping[str, Any]) -> str:
    evidence = _evidence(task)
    verified = _list_text(evidence.get("verified_paths"))
    if verified:
        return verified[0]
    targets = _list_text(task.get("target_files"), evidence.get("resolved_target_files"))
    return targets[0] if targets else ""


def _change_type_for_task(task: Mapping[str, Any], target_file_path: str) -> str:
    path = _text(target_file_path, limit=200)
    if not path:
        return "auto"
    if path == "agent/prompts.py":
        return "prompt_policy"
    if path.startswith("orchestration/meta_") or path == "orchestration/orchestration_policy.py":
        return "orchestration_policy"
    if path.startswith("orchestration/browser_workflow_"):
        return "orchestration_policy"
    if path == "tools/deep_research/tool.py":
        return "report_quality_guardrails"
    if path.startswith("tests/test_"):
        return "evaluation_tests"
    if path.startswith("docs/") and path.endswith(".md"):
        return "documentation"

    safe_fix_class = _text(task.get("safe_fix_class"), limit=96).lower()
    if safe_fix_class == "regression_test_expansion":
        return "evaluation_tests"
    if safe_fix_class in {
        "routing_policy_hardening",
        "state_binding_hardening",
        "runtime_guard_hardening",
        "specialist_alignment_hardening",
        "workflow_rendering_hardening",
    }:
        return "orchestration_policy"
    return "auto"


def build_improvement_task_bridge(
    task: Mapping[str, Any],
    promotion: Mapping[str, Any],
    *,
    rollout_stage: str = "",
) -> dict[str, Any]:
    target_file_path = _target_file_path(task)
    requested_fix_mode = _text(promotion.get("requested_fix_mode"), limit=64).lower()
    promotion_state = _text(promotion.get("promotion_state"), limit=64).lower()
    change_type = _change_type_for_task(task, target_file_path)

    if not bool(promotion.get("e3_eligible")):
        bridge_state = "not_e3_eligible"
        return {
            "task_id": _text(task.get("task_id"), limit=80),
            "candidate_id": _text(task.get("candidate_id"), limit=80),
            "title": _text(task.get("title"), limit=120),
            "bridge_state": bridge_state,
            "target_file_path": target_file_path,
            "change_type": change_type,
            "requested_fix_mode": requested_fix_mode,
            "effective_fix_mode": _text(promotion.get("effective_fix_mode"), limit=64).lower(),
            "route_target": "",
            "allow_task": False,
            "allow_self_modify": False,
            "reason": "promotion_not_e3_eligible",
            "promotion_state": promotion_state,
            "required_checks": [],
            "required_test_targets": [],
        }

    if not bool(promotion.get("e3_ready")):
        bridge_state = "deferred_by_promotion"
        return {
            "task_id": _text(task.get("task_id"), limit=80),
            "candidate_id": _text(task.get("candidate_id"), limit=80),
            "title": _text(task.get("title"), limit=120),
            "bridge_state": bridge_state,
            "target_file_path": target_file_path,
            "change_type": change_type,
            "requested_fix_mode": requested_fix_mode,
            "effective_fix_mode": _text(promotion.get("effective_fix_mode"), limit=64).lower(),
            "route_target": "",
            "allow_task": False,
            "allow_self_modify": False,
            "reason": f"promotion_state:{promotion_state or 'deferred'}",
            "promotion_state": promotion_state,
            "required_checks": [],
            "required_test_targets": [],
        }

    execution = evaluate_self_hardening_execution(
        requested_fix_mode=requested_fix_mode or "developer_task",
        recommended_agent="development",
        target_file_path=target_file_path,
        change_type=change_type,
        rollout_stage=rollout_stage or _text(promotion.get("rollout_stage"), limit=64),
    )
    if not execution.allow_task:
        bridge_state = "bridge_blocked"
    elif execution.allow_self_modify and execution.route_target == "self_modify":
        bridge_state = "self_modify_ready"
    else:
        bridge_state = "developer_bridge_ready"

    if bridge_state not in _BRIDGE_STATES:
        bridge_state = "bridge_blocked"

    return {
        "task_id": _text(task.get("task_id"), limit=80),
        "candidate_id": _text(task.get("candidate_id"), limit=80),
        "title": _text(task.get("title"), limit=120),
        "bridge_state": bridge_state,
        "target_file_path": target_file_path,
        "change_type": change_type,
        "requested_fix_mode": execution.requested_fix_mode,
        "effective_fix_mode": execution.effective_fix_mode,
        "route_target": execution.route_target,
        "allow_task": bool(execution.allow_task),
        "allow_self_modify": bool(execution.allow_self_modify),
        "reason": execution.reason,
        "promotion_state": promotion_state,
        "required_checks": list(execution.required_checks),
        "required_test_targets": list(execution.required_test_targets),
    }


def build_improvement_task_bridges(
    tasks: Iterable[Mapping[str, Any]],
    promotions: Iterable[Mapping[str, Any]],
    *,
    limit: int | None = None,
    rollout_stage: str = "",
) -> list[dict[str, Any]]:
    decisions_by_task = {
        _text(item.get("task_id"), limit=80): item
        for item in promotions
    }
    bridges: list[dict[str, Any]] = []
    for task in tasks:
        task_id = _text(task.get("task_id"), limit=80)
        promotion = decisions_by_task.get(task_id)
        if promotion is None:
            continue
        bridges.append(build_improvement_task_bridge(task, promotion, rollout_stage=rollout_stage))
    if limit is None:
        return bridges
    return bridges[: max(0, int(limit))]
