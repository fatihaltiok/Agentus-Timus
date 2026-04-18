"""Z5 runtime plan progression and bounded replanning for Meta execution plans."""

from __future__ import annotations

from typing import Any, Mapping

from orchestration.meta_plan_compiler import parse_meta_execution_plan


_RESOLVED_STEP_STATUSES = {"completed", "skipped", "cancelled"}
_ACTIVE_PLAN_STATUSES = {"active", "blocked", "completed"}
_STEP_SIGNALS = {"step_completed", "step_blocked", "step_unnecessary", "goal_satisfied"}


def _clean_text(value: Any, *, limit: int = 220) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "..."


def _normalize_plan_status(value: Any, *, fallback: str = "active") -> str:
    status = _clean_text(value, limit=32).lower()
    if status in _ACTIVE_PLAN_STATUSES:
        return status
    return fallback


def _normalize_step_status(value: Any) -> str:
    status = _clean_text(value, limit=32).lower()
    if not status:
        return "pending"
    return status


def _resolve_step_index(
    steps: list[dict[str, Any]],
    *,
    plan_step_id: str = "",
    stage_id: str = "",
    next_step_id: str = "",
) -> int:
    normalized_plan_step_id = _clean_text(plan_step_id, limit=64).lower()
    normalized_stage_id = _clean_text(stage_id, limit=64)
    normalized_next_step_id = _clean_text(next_step_id, limit=64).lower()

    for idx, step in enumerate(steps):
        if normalized_plan_step_id and _clean_text(step.get("id"), limit=64).lower() == normalized_plan_step_id:
            return idx
    for idx, step in enumerate(steps):
        if normalized_stage_id and _clean_text(step.get("recipe_stage_id"), limit=64) == normalized_stage_id:
            return idx
    for idx, step in enumerate(steps):
        if normalized_next_step_id and _clean_text(step.get("id"), limit=64).lower() == normalized_next_step_id:
            return idx
    for idx, step in enumerate(steps):
        if _normalize_step_status(step.get("status")) not in _RESOLVED_STEP_STATUSES:
            return idx
    return -1


def _dependencies_satisfied(step: Mapping[str, Any], resolved_ids: set[str]) -> bool:
    depends_on = [
        _clean_text(item, limit=64).lower()
        for item in (step.get("depends_on") or [])
        if _clean_text(item, limit=64)
    ]
    return all(item in resolved_ids for item in depends_on)


def _resolve_next_pending_step_id(steps: list[dict[str, Any]]) -> str:
    resolved_ids = {
        _clean_text(step.get("id"), limit=64).lower()
        for step in steps
        if _normalize_step_status(step.get("status")) in _RESOLVED_STEP_STATUSES
    }
    for step in steps:
        step_id = _clean_text(step.get("id"), limit=64).lower()
        step_status = _normalize_step_status(step.get("status"))
        if not step_id or step_status in _RESOLVED_STEP_STATUSES:
            continue
        if _dependencies_satisfied(step, resolved_ids):
            return step_id
    return ""


def _build_runtime_plan(
    parsed_plan: Mapping[str, Any],
    raw_plan: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    raw = dict(raw_plan or {})
    steps = [dict(step) for step in (parsed_plan.get("steps") or [])]
    fallback_status = "completed" if not steps else ("blocked" if parsed_plan.get("blocked_by") else "active")
    metadata = dict(parsed_plan.get("metadata") or {})
    metadata["step_count"] = len(steps)
    return {
        **dict(parsed_plan),
        "steps": steps,
        "status": _normalize_plan_status(raw.get("status"), fallback=fallback_status),
        "last_completed_step_id": _clean_text(raw.get("last_completed_step_id"), limit=64).lower(),
        "last_completed_step_title": _clean_text(raw.get("last_completed_step_title"), limit=180),
        "metadata": metadata,
    }


def advance_meta_execution_plan(
    plan: Mapping[str, Any] | None,
    *,
    stage_id: Any = "",
    plan_step_id: Any = "",
    stage_status: Any = "",
    specialist_step_signal: Any = "",
    specialist_step_reason: Any = "",
) -> tuple[dict[str, Any], dict[str, Any]]:
    parsed = parse_meta_execution_plan(plan or {})
    if not parsed:
        return {}, {"applied": False, "state": "no_plan"}

    runtime_plan = _build_runtime_plan(parsed, plan)
    steps = runtime_plan["steps"]
    if not steps:
        runtime_plan["status"] = "completed"
        return runtime_plan, {
            "applied": True,
            "state": "completed",
            "plan_status": "completed",
            "next_step_id": "",
            "goal_satisfied": False,
        }

    signal = _clean_text(specialist_step_signal, limit=48).lower()
    if signal not in _STEP_SIGNALS:
        normalized_stage_status = _clean_text(stage_status, limit=32).lower()
        if normalized_stage_status in {"success", "skipped"}:
            signal = "step_completed" if normalized_stage_status == "success" else "step_unnecessary"
        elif normalized_stage_status in {"partial", "error"}:
            signal = "step_blocked"
        else:
            signal = ""

    target_index = _resolve_step_index(
        steps,
        plan_step_id=_clean_text(plan_step_id, limit=64),
        stage_id=_clean_text(stage_id, limit=64),
        next_step_id=runtime_plan.get("next_step_id"),
    )
    if target_index < 0:
        return runtime_plan, {"applied": False, "state": "no_matching_step"}

    target_step = steps[target_index]
    target_step_id = _clean_text(target_step.get("id"), limit=64).lower()
    target_title = _clean_text(target_step.get("title"), limit=180)
    reason = _clean_text(specialist_step_reason, limit=120).lower().replace(" ", "_")
    summary = {
        "applied": True,
        "signal": signal or "",
        "reason": reason,
        "plan_id": _clean_text(runtime_plan.get("plan_id"), limit=64),
        "plan_status": _normalize_plan_status(runtime_plan.get("status")),
        "last_completed_step_id": _clean_text(runtime_plan.get("last_completed_step_id"), limit=64).lower(),
        "next_step_id": _clean_text(runtime_plan.get("next_step_id"), limit=64).lower(),
        "goal_satisfied": False,
        "replanned": False,
        "state": "unchanged",
    }

    if signal == "goal_satisfied":
        target_step["status"] = "completed"
        runtime_plan["last_completed_step_id"] = target_step_id
        runtime_plan["last_completed_step_title"] = target_title
        for step in steps:
            if _normalize_step_status(step.get("status")) not in _RESOLVED_STEP_STATUSES:
                step["status"] = "cancelled"
        runtime_plan["blocked_by"] = []
        runtime_plan["next_step_id"] = ""
        runtime_plan["status"] = "completed"
        summary.update(
            {
                "state": "goal_satisfied",
                "plan_status": "completed",
                "last_completed_step_id": target_step_id,
                "next_step_id": "",
                "goal_satisfied": True,
                "replanned": True,
            }
        )
        return runtime_plan, summary

    if signal == "step_unnecessary":
        target_step["status"] = "skipped"
        runtime_plan["blocked_by"] = []
        next_step_id = _resolve_next_pending_step_id(steps)
        runtime_plan["next_step_id"] = next_step_id
        runtime_plan["status"] = "completed" if not next_step_id else "active"
        summary.update(
            {
                "state": "step_skipped",
                "plan_status": runtime_plan["status"],
                "next_step_id": next_step_id,
                "replanned": True,
            }
        )
        return runtime_plan, summary

    if signal == "step_blocked":
        target_step["status"] = "blocked"
        blocker = reason or _clean_text(stage_id, limit=64).lower() or "step_blocked"
        runtime_plan["blocked_by"] = [blocker]
        runtime_plan["next_step_id"] = target_step_id or _clean_text(runtime_plan.get("next_step_id"), limit=64).lower()
        runtime_plan["status"] = "blocked"
        summary.update(
            {
                "state": "blocked",
                "plan_status": "blocked",
                "next_step_id": runtime_plan["next_step_id"],
                "replanned": False,
            }
        )
        return runtime_plan, summary

    target_step["status"] = "completed"
    runtime_plan["last_completed_step_id"] = target_step_id
    runtime_plan["last_completed_step_title"] = target_title
    runtime_plan["blocked_by"] = []
    next_step_id = _resolve_next_pending_step_id(steps)
    runtime_plan["next_step_id"] = next_step_id
    runtime_plan["status"] = "completed" if not next_step_id else "active"
    summary.update(
        {
            "state": "advanced" if next_step_id else "completed",
            "plan_status": runtime_plan["status"],
            "last_completed_step_id": target_step_id,
            "next_step_id": next_step_id,
            "replanned": bool(next_step_id != target_step_id),
        }
    )
    return runtime_plan, summary


def insert_runtime_stage_into_meta_execution_plan(
    plan: Mapping[str, Any] | None,
    runtime_stage: Mapping[str, Any] | None,
    *,
    before_step_id: Any = "",
    depends_on_step_id: Any = "",
) -> tuple[dict[str, Any], dict[str, Any]]:
    parsed = parse_meta_execution_plan(plan or {})
    stage = dict(runtime_stage or {})
    if not parsed or not stage:
        return {}, {"applied": False, "state": "no_plan"}

    runtime_plan = _build_runtime_plan(parsed, plan)
    steps = runtime_plan["steps"]
    stage_id = _clean_text(stage.get("stage_id"), limit=64).lower().replace(" ", "_")
    if not stage_id:
        return runtime_plan, {"applied": False, "state": "missing_stage_id"}
    if any(_clean_text(step.get("recipe_stage_id"), limit=64).lower() == stage_id for step in steps):
        return runtime_plan, {
            "applied": False,
            "state": "already_present",
            "plan_status": _normalize_plan_status(runtime_plan.get("status")),
            "next_step_id": _clean_text(runtime_plan.get("next_step_id"), limit=64).lower(),
        }

    agent = _clean_text(stage.get("agent"), limit=48).lower() or "meta"
    step_kind = "delivery" if agent in {"document", "communication"} else "research" if agent == "research" else (
        "plan" if agent == "meta" else "execution"
    )
    completion_signals = ["step_completed"]
    if "verify" in stage_id or "validation" in stage_id:
        completion_signals = ["verification_passed", "step_completed"]

    step_payload = {
        "id": stage_id,
        "title": _clean_text(stage.get("goal") or stage.get("expected_output") or stage_id, limit=180),
        "step_kind": step_kind,
        "assigned_agent": agent,
        "status": "pending",
        "depends_on": [_clean_text(depends_on_step_id, limit=64).lower()] if _clean_text(depends_on_step_id, limit=64) else [],
        "optional": bool(stage.get("optional")),
        "completion_signals": completion_signals,
        "recipe_stage_id": _clean_text(stage.get("stage_id"), limit=64),
        "expected_output": _clean_text(stage.get("expected_output"), limit=160),
        "source_subtask_id": "",
        "delegation_mode": "runtime_replan",
    }

    insert_index = len(steps)
    normalized_before_step_id = _clean_text(before_step_id, limit=64).lower()
    if normalized_before_step_id:
        for idx, step in enumerate(steps):
            if _clean_text(step.get("id"), limit=64).lower() == normalized_before_step_id:
                insert_index = idx
                break
    steps.insert(insert_index, step_payload)
    runtime_plan["metadata"]["step_count"] = len(steps)
    runtime_plan["next_step_id"] = stage_id if normalized_before_step_id or not runtime_plan.get("next_step_id") else _clean_text(runtime_plan.get("next_step_id"), limit=64).lower()
    runtime_plan["status"] = "active"
    runtime_plan["blocked_by"] = []
    return runtime_plan, {
        "applied": True,
        "state": "runtime_stage_inserted",
        "plan_status": "active",
        "inserted_step_id": stage_id,
        "next_step_id": _clean_text(runtime_plan.get("next_step_id"), limit=64).lower(),
        "replanned": True,
    }
