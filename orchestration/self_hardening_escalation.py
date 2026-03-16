from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Dict


_FIX_MODES = {"observe_only", "developer_task", "self_modify_safe", "human_only"}
_FAILURE_STATUSES = {"blocked", "pending_approval", "rolled_back", "error"}
_PATTERN_STATE_PREFIX = "m18_hardening_pattern:"

_SELF_MODIFY_DOWNGRADE_AFTER = max(
    1,
    int(os.getenv("HARDENING_SELF_MODIFY_DOWNGRADE_AFTER", "1") or "1"),
)
_SELF_MODIFY_FREEZE_AFTER = max(
    _SELF_MODIFY_DOWNGRADE_AFTER + 1,
    int(os.getenv("HARDENING_SELF_MODIFY_FREEZE_AFTER", "2") or "2"),
)
_DEVELOPER_FREEZE_AFTER_TASKS = max(
    1,
    int(os.getenv("HARDENING_DEVELOPER_FREEZE_AFTER_TASKS", "2") or "2"),
)
_DEVELOPER_FREEZE_AFTER_RECURRENCES = max(
    _DEVELOPER_FREEZE_AFTER_TASKS + 1,
    int(os.getenv("HARDENING_DEVELOPER_FREEZE_AFTER_RECURRENCES", "3") or "3"),
)
_PATTERN_FREEZE_HOURS = max(
    1,
    int(os.getenv("HARDENING_PATTERN_FREEZE_HOURS", "24") or "24"),
)


def _normalize_fix_mode(value: str) -> str:
    normalized = str(value or "").strip().lower()
    return normalized if normalized in _FIX_MODES else "observe_only"


def _to_int(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except Exception:
        return 0


def _parse_iso(value: str) -> datetime | None:
    safe_value = str(value or "").strip()
    if not safe_value:
        return None
    try:
        return datetime.fromisoformat(safe_value)
    except Exception:
        return None


def _pattern_state_key(pattern_name: str) -> str:
    return f"{_PATTERN_STATE_PREFIX}{str(pattern_name or '').strip()}"


def _default_pattern_state(pattern_name: str, requested_fix_mode: str) -> Dict[str, Any]:
    return {
        "pattern_name": str(pattern_name or "").strip(),
        "requested_fix_mode": _normalize_fix_mode(requested_fix_mode),
        "effective_fix_mode": _normalize_fix_mode(requested_fix_mode),
        "effective_reason": "requested_fix_mode",
        "recurrence_count": 0,
        "proposal_count": 0,
        "developer_task_count": 0,
        "self_modify_task_count": 0,
        "self_modify_attempt_count": 0,
        "self_modify_failure_count": 0,
        "success_count": 0,
        "blocked_count": 0,
        "pending_approval_count": 0,
        "rolled_back_count": 0,
        "error_count": 0,
        "downgrade_count": 0,
        "human_only_escalation_count": 0,
        "repeat_failure_escalation_count": 0,
        "freeze_activation_count": 0,
        "freeze_until": "",
        "freeze_reason": "",
        "freeze_active": False,
        "last_status": "",
        "last_stage": "",
        "last_reason": "",
        "last_route_target": "",
        "last_execution_mode": "",
        "last_detected_at": "",
        "last_success_at": "",
        "updated_at": "",
    }


def is_self_hardening_freeze_active(*, freeze_until: str, now_iso: str = "") -> bool:
    freeze_dt = _parse_iso(freeze_until)
    if freeze_dt is None:
        return False
    now_dt = _parse_iso(now_iso) or datetime.now()
    return freeze_dt > now_dt


@dataclass(frozen=True)
class SelfHardeningEscalationDecision:
    requested_fix_mode: str
    effective_fix_mode: str
    freeze_active: bool
    freeze_until: str
    reason: str
    recurrence_count: int = 0
    self_modify_failures: int = 0
    developer_task_count: int = 0


def classify_self_hardening_effective_fix_mode(
    *,
    requested_fix_mode: str,
    self_modify_failures: int = 0,
    developer_task_count: int = 0,
    recurrence_count: int = 0,
    freeze_until: str = "",
    now_iso: str = "",
) -> SelfHardeningEscalationDecision:
    requested = _normalize_fix_mode(requested_fix_mode)
    safe_self_modify_failures = _to_int(self_modify_failures)
    safe_developer_task_count = _to_int(developer_task_count)
    safe_recurrence_count = _to_int(recurrence_count)
    safe_freeze_until = str(freeze_until or "").strip()

    if requested in {"observe_only", "human_only"}:
        return SelfHardeningEscalationDecision(
            requested_fix_mode=requested,
            effective_fix_mode=requested,
            freeze_active=False,
            freeze_until="",
            reason="requested_fix_mode",
            recurrence_count=safe_recurrence_count,
            self_modify_failures=safe_self_modify_failures,
            developer_task_count=safe_developer_task_count,
        )

    if is_self_hardening_freeze_active(freeze_until=safe_freeze_until, now_iso=now_iso):
        return SelfHardeningEscalationDecision(
            requested_fix_mode=requested,
            effective_fix_mode="human_only",
            freeze_active=True,
            freeze_until=safe_freeze_until,
            reason="human_freeze_active",
            recurrence_count=safe_recurrence_count,
            self_modify_failures=safe_self_modify_failures,
            developer_task_count=safe_developer_task_count,
        )

    if requested == "self_modify_safe":
        if safe_self_modify_failures >= _SELF_MODIFY_FREEZE_AFTER:
            return SelfHardeningEscalationDecision(
                requested_fix_mode=requested,
                effective_fix_mode="human_only",
                freeze_active=False,
                freeze_until="",
                reason="repeated_self_modify_failures",
                recurrence_count=safe_recurrence_count,
                self_modify_failures=safe_self_modify_failures,
                developer_task_count=safe_developer_task_count,
            )
        if safe_self_modify_failures >= _SELF_MODIFY_DOWNGRADE_AFTER:
            return SelfHardeningEscalationDecision(
                requested_fix_mode=requested,
                effective_fix_mode="developer_task",
                freeze_active=False,
                freeze_until="",
                reason="self_modify_failure_budget_exhausted",
                recurrence_count=safe_recurrence_count,
                self_modify_failures=safe_self_modify_failures,
                developer_task_count=safe_developer_task_count,
            )

    if (
        safe_developer_task_count >= _DEVELOPER_FREEZE_AFTER_TASKS
        and safe_recurrence_count >= _DEVELOPER_FREEZE_AFTER_RECURRENCES
    ):
        return SelfHardeningEscalationDecision(
            requested_fix_mode=requested,
            effective_fix_mode="human_only",
            freeze_active=False,
            freeze_until="",
            reason="recurring_after_developer_attempts",
            recurrence_count=safe_recurrence_count,
            self_modify_failures=safe_self_modify_failures,
            developer_task_count=safe_developer_task_count,
        )

    return SelfHardeningEscalationDecision(
        requested_fix_mode=requested,
        effective_fix_mode=requested,
        freeze_active=False,
        freeze_until="",
        reason="requested_fix_mode",
        recurrence_count=safe_recurrence_count,
        self_modify_failures=safe_self_modify_failures,
        developer_task_count=safe_developer_task_count,
    )


def _normalize_pattern_state(pattern_name: str, requested_fix_mode: str, metadata: Dict[str, Any]) -> Dict[str, Any]:
    state = _default_pattern_state(pattern_name, requested_fix_mode)
    for key, value in metadata.items():
        if key in state:
            state[key] = value
    state["pattern_name"] = str(pattern_name or state.get("pattern_name") or "").strip()
    state["requested_fix_mode"] = _normalize_fix_mode(
        str(requested_fix_mode or state.get("requested_fix_mode") or "")
    )
    for numeric_key in (
        "recurrence_count",
        "proposal_count",
        "developer_task_count",
        "self_modify_task_count",
        "self_modify_attempt_count",
        "self_modify_failure_count",
        "success_count",
        "blocked_count",
        "pending_approval_count",
        "rolled_back_count",
        "error_count",
        "downgrade_count",
        "human_only_escalation_count",
        "repeat_failure_escalation_count",
        "freeze_activation_count",
    ):
        state[numeric_key] = _to_int(state.get(numeric_key))
    state["freeze_until"] = str(state.get("freeze_until") or "").strip()
    state["freeze_reason"] = str(state.get("freeze_reason") or "").strip()
    state["last_status"] = str(state.get("last_status") or "").strip()
    state["last_stage"] = str(state.get("last_stage") or "").strip()
    state["last_reason"] = str(state.get("last_reason") or "").strip()
    state["last_route_target"] = str(state.get("last_route_target") or "").strip()
    state["last_execution_mode"] = _normalize_fix_mode(str(state.get("last_execution_mode") or ""))
    state["last_detected_at"] = str(state.get("last_detected_at") or "").strip()
    state["last_success_at"] = str(state.get("last_success_at") or "").strip()
    state["updated_at"] = str(state.get("updated_at") or "").strip()
    decision = classify_self_hardening_effective_fix_mode(
        requested_fix_mode=state["requested_fix_mode"],
        self_modify_failures=state["self_modify_failure_count"],
        developer_task_count=state["developer_task_count"],
        recurrence_count=state["recurrence_count"],
        freeze_until=state["freeze_until"],
    )
    state["effective_fix_mode"] = decision.effective_fix_mode
    state["effective_reason"] = decision.reason
    state["freeze_active"] = bool(decision.freeze_active)
    return state


def get_self_hardening_pattern_state(
    queue,
    *,
    pattern_name: str,
    requested_fix_mode: str = "",
) -> Dict[str, Any]:
    safe_pattern = str(pattern_name or "").strip()
    if not safe_pattern:
        return _default_pattern_state("", requested_fix_mode)
    raw_state = queue.get_policy_runtime_state(_pattern_state_key(safe_pattern)) or {}
    if not isinstance(raw_state, dict):
        raw_state = {}
    metadata = raw_state.get("metadata", {}) if isinstance(raw_state.get("metadata"), dict) else {}
    return _normalize_pattern_state(
        safe_pattern,
        requested_fix_mode or str(raw_state.get("state_value") or ""),
        metadata,
    )


def record_self_hardening_pattern_event(
    queue,
    *,
    pattern_name: str,
    requested_fix_mode: str,
    stage: str,
    status: str = "",
    execution_mode: str = "",
    route_target: str = "",
    reason: str = "",
    observed_at: str = "",
) -> Dict[str, Any]:
    safe_pattern = str(pattern_name or "").strip()
    if not safe_pattern:
        return {"state": _default_pattern_state("", requested_fix_mode), "transition_metrics": {}}

    now_iso = str(observed_at or datetime.now().isoformat())
    old_state = get_self_hardening_pattern_state(
        queue,
        pattern_name=safe_pattern,
        requested_fix_mode=requested_fix_mode,
    )
    state = dict(old_state)
    stage_name = str(stage or "").strip() or "unknown"
    status_name = str(status or "").strip().lower()
    execution_mode_name = _normalize_fix_mode(execution_mode) if execution_mode else ""
    requested_mode = _normalize_fix_mode(requested_fix_mode or state.get("requested_fix_mode") or "")

    state["requested_fix_mode"] = requested_mode
    state["last_status"] = status_name
    state["last_stage"] = stage_name
    state["last_reason"] = str(reason or "").strip()
    state["last_route_target"] = str(route_target or "").strip()
    if execution_mode_name:
        state["last_execution_mode"] = execution_mode_name
    state["updated_at"] = now_iso

    if stage_name in {"proposal_detected", "proposal_skipped_cooldown"}:
        state["recurrence_count"] = _to_int(state.get("recurrence_count")) + 1
        state["last_detected_at"] = now_iso
        if stage_name == "proposal_detected":
            state["proposal_count"] = _to_int(state.get("proposal_count")) + 1
    elif stage_name == "task_created":
        if execution_mode_name == "developer_task":
            state["developer_task_count"] = _to_int(state.get("developer_task_count")) + 1
        elif execution_mode_name == "self_modify_safe":
            state["self_modify_task_count"] = _to_int(state.get("self_modify_task_count")) + 1
        if requested_mode == "self_modify_safe" and execution_mode_name == "developer_task":
            state["downgrade_count"] = _to_int(state.get("downgrade_count")) + 1
    elif stage_name == "self_modify_started":
        state["self_modify_attempt_count"] = _to_int(state.get("self_modify_attempt_count")) + 1
    elif stage_name == "self_modify_finished":
        if status_name == "success":
            state["success_count"] = _to_int(state.get("success_count")) + 1
            state["recurrence_count"] = 0
            state["developer_task_count"] = 0
            state["self_modify_failure_count"] = 0
            state["freeze_until"] = ""
            state["freeze_reason"] = ""
            state["last_success_at"] = now_iso
        elif status_name in _FAILURE_STATUSES:
            state["self_modify_failure_count"] = _to_int(state.get("self_modify_failure_count")) + 1
            count_key = {
                "blocked": "blocked_count",
                "pending_approval": "pending_approval_count",
                "rolled_back": "rolled_back_count",
                "error": "error_count",
            }.get(status_name)
            if count_key:
                state[count_key] = _to_int(state.get(count_key)) + 1

    if state.get("freeze_until") and not is_self_hardening_freeze_active(
        freeze_until=str(state.get("freeze_until") or ""),
        now_iso=now_iso,
    ):
        state["freeze_until"] = ""
        state["freeze_reason"] = ""

    previous_effective_mode = str(old_state.get("effective_fix_mode") or requested_mode or "observe_only")
    decision = classify_self_hardening_effective_fix_mode(
        requested_fix_mode=requested_mode,
        self_modify_failures=state.get("self_modify_failure_count", 0),
        developer_task_count=state.get("developer_task_count", 0),
        recurrence_count=state.get("recurrence_count", 0),
        freeze_until=str(state.get("freeze_until") or ""),
        now_iso=now_iso,
    )

    freeze_activated = False
    if (
        decision.effective_fix_mode == "human_only"
        and requested_mode in {"developer_task", "self_modify_safe"}
        and not decision.freeze_active
    ):
        freeze_activated = True
        freeze_base = _parse_iso(now_iso) or datetime.now()
        state["freeze_until"] = (freeze_base + timedelta(hours=_PATTERN_FREEZE_HOURS)).isoformat()
        state["freeze_reason"] = decision.reason
        decision = classify_self_hardening_effective_fix_mode(
            requested_fix_mode=requested_mode,
            self_modify_failures=state.get("self_modify_failure_count", 0),
            developer_task_count=state.get("developer_task_count", 0),
            recurrence_count=state.get("recurrence_count", 0),
            freeze_until=str(state.get("freeze_until") or ""),
            now_iso=now_iso,
        )

    transition_metrics: Dict[str, int] = {}
    if (
        previous_effective_mode != "developer_task"
        and decision.effective_fix_mode == "developer_task"
        and requested_mode == "self_modify_safe"
    ):
        state["repeat_failure_escalation_count"] = _to_int(state.get("repeat_failure_escalation_count")) + 1
        transition_metrics["repeat_failure_escalations_total"] = 1
    if (
        previous_effective_mode != "human_only"
        and decision.effective_fix_mode == "human_only"
        and requested_mode in {"developer_task", "self_modify_safe"}
    ):
        state["human_only_escalation_count"] = _to_int(state.get("human_only_escalation_count")) + 1
        transition_metrics["human_only_escalations_total"] = 1
    if freeze_activated:
        state["freeze_activation_count"] = _to_int(state.get("freeze_activation_count")) + 1
        transition_metrics["freeze_activations_total"] = 1

    state["effective_fix_mode"] = decision.effective_fix_mode
    state["effective_reason"] = decision.reason
    state["freeze_active"] = bool(decision.freeze_active)

    queue.set_policy_runtime_state(
        _pattern_state_key(safe_pattern),
        decision.effective_fix_mode,
        metadata_update=state,
        observed_at=now_iso,
    )
    return {"state": state, "transition_metrics": transition_metrics}
