"""Phase E E3.3: managed autonomous hardening for safe improvement tasks."""

from __future__ import annotations

import os
from typing import Any, Iterable, Mapping

from orchestration.autonomy_observation import record_autonomy_observation
from orchestration.improvement_task_bridge import build_improvement_task_bridges
from orchestration.improvement_task_compiler import compile_improvement_tasks
from orchestration.improvement_task_execution import (
    build_improvement_hardening_task_payloads,
    enqueue_improvement_hardening_task,
)
from orchestration.improvement_task_promotion import evaluate_compiled_task_promotions
from orchestration.self_hardening_runtime import (
    get_self_hardening_runtime_summary,
    record_self_hardening_event,
)
from orchestration.task_queue import get_queue


_AUTOENQUEUE_STATES = {
    "not_creatable",
    "route_not_autonomous",
    "self_modify_opt_in_required",
    "queue_budget_exhausted",
    "strict_force_off",
    "rollback_active",
    "rollout_frozen",
    "verification_blocked",
    "verification_backpressure",
    "runtime_critical",
    "autoenqueue_ready",
    "enqueue_created",
    "enqueue_deduped",
    "enqueue_cooldown_active",
    "enqueue_blocked",
}


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name, "true" if default else "false").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)).strip())
    except Exception:
        return default


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)).strip())
    except Exception:
        return default


def _is_truthy(value: Any) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _text(value: Any, *, limit: int = 160) -> str:
    text = str(value or "").strip()
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "..."


def _metadata(payload: Mapping[str, Any]) -> Mapping[str, Any]:
    value = payload.get("metadata")
    return value if isinstance(value, Mapping) else {}


def _policy_runtime_state(queue: Any, key: str) -> Mapping[str, Any]:
    getter = getattr(queue, "get_policy_runtime_state", None)
    if not callable(getter):
        return {}
    try:
        value = getter(key)
    except Exception:
        return {}
    return value if isinstance(value, Mapping) else {}


def _runtime_metrics(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _evaluate_verification_backpressure(runtime: Mapping[str, Any]) -> dict[str, Any]:
    metrics = _runtime_metrics(runtime.get("metrics"))
    verified_total = max(0, int(metrics.get("verification_verified_total") or 0))
    blocked_total = max(0, int(metrics.get("verification_blocked_total") or 0))
    rolled_back_total = max(0, int(metrics.get("verification_rolled_back_total") or 0))
    error_total = max(0, int(metrics.get("verification_error_total") or 0))
    negative_total = blocked_total + rolled_back_total + error_total
    sample_total = verified_total + negative_total
    min_sample = max(1, _env_int("AUTONOMY_IMPROVEMENT_VERIFICATION_MIN_SAMPLE", 3))
    min_verified_rate = max(0.0, min(1.0, _env_float("AUTONOMY_IMPROVEMENT_VERIFIED_RATE_MIN", 0.34)))
    max_negative_total = max(1, _env_int("AUTONOMY_IMPROVEMENT_VERIFICATION_NEGATIVE_BUDGET", 2))
    verified_rate = float(verified_total / sample_total) if sample_total > 0 else 0.0
    blocked = bool(
        sample_total >= min_sample
        and negative_total >= max_negative_total
        and verified_rate < min_verified_rate
    )
    reasons: list[str] = []
    if blocked:
        reasons.extend(
            [
                f"verification_sample_total:{sample_total}",
                f"verification_negative_total:{negative_total}",
                f"verification_verified_rate:{verified_rate:.3f}",
            ]
        )
    return {
        "blocked": blocked,
        "reasons": reasons[:3],
        "verified_total": verified_total,
        "blocked_total": blocked_total,
        "rolled_back_total": rolled_back_total,
        "error_total": error_total,
        "negative_total": negative_total,
        "sample_total": sample_total,
        "verified_rate": round(verified_rate, 3),
        "min_sample": min_sample,
        "min_verified_rate": round(min_verified_rate, 3),
        "max_negative_total": max_negative_total,
    }


def get_improvement_task_rollout_guard(queue: Any) -> dict[str, Any]:
    runtime = get_self_hardening_runtime_summary(queue)
    verification_backpressure = _evaluate_verification_backpressure(runtime)
    strict_force_off = _is_truthy(_policy_runtime_state(queue, "strict_force_off").get("state_value"))
    freeze_active = _is_truthy(_policy_runtime_state(queue, "hardening_rollout_freeze").get("state_value"))
    scorecard_last_action = _text(_policy_runtime_state(queue, "scorecard_last_action").get("state_value"), limit=96).lower()
    hardening_last_action = _text(_policy_runtime_state(queue, "hardening_last_action").get("state_value"), limit=96).lower()
    runtime_state = _text(runtime.get("state"), limit=64).lower()
    verification_status = _text(runtime.get("last_verification_status"), limit=64).lower()
    canary_state = _text(runtime.get("last_canary_state"), limit=64).lower()
    state = "allow"
    reasons: list[str] = []

    if strict_force_off:
        state = "strict_force_off"
        reasons.append("policy_runtime:strict_force_off")
    elif "rollback" in scorecard_last_action or "rollback" in hardening_last_action:
        state = "rollback_active"
        reasons.append(f"scorecard_action:{scorecard_last_action or 'n/a'}")
        reasons.append(f"hardening_action:{hardening_last_action or 'n/a'}")
    elif freeze_active or "freeze" in hardening_last_action or scorecard_last_action == "governance_hold":
        state = "rollout_frozen"
        reasons.append("policy_runtime:hardening_rollout_freeze" if freeze_active else "rollout_action:freeze")
    elif verification_status in {"blocked", "rolled_back", "error"} or canary_state in {
        "blocked",
        "rolled_back",
        "error",
        "failed",
    }:
        state = "verification_blocked"
        if verification_status:
            reasons.append(f"verification_status:{verification_status}")
        if canary_state:
            reasons.append(f"canary_state:{canary_state}")
    elif verification_backpressure["blocked"]:
        state = "verification_backpressure"
        reasons.extend(list(verification_backpressure.get("reasons") or [])[:3])
    elif runtime_state == "critical":
        state = "runtime_critical"
        reasons.append("self_hardening_runtime:critical")

    return {
        "state": state,
        "blocked": state != "allow",
        "reasons": reasons[:4],
        "strict_force_off": strict_force_off,
        "freeze_active": freeze_active,
        "scorecard_last_action": scorecard_last_action,
        "hardening_last_action": hardening_last_action,
        "runtime_state": runtime_state,
        "verification_status": verification_status,
        "canary_state": canary_state,
        "verification_backpressure": verification_backpressure,
    }


def build_improvement_task_governance_view(queue: Any | None = None) -> dict[str, Any]:
    active_queue = queue or get_queue()
    rollout_guard = get_improvement_task_rollout_guard(active_queue)
    return {
        "rollout_guard_state": _text(rollout_guard.get("state"), limit=64),
        "rollout_guard_blocked": bool(rollout_guard.get("blocked")),
        "rollout_guard_reasons": [
            _text(item, limit=96)
            for item in (rollout_guard.get("reasons") or [])
            if _text(item, limit=96)
        ][:3],
        "strict_force_off": bool(rollout_guard.get("strict_force_off")),
        "freeze_active": bool(rollout_guard.get("freeze_active")),
        "runtime_state": _text(rollout_guard.get("runtime_state"), limit=64),
        "verification_status": _text(rollout_guard.get("verification_status"), limit=64),
        "canary_state": _text(rollout_guard.get("canary_state"), limit=64),
        "verification_backpressure": dict(rollout_guard.get("verification_backpressure") or {}),
    }


def get_improvement_task_autonomy_settings() -> dict[str, Any]:
    compat_mode = _env_bool("AUTONOMY_COMPAT_MODE", True)
    enabled = (not compat_mode) and _env_bool("AUTONOMY_IMPROVEMENT_AUTOENQUEUE_ENABLED", False)
    max_autoenqueue = max(0, _env_int("AUTONOMY_IMPROVEMENT_AUTOENQUEUE_MAX_TASKS", 1))
    candidate_limit = max(1, _env_int("AUTONOMY_IMPROVEMENT_AUTOENQUEUE_LIMIT", 5))
    allow_self_modify = (
        enabled
        and _env_bool("AUTONOMY_IMPROVEMENT_AUTOENQUEUE_SELF_MODIFY_ENABLED", False)
        and _env_bool("AUTONOMY_SELF_MODIFY_ENABLED", False)
    )
    return {
        "enabled": enabled,
        "allow_self_modify": allow_self_modify,
        "max_autoenqueue": max_autoenqueue,
        "candidate_limit": candidate_limit,
    }


def build_improvement_task_autonomy_decision(
    payload: Mapping[str, Any],
    *,
    rollout_guard: Mapping[str, Any] | None = None,
    allow_self_modify: bool = False,
    enqueued_this_cycle: int = 0,
    max_autoenqueue: int = 1,
) -> dict[str, Any]:
    metadata = _metadata(payload)
    candidate_id = _text(payload.get("candidate_id"), limit=80)
    compiled_task_id = _text(payload.get("compiled_task_id"), limit=80)
    title = _text(metadata.get("title") or payload.get("title"), limit=120)
    category = _text(metadata.get("category"), limit=64)
    target_agent = _text(payload.get("target_agent"), limit=64).lower()
    creation_state = _text(payload.get("creation_state"), limit=64)
    bridge_state = _text(payload.get("bridge_state") or metadata.get("bridge_state"), limit=64)
    requested_fix_mode = _text(metadata.get("requested_fix_mode"), limit=64)
    effective_fix_mode = _text(metadata.get("effective_fix_mode") or metadata.get("execution_mode"), limit=64)
    guard_state = _text((rollout_guard or {}).get("state"), limit=64).lower() or "allow"
    guard_blocked = bool((rollout_guard or {}).get("blocked")) and guard_state != "allow"
    guard_reasons = [
        _text(item, limit=96)
        for item in ((rollout_guard or {}).get("reasons") or [])
        if _text(item, limit=96)
    ]
    reasons: list[str] = []
    blocked_by: list[str] = []

    safe_budget = max(0, int(max_autoenqueue or 0))
    used_budget = max(0, int(enqueued_this_cycle or 0))
    autoenqueue_state = "not_creatable"
    allow_autoenqueue = False

    if creation_state != "task_payload_ready":
        blocked_by.append(f"creation_state:{creation_state or 'unknown'}")
        reasons.append("payload_not_ready")
    elif guard_blocked:
        autoenqueue_state = guard_state
        blocked_by.append(f"rollout_guard:{guard_state}")
        reasons.append("rollout_guard_blocked")
        reasons.extend(guard_reasons[:3])
    elif target_agent == "development":
        reasons.append("development_autonomy_allowed")
        if used_budget >= safe_budget:
            autoenqueue_state = "queue_budget_exhausted"
            blocked_by.append("max_autoenqueue_reached")
        else:
            autoenqueue_state = "autoenqueue_ready"
            allow_autoenqueue = True
    elif target_agent == "self_modify":
        reasons.append("self_modify_route_detected")
        if not allow_self_modify:
            autoenqueue_state = "self_modify_opt_in_required"
            blocked_by.append("self_modify_opt_in_required")
        elif used_budget >= safe_budget:
            autoenqueue_state = "queue_budget_exhausted"
            blocked_by.append("max_autoenqueue_reached")
        else:
            autoenqueue_state = "autoenqueue_ready"
            allow_autoenqueue = True
            reasons.append("self_modify_opt_in_enabled")
    else:
        autoenqueue_state = "route_not_autonomous"
        blocked_by.append(f"target_agent:{target_agent or 'unknown'}")
        reasons.append("target_agent_outside_autonomous_subset")

    if autoenqueue_state not in _AUTOENQUEUE_STATES:
        autoenqueue_state = "enqueue_blocked"
        allow_autoenqueue = False
        blocked_by.append("invalid_autoenqueue_state")

    queue_budget_remaining = max(
        0,
        safe_budget - used_budget - (1 if autoenqueue_state == "autoenqueue_ready" else 0),
    )

    return {
        "candidate_id": candidate_id,
        "compiled_task_id": compiled_task_id,
        "title": title,
        "category": category,
        "creation_state": creation_state,
        "bridge_state": bridge_state,
        "target_agent": target_agent,
        "requested_fix_mode": requested_fix_mode,
        "effective_fix_mode": effective_fix_mode,
        "rollout_guard_state": guard_state,
        "rollout_guard_blocked": guard_blocked,
        "rollout_guard_reasons": guard_reasons[:3],
        "autoenqueue_state": autoenqueue_state,
        "allow_autoenqueue": allow_autoenqueue,
        "allow_self_modify": bool(allow_self_modify),
        "max_autoenqueue": safe_budget,
        "queue_budget_remaining": queue_budget_remaining,
        "priority": int(payload.get("priority") or 2),
        "improvement_dedup_key": _text(metadata.get("improvement_dedup_key"), limit=240),
        "autoenqueue_reasons": reasons,
        "blocked_by": blocked_by,
    }


def build_improvement_task_autonomy_decisions(
    payloads: Iterable[Mapping[str, Any]],
    *,
    rollout_guard: Mapping[str, Any] | None = None,
    allow_self_modify: bool = False,
    max_autoenqueue: int = 1,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    decisions: list[dict[str, Any]] = []
    reserved_budget = 0
    for payload in payloads:
        decision = build_improvement_task_autonomy_decision(
            payload,
            rollout_guard=rollout_guard,
            allow_self_modify=allow_self_modify,
            enqueued_this_cycle=reserved_budget,
            max_autoenqueue=max_autoenqueue,
        )
        decisions.append(decision)
        if decision["autoenqueue_state"] == "autoenqueue_ready":
            reserved_budget += 1
    if limit is None:
        return decisions
    return decisions[: max(0, int(limit))]


def _hardening_metric_increment(target_agent: str, enqueue_status: str) -> dict[str, int]:
    metrics: dict[str, int] = {}
    if enqueue_status == "created":
        metrics["tasks_created_total"] = 1
        if target_agent == "development":
            metrics["developer_tasks_total"] = 1
        elif target_agent == "self_modify":
            metrics["self_modify_tasks_total"] = 1
    elif enqueue_status == "deduped":
        metrics["tasks_deduped_total"] = 1
    return metrics


def _record_improvement_task_autonomy_event(decision: Mapping[str, Any]) -> None:
    payload = {
        "candidate_id": _text(decision.get("candidate_id"), limit=80),
        "compiled_task_id": _text(decision.get("compiled_task_id"), limit=80),
        "target_agent": _text(decision.get("target_agent"), limit=64),
        "creation_state": _text(decision.get("creation_state"), limit=64),
        "bridge_state": _text(decision.get("bridge_state"), limit=64),
        "requested_fix_mode": _text(decision.get("requested_fix_mode"), limit=64),
        "effective_fix_mode": _text(decision.get("effective_fix_mode"), limit=64),
        "rollout_guard_state": _text(decision.get("rollout_guard_state"), limit=64),
        "rollout_guard_blocked": bool(decision.get("rollout_guard_blocked")),
        "autoenqueue_state": _text(decision.get("autoenqueue_state"), limit=64),
        "enqueue_status": _text(decision.get("enqueue_status"), limit=64),
        "enqueue_reason": _text(decision.get("enqueue_reason"), limit=160),
        "enqueued_task_id": _text(decision.get("enqueued_task_id"), limit=80),
        "existing_task_id": _text(decision.get("existing_task_id"), limit=80),
        "cooldown_minutes": int(decision.get("cooldown_minutes") or 0),
        "allow_self_modify": bool(decision.get("allow_self_modify")),
    }
    try:
        record_autonomy_observation("improvement_task_autonomy_event", payload)
    except Exception:
        pass


def _record_improvement_task_hardening_runtime(queue: Any, decision: Mapping[str, Any]) -> None:
    enqueue_status = _text(decision.get("enqueue_status"), limit=64)
    if enqueue_status not in {"created", "deduped", "not_created", "cooldown_active"}:
        return
    stage = {
        "created": "improvement_task_enqueued",
        "deduped": "improvement_task_deduped",
        "not_created": "improvement_task_enqueue_blocked",
        "cooldown_active": "improvement_task_enqueue_blocked",
    }[enqueue_status]
    status = {
        "created": "created",
        "deduped": "reused",
        "not_created": "blocked",
        "cooldown_active": "blocked",
    }[enqueue_status]
    try:
        record_self_hardening_event(
            queue=queue,
            stage=stage,
            status=status,
            pattern_name=_text(decision.get("candidate_id"), limit=80),
            component=_text(decision.get("category"), limit=64),
            requested_fix_mode=_text(decision.get("requested_fix_mode"), limit=64),
            execution_mode=_text(decision.get("effective_fix_mode"), limit=64),
            route_target=_text(decision.get("target_agent"), limit=64),
            reason=_text(decision.get("enqueue_reason") or decision.get("autoenqueue_state"), limit=160),
            task_id=_text(decision.get("enqueued_task_id"), limit=80),
            target_file_path=_text(decision.get("target_file_path"), limit=200),
            change_type=_text(decision.get("change_type"), limit=96),
            increment_metrics=_hardening_metric_increment(
                _text(decision.get("target_agent"), limit=64),
                enqueue_status,
            ),
        )
    except Exception:
        pass


def apply_improvement_task_autonomy(
    queue: Any,
    tasks: Iterable[Mapping[str, Any]],
    promotions: Iterable[Mapping[str, Any]],
    bridges: Iterable[Mapping[str, Any]],
    payloads: Iterable[Mapping[str, Any]],
    *,
    allow_self_modify: bool = False,
    max_autoenqueue: int = 1,
) -> dict[str, Any]:
    tasks_by_id = {_text(task.get("task_id"), limit=80): task for task in tasks}
    promotions_by_id = {_text(item.get("task_id"), limit=80): item for item in promotions}
    bridges_by_id = {_text(item.get("task_id"), limit=80): item for item in bridges}

    decisions: list[dict[str, Any]] = []
    enqueued_total = 0
    deduped_total = 0
    blocked_total = 0
    rollout_guard = get_improvement_task_rollout_guard(queue)

    for payload in payloads:
        compiled_task_id = _text(payload.get("compiled_task_id"), limit=80)
        decision = build_improvement_task_autonomy_decision(
            payload,
            rollout_guard=rollout_guard,
            allow_self_modify=allow_self_modify,
            enqueued_this_cycle=enqueued_total,
            max_autoenqueue=max_autoenqueue,
        )
        bridge = bridges_by_id.get(compiled_task_id) or {}
        decision.update(
            {
                "target_file_path": _text(bridge.get("target_file_path"), limit=200),
                "change_type": _text(bridge.get("change_type"), limit=96),
                "enqueue_status": "",
                "enqueue_reason": "",
                "enqueued_task_id": "",
                "existing_task_id": "",
                "cooldown_minutes": 0,
            }
        )

        if decision["autoenqueue_state"] == "autoenqueue_ready":
            task = tasks_by_id.get(compiled_task_id)
            promotion = promotions_by_id.get(compiled_task_id)
            if task is None or promotion is None or not bridge:
                decision["autoenqueue_state"] = "enqueue_blocked"
                decision["enqueue_status"] = "not_created"
                decision["enqueue_reason"] = "missing_task_context"
                blocked_total += 1
            else:
                result = enqueue_improvement_hardening_task(queue, task, promotion, bridge)
                decision["enqueue_status"] = _text(result.get("status"), limit=64)
                decision["enqueue_reason"] = _text(result.get("reason"), limit=160)
                decision["enqueued_task_id"] = _text(result.get("task_id"), limit=80)
                if decision["enqueue_status"] != "created":
                    decision["existing_task_id"] = _text(result.get("task_id"), limit=80)
                decision["cooldown_minutes"] = int(result.get("cooldown_minutes") or 0)
                if decision["enqueue_status"] == "created":
                    decision["autoenqueue_state"] = "enqueue_created"
                    enqueued_total += 1
                elif decision["enqueue_status"] == "deduped":
                    decision["autoenqueue_state"] = "enqueue_deduped"
                    deduped_total += 1
                elif decision["enqueue_status"] == "cooldown_active":
                    decision["autoenqueue_state"] = "enqueue_cooldown_active"
                    blocked_total += 1
                else:
                    decision["autoenqueue_state"] = "enqueue_blocked"
                    blocked_total += 1
        else:
            if decision.get("rollout_guard_blocked"):
                decision["enqueue_status"] = "not_created"
                decision["enqueue_reason"] = _text(
                    "; ".join(decision.get("rollout_guard_reasons") or []) or decision.get("rollout_guard_state"),
                    limit=160,
                )
            blocked_total += 1

        _record_improvement_task_autonomy_event(decision)
        if decision["enqueue_status"]:
            _record_improvement_task_hardening_runtime(queue, decision)
        decisions.append(decision)

    return {
        "decisions": decisions,
        "enqueued_total": enqueued_total,
        "deduped_total": deduped_total,
        "blocked_total": blocked_total,
        "rollout_guard": rollout_guard,
    }


async def run_improvement_task_autonomy_cycle(
    queue: Any,
    *,
    limit: int = 5,
    allow_self_modify: bool = False,
    max_autoenqueue: int = 1,
    rollout_stage: str = "",
) -> dict[str, Any]:
    from orchestration.self_improvement_engine import get_improvement_engine
    from orchestration.session_reflection import SessionReflectionLoop

    engine = get_improvement_engine()
    normalized_candidates = engine.get_normalized_suggestions(applied=False)
    try:
        combined_candidates = await SessionReflectionLoop().get_improvement_suggestions()
    except Exception:
        combined_candidates = normalized_candidates

    compiled_tasks = compile_improvement_tasks(combined_candidates, limit=limit)
    promotion_decisions = evaluate_compiled_task_promotions(
        compiled_tasks,
        limit=limit,
        rollout_stage=rollout_stage,
    )
    bridge_decisions = build_improvement_task_bridges(
        compiled_tasks,
        promotion_decisions,
        limit=limit,
        rollout_stage=rollout_stage,
    )
    execution_payloads = build_improvement_hardening_task_payloads(
        compiled_tasks,
        promotion_decisions,
        bridge_decisions,
        limit=limit,
    )
    autonomy = apply_improvement_task_autonomy(
        queue,
        compiled_tasks,
        promotion_decisions,
        bridge_decisions,
        execution_payloads,
        allow_self_modify=allow_self_modify,
        max_autoenqueue=max_autoenqueue,
    )
    return {
        "status": "ok",
        "candidate_count": len(combined_candidates),
        "compiled_count": len(compiled_tasks),
        "enqueued_total": int(autonomy.get("enqueued_total") or 0),
        "deduped_total": int(autonomy.get("deduped_total") or 0),
        "blocked_total": int(autonomy.get("blocked_total") or 0),
        "rollout_guard": autonomy.get("rollout_guard") or {"state": "allow", "blocked": False, "reasons": []},
        "compiled_tasks": compiled_tasks,
        "promotion_decisions": promotion_decisions,
        "bridge_decisions": bridge_decisions,
        "execution_payloads": execution_payloads,
        "autonomy_decisions": list(autonomy.get("decisions") or []),
    }
