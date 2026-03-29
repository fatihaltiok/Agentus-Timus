from __future__ import annotations

from typing import Any, Dict, Optional

from orchestration.autonomy_observation import record_autonomy_observation
from orchestration.self_hardening_escalation import record_self_hardening_pattern_event
from orchestration.self_hardening_rollout import get_self_hardening_rollout_stage
from orchestration.self_hardening_verification import classify_self_hardening_verification_status


_METRIC_KEYS = (
    "proposals_total",
    "cooldown_skips_total",
    "goals_created_total",
    "goals_reused_total",
    "tasks_created_total",
    "tasks_deduped_total",
    "developer_tasks_total",
    "self_modify_tasks_total",
    "self_modify_attempts_total",
    "self_modify_successes_total",
    "self_modify_pending_approval_total",
    "self_modify_blocked_total",
    "self_modify_rolled_back_total",
    "self_modify_errors_total",
    "downgraded_to_development_total",
    "repeat_failure_escalations_total",
    "human_only_escalations_total",
    "freeze_activations_total",
    "verification_planned_total",
    "verification_verified_total",
    "verification_pending_approval_total",
    "verification_blocked_total",
    "verification_rolled_back_total",
    "verification_error_total",
)

_LAST_EVENT_KEY = "m18_hardening_last_event"
_METRICS_KEY = "m18_hardening_metrics"


def _to_int(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except Exception:
        return 0


def classify_self_hardening_runtime_state(
    *,
    last_status: str,
    last_stage: str,
    verification_status: str = "",
    effective_fix_mode: str = "",
    freeze_active: bool = False,
) -> str:
    normalized_status = str(last_status or "").strip().lower()
    normalized_stage = str(last_stage or "").strip().lower()
    normalized_verification = str(verification_status or "").strip().lower()
    normalized_effective_fix_mode = str(effective_fix_mode or "").strip().lower()
    if normalized_status in {"error", "rolled_back"}:
        return "critical"
    if normalized_verification == "error":
        return "warn"
    if bool(freeze_active) or normalized_effective_fix_mode == "human_only":
        return "warn"
    if normalized_status in {"blocked", "pending_approval", "skipped"}:
        return "warn"
    if normalized_status in {"success", "created", "reused"}:
        return "ok"
    if normalized_stage in {"idle_no_signals", ""}:
        return "idle"
    return "warn"


def record_self_hardening_event(
    *,
    queue,
    stage: str,
    status: str = "",
    pattern_name: str = "",
    component: str = "",
    requested_fix_mode: str = "",
    execution_mode: str = "",
    route_target: str = "",
    reason: str = "",
    rollout_stage: str = "",
    rollout_reason: str = "",
    task_id: str = "",
    goal_id: str = "",
    target_file_path: str = "",
    change_type: str = "",
    sample_lines: Optional[list[str]] = None,
    required_checks: Optional[list[str] | tuple[str, ...]] = None,
    required_test_targets: Optional[list[str] | tuple[str, ...]] = None,
    verification_status: str = "",
    verification_summary: str = "",
    test_result: str = "",
    canary_state: str = "",
    canary_summary: str = "",
    audit_id: str = "",
    increment_metrics: Optional[Dict[str, int]] = None,
    observed_at: str = "",
) -> Dict[str, Any]:
    pattern_runtime: Dict[str, Any] = {}
    transition_metrics: Dict[str, int] = {}
    if str(pattern_name or "").strip():
        try:
            pattern_runtime = record_self_hardening_pattern_event(
                queue,
                pattern_name=pattern_name,
                requested_fix_mode=requested_fix_mode,
                stage=stage,
                status=status,
                execution_mode=execution_mode,
                route_target=route_target,
                reason=reason,
                observed_at=observed_at,
            )
            transition_metrics = dict(pattern_runtime.get("transition_metrics") or {})
        except Exception:
            pattern_runtime = {}
            transition_metrics = {}
    pattern_state = (
        pattern_runtime.get("state", {})
        if isinstance(pattern_runtime.get("state"), dict)
        else {}
    )
    safe_required_checks = tuple(str(item or "").strip() for item in (required_checks or []) if str(item or "").strip())
    safe_required_test_targets = tuple(
        str(item or "").strip() for item in (required_test_targets or []) if str(item or "").strip()
    )
    has_verification_context = bool(
        verification_status
        or safe_required_checks
        or safe_required_test_targets
        or test_result
        or canary_state
        or canary_summary
        or stage in {"task_created", "task_deduped", "task_not_created", "self_modify_started", "self_modify_finished"}
    )
    verification_decision = classify_self_hardening_verification_status(
        result_status=verification_status or (status if has_verification_context else "not_run"),
        test_result=test_result,
        canary_state=canary_state,
        required_checks=safe_required_checks,
        required_test_targets=safe_required_test_targets,
    )
    event_payload = {
        "status": str(status or "").strip(),
        "pattern_name": str(pattern_name or "").strip(),
        "component": str(component or "").strip(),
        "requested_fix_mode": str(requested_fix_mode or "").strip(),
        "execution_mode": str(execution_mode or "").strip(),
        "route_target": str(route_target or "").strip(),
        "reason": str(reason or "").strip(),
        "rollout_stage": str(rollout_stage or "").strip(),
        "rollout_reason": str(rollout_reason or "").strip(),
        "task_id": str(task_id or "").strip(),
        "goal_id": str(goal_id or "").strip(),
        "target_file_path": str(target_file_path or "").strip(),
        "change_type": str(change_type or "").strip(),
        "sample_lines": list(sample_lines or [])[:3],
        "pattern_effective_fix_mode": str(pattern_state.get("effective_fix_mode") or "").strip(),
        "pattern_effective_reason": str(pattern_state.get("effective_reason") or "").strip(),
        "pattern_freeze_until": str(pattern_state.get("freeze_until") or "").strip(),
        "pattern_freeze_active": bool(pattern_state.get("freeze_active")),
        "pattern_recurrence_count": _to_int(pattern_state.get("recurrence_count")),
        "verification_status": str(
            verification_status or verification_decision.verification_status or ""
        ).strip(),
        "verification_summary": str(
            verification_summary or verification_decision.summary or ""
        ).strip(),
        "verification_required": bool(verification_decision.verification_required),
        "required_checks": list(safe_required_checks),
        "required_test_targets": list(safe_required_test_targets),
        "test_result": str(test_result or "").strip(),
        "canary_state": str(canary_state or "").strip(),
        "canary_summary": str(canary_summary or "").strip(),
        "audit_id": str(audit_id or "").strip(),
    }
    queue.set_policy_runtime_state(
        _LAST_EVENT_KEY,
        str(stage or "").strip() or "unknown",
        metadata_update=event_payload,
        observed_at=observed_at or None,
    )

    metrics_state = queue.get_policy_runtime_state(_METRICS_KEY) or {}
    metadata = metrics_state.get("metadata", {}) if isinstance(metrics_state.get("metadata"), dict) else {}
    for key in _METRIC_KEYS:
        metadata[key] = _to_int(metadata.get(key))
    merged_metric_updates = dict(increment_metrics or {})
    for key, delta in transition_metrics.items():
        merged_metric_updates[key] = _to_int(merged_metric_updates.get(key)) + _to_int(delta)
    verification_metric_key = {
        "planned": "verification_planned_total",
        "verified": "verification_verified_total",
        "pending_approval": "verification_pending_approval_total",
        "blocked": "verification_blocked_total",
        "rolled_back": "verification_rolled_back_total",
        "error": "verification_error_total",
    }.get(str(event_payload.get("verification_status") or "").strip())
    if verification_metric_key and verification_metric_key not in merged_metric_updates:
        merged_metric_updates[verification_metric_key] = 1
    for key, delta in merged_metric_updates.items():
        if key not in _METRIC_KEYS:
            continue
        metadata[key] = _to_int(metadata.get(key)) + max(0, int(delta or 0))
    queue.set_policy_runtime_state(
        _METRICS_KEY,
        "active",
        metadata_update=metadata,
        observed_at=observed_at or None,
    )
    try:
        record_autonomy_observation(
            "self_hardening_runtime_event",
            {
                "stage": str(stage or "").strip(),
                "status": event_payload.get("status", ""),
                "pattern_name": event_payload.get("pattern_name", ""),
                "component": event_payload.get("component", ""),
                "requested_fix_mode": event_payload.get("requested_fix_mode", ""),
                "execution_mode": event_payload.get("execution_mode", ""),
                "route_target": event_payload.get("route_target", ""),
                "rollout_stage": event_payload.get("rollout_stage", ""),
                "verification_status": event_payload.get("verification_status", ""),
                "verification_required": bool(event_payload.get("verification_required")),
                "audit_id": event_payload.get("audit_id", ""),
                "task_id": event_payload.get("task_id", ""),
                "goal_id": event_payload.get("goal_id", ""),
                "target_file_path": event_payload.get("target_file_path", ""),
                "change_type": event_payload.get("change_type", ""),
                "pattern_effective_fix_mode": event_payload.get("pattern_effective_fix_mode", ""),
                "pattern_freeze_active": bool(event_payload.get("pattern_freeze_active")),
            },
            observed_at=observed_at or "",
        )
    except Exception:
        pass
    return {
        "last_event": str(stage or "").strip() or "unknown",
        "last_event_metadata": event_payload,
        "metrics": metadata,
    }


def get_self_hardening_runtime_summary(queue) -> Dict[str, Any]:
    try:
        last_event = queue.get_policy_runtime_state(_LAST_EVENT_KEY) or {}
        metrics_state = queue.get_policy_runtime_state(_METRICS_KEY) or {}
    except Exception:
        return {
            "state": "unknown",
            "last_event": "",
            "last_status": "",
            "last_pattern_name": "",
            "last_component": "",
            "last_requested_fix_mode": "",
            "last_execution_mode": "",
            "last_route_target": "",
            "last_reason": "",
            "last_rollout_stage": get_self_hardening_rollout_stage(),
            "last_rollout_reason": "",
            "last_task_id": "",
            "last_goal_id": "",
            "last_target_file_path": "",
            "last_change_type": "",
            "last_pattern_effective_fix_mode": "",
            "last_pattern_effective_reason": "",
            "last_pattern_freeze_until": "",
            "last_pattern_freeze_active": False,
            "last_pattern_recurrence_count": 0,
            "last_verification_status": "",
            "last_verification_summary": "",
            "last_verification_required": False,
            "last_required_checks": [],
            "last_required_test_targets": [],
            "last_test_result": "",
            "last_canary_state": "",
            "last_canary_summary": "",
            "last_audit_id": "",
            "metrics": {key: 0 for key in _METRIC_KEYS},
            "updated_at": "",
        }

    event_meta = last_event.get("metadata", {}) if isinstance(last_event.get("metadata"), dict) else {}
    metrics_meta = metrics_state.get("metadata", {}) if isinstance(metrics_state.get("metadata"), dict) else {}
    metrics = {key: _to_int(metrics_meta.get(key)) for key in _METRIC_KEYS}
    last_stage = str(last_event.get("state_value") or "").strip()
    last_status = str(event_meta.get("status") or "").strip()
    last_verification_status = str(event_meta.get("verification_status") or "").strip()
    last_effective_fix_mode = str(event_meta.get("pattern_effective_fix_mode") or "").strip()
    last_freeze_active = bool(event_meta.get("pattern_freeze_active"))
    current_rollout_stage = get_self_hardening_rollout_stage()
    return {
        "state": classify_self_hardening_runtime_state(
            last_status=last_status,
            last_stage=last_stage,
            verification_status=last_verification_status,
            effective_fix_mode=last_effective_fix_mode,
            freeze_active=last_freeze_active,
        ),
        "last_event": last_stage,
        "last_status": last_status,
        "last_pattern_name": str(event_meta.get("pattern_name") or "").strip(),
        "last_component": str(event_meta.get("component") or "").strip(),
        "last_requested_fix_mode": str(event_meta.get("requested_fix_mode") or "").strip(),
        "last_execution_mode": str(event_meta.get("execution_mode") or "").strip(),
        "last_route_target": str(event_meta.get("route_target") or "").strip(),
        "last_reason": str(event_meta.get("reason") or "").strip(),
        "last_rollout_stage": str(event_meta.get("rollout_stage") or current_rollout_stage).strip(),
        "last_rollout_reason": str(event_meta.get("rollout_reason") or "").strip(),
        "last_task_id": str(event_meta.get("task_id") or "").strip(),
        "last_goal_id": str(event_meta.get("goal_id") or "").strip(),
        "last_target_file_path": str(event_meta.get("target_file_path") or "").strip(),
        "last_change_type": str(event_meta.get("change_type") or "").strip(),
        "last_pattern_effective_fix_mode": last_effective_fix_mode,
        "last_pattern_effective_reason": str(event_meta.get("pattern_effective_reason") or "").strip(),
        "last_pattern_freeze_until": str(event_meta.get("pattern_freeze_until") or "").strip(),
        "last_pattern_freeze_active": last_freeze_active,
        "last_pattern_recurrence_count": _to_int(event_meta.get("pattern_recurrence_count")),
        "last_verification_status": last_verification_status,
        "last_verification_summary": str(event_meta.get("verification_summary") or "").strip(),
        "last_verification_required": bool(event_meta.get("verification_required")),
        "last_required_checks": list(event_meta.get("required_checks") or []),
        "last_required_test_targets": list(event_meta.get("required_test_targets") or []),
        "last_test_result": str(event_meta.get("test_result") or "").strip(),
        "last_canary_state": str(event_meta.get("canary_state") or "").strip(),
        "last_canary_summary": str(event_meta.get("canary_summary") or "").strip(),
        "last_audit_id": str(event_meta.get("audit_id") or "").strip(),
        "sample_lines": list(event_meta.get("sample_lines") or [])[:3],
        "metrics": metrics,
        "current_rollout_stage": current_rollout_stage,
        "updated_at": str(last_event.get("updated_at") or metrics_state.get("updated_at") or ""),
    }
