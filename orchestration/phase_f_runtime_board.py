from __future__ import annotations

from datetime import datetime
import inspect
from typing import Any, Mapping, Sequence


PHASE_F_RUNTIME_BOARD_VERSION = "phase_f_runtime_board_v1"

_ACTION_PRIORITY = {
    "allow": 0,
    "observe": 1,
    "hold": 2,
    "recover": 3,
    "freeze": 4,
}

_RISK_PRIORITY = {
    "none": 0,
    "low": 1,
    "medium": 2,
    "high": 3,
    "critical": 4,
}


def _iso_now() -> str:
    return datetime.now().astimezone().replace(microsecond=0).isoformat()


def _text(value: Any, *, limit: int = 160) -> str:
    text = str(value or "").strip()
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "..."


def _normalize_reason_list(values: Sequence[Any] | None, *, limit: int = 6) -> list[str]:
    items: list[str] = []
    for raw in list(values or []):
        item = _text(raw, limit=120)
        if not item or item in items:
            continue
        items.append(item)
        if len(items) >= limit:
            break
    return items


def _pick_highest(values: Sequence[str] | None, *, ranking: Mapping[str, int], default: str) -> str:
    best = default
    best_rank = int(ranking.get(default, 0))
    for raw in list(values or []):
        value = _text(raw, limit=64).lower()
        rank = int(ranking.get(value, -1))
        if rank > best_rank:
            best = value
            best_rank = rank
    return best


def _risk_for_state(state: Any) -> str:
    normalized = _text(state, limit=64).lower()
    if normalized in {"", "ok", "healthy", "clear", "allow", "pass", "idle"}:
        return "none"
    if normalized in {"active", "observing", "startup_grace"}:
        return "low"
    if normalized in {"warn", "cooldown_active", "approval_required", "challenge_active"}:
        return "medium"
    if normalized in {"degraded", "challenge_required", "hold", "retrieval_backpressure", "verification_backpressure"}:
        return "high"
    if normalized in {"critical", "strict_force_off", "freeze", "rollback_active", "outage"}:
        return "critical"
    return "medium"


def _action_for_state(state: Any) -> str:
    normalized = _text(state, limit=64).lower()
    if normalized in {"", "ok", "healthy", "clear", "allow", "pass", "idle"}:
        return "allow"
    if normalized in {"active", "observing", "startup_grace"}:
        return "observe"
    if normalized in {"warn", "cooldown_active", "approval_required", "challenge_active"}:
        return "hold"
    if normalized in {"degraded", "challenge_required", "rollback_active", "outage"}:
        return "recover"
    if normalized in {"critical", "strict_force_off", "freeze"}:
        return "freeze"
    return "hold"


def _lane_view(
    *,
    lane: str,
    state: Any,
    blocked: bool = False,
    degraded: bool = False,
    reasons: Sequence[Any] | None = None,
    metrics: Mapping[str, Any] | None = None,
    action: str = "",
    risk_class: str = "",
    last_activity_at: Any = "",
    refs: Sequence[Any] | None = None,
) -> dict[str, Any]:
    normalized_state = _text(state, limit=64).lower() or "unknown"
    normalized_action = _text(action, limit=32).lower() or _action_for_state(normalized_state)
    normalized_risk = _text(risk_class, limit=32).lower() or _risk_for_state(normalized_state)
    return {
        "lane": _text(lane, limit=64).lower(),
        "state": normalized_state,
        "blocked": bool(blocked),
        "degraded": bool(degraded),
        "action": normalized_action,
        "risk_class": normalized_risk,
        "reasons": _normalize_reason_list(reasons),
        "last_activity_at": _text(last_activity_at, limit=64),
        "metrics": dict(metrics or {}),
        "refs": _normalize_reason_list(refs, limit=8),
    }


def summarize_phase_f_runtime_board_lanes(lanes: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    safe_lanes = dict(lanes or {})
    blocked_lanes = [
        _text(name, limit=64)
        for name, lane in safe_lanes.items()
        if bool((lane or {}).get("blocked"))
    ]
    degraded_lanes = [
        _text(name, limit=64)
        for name, lane in safe_lanes.items()
        if bool((lane or {}).get("degraded"))
    ]
    highest_risk_class = _pick_highest(
        [str((lane or {}).get("risk_class") or "") for lane in safe_lanes.values()],
        ranking=_RISK_PRIORITY,
        default="none",
    )
    recommended_action = _pick_highest(
        [str((lane or {}).get("action") or "") for lane in safe_lanes.values()],
        ranking=_ACTION_PRIORITY,
        default="allow",
    )
    overall_state = "ok"
    if highest_risk_class == "critical":
        overall_state = "critical"
    elif blocked_lanes or degraded_lanes or highest_risk_class in {"high", "medium"}:
        overall_state = "warn"

    return {
        "lane_count": len(safe_lanes),
        "lane_names": sorted(str(name) for name in safe_lanes.keys()),
        "blocked_lanes": blocked_lanes,
        "blocked_lane_count": len(blocked_lanes),
        "degraded_lanes": degraded_lanes,
        "degraded_lane_count": len(degraded_lanes),
        "highest_risk_class": highest_risk_class,
        "recommended_action": recommended_action,
        "state": overall_state,
    }


def _stack_lane(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    services = dict(snapshot.get("services") or {})
    failing_services = sorted(name for name, row in services.items() if not bool((row or {}).get("ok")))
    mcp_runtime = dict(snapshot.get("mcp_runtime") or {})
    ops = dict(snapshot.get("ops") or {})
    state = _text(ops.get("state"), limit=32).lower() or "unknown"
    if failing_services:
        state = "critical"
    return _lane_view(
        lane="stack",
        state=state,
        blocked=bool(failing_services),
        degraded=bool(failing_services) or _text(mcp_runtime.get("state"), limit=32).lower() not in {"", "healthy"},
        reasons=failing_services or [mcp_runtime.get("reason"), ops.get("state")],
        metrics={
            "service_count": len(services),
            "failing_service_count": len(failing_services),
            "mcp_runtime_state": _text(mcp_runtime.get("state"), limit=32).lower(),
            "critical_alerts": int(ops.get("critical_alerts") or 0),
            "warnings": int(ops.get("warnings") or 0),
        },
        refs=["gateway/status_snapshot.py", "server/mcp_server.py"],
    )


def _request_lane(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    runtime = dict(snapshot.get("request_runtime") or {})
    state = _text(runtime.get("state"), limit=32).lower() or "unknown"
    failed_total = int(runtime.get("chat_failed_total") or 0) + int(runtime.get("task_failed_total") or 0)
    degraded = state in {"warn", "unknown"} or failed_total > 0
    return _lane_view(
        lane="request_flow",
        state=state,
        blocked=False,
        degraded=degraded,
        reasons=[runtime.get("reason")],
        metrics={
            "chat_requests_total": int(runtime.get("chat_requests_total") or 0),
            "chat_completed_total": int(runtime.get("chat_completed_total") or 0),
            "chat_failed_total": int(runtime.get("chat_failed_total") or 0),
            "task_failed_total": int(runtime.get("task_failed_total") or 0),
            "user_visible_failures_total": int(runtime.get("user_visible_failures_total") or 0),
        },
        last_activity_at=(runtime.get("last_outcome") or {}).get("observed_at") or (runtime.get("last_request") or {}).get("observed_at"),
        refs=["orchestration/autonomy_observation.py", "gateway/status_snapshot.py"],
    )


def _communication_lane(observation_summary: Mapping[str, Any]) -> dict[str, Any]:
    runtime = dict(observation_summary.get("communication_runtime") or {})
    failed = int(runtime.get("tasks_failed_total") or 0) + int(runtime.get("email_send_failed_total") or 0)
    started = int(runtime.get("tasks_started_total") or 0)
    completed = int(runtime.get("tasks_completed_total") or 0)
    state = "idle"
    if started > 0:
        state = "active"
    if failed > 0:
        state = "warn"
    return _lane_view(
        lane="communication",
        state=state,
        blocked=False,
        degraded=failed > 0,
        reasons=["communication_failures_present"] if failed > 0 else [],
        metrics={
            "tasks_started_total": started,
            "tasks_completed_total": completed,
            "tasks_failed_total": int(runtime.get("tasks_failed_total") or 0),
            "tasks_partial_total": int(runtime.get("tasks_partial_total") or 0),
            "email_send_failed_total": int(runtime.get("email_send_failed_total") or 0),
        },
        refs=["orchestration/autonomy_observation.py"],
    )


def _approval_auth_lane(
    observation_summary: Mapping[str, Any],
    operator_snapshot: Mapping[str, Any],
) -> dict[str, Any]:
    challenge_runtime = dict(observation_summary.get("challenge_runtime") or {})
    approval_surface = dict(operator_snapshot.get("approval") or {})
    pending_count = int(approval_surface.get("pending_count") or 0)
    challenge_required = int(challenge_runtime.get("challenge_required_total") or 0)
    challenge_resolved = int(challenge_runtime.get("challenge_resolved_total") or 0)
    challenge_reblocked = int(challenge_runtime.get("challenge_reblocked_total") or 0)
    unresolved_challenges = max(0, challenge_required + challenge_reblocked - challenge_resolved)

    state = "clear"
    blocked = False
    reasons: list[str] = []
    if pending_count > 0:
        state = "approval_required"
        blocked = True
        reasons.append(f"pending_approvals:{pending_count}")
    elif unresolved_challenges > 0:
        state = "challenge_active"
        blocked = True
        reasons.append(f"unresolved_challenges:{unresolved_challenges}")

    return _lane_view(
        lane="approval_auth",
        state=state,
        blocked=blocked,
        degraded=blocked,
        reasons=reasons or approval_surface.get("requested_actions") or [],
        metrics={
            "pending_approval_count": pending_count,
            "approval_highest_risk_class": _text(approval_surface.get("highest_risk_class"), limit=32).lower(),
            "challenge_required_total": challenge_required,
            "challenge_resolved_total": challenge_resolved,
            "challenge_reblocked_total": challenge_reblocked,
            "challenge_resolution_rate": float(challenge_runtime.get("resolution_rate") or 0.0),
        },
        refs=["orchestration/autonomy_change_control.py", "orchestration/approval_auth_contract.py"],
    )


def _phase_e_lane(operator_snapshot: Mapping[str, Any], lane_name: str) -> dict[str, Any]:
    lane = dict(((operator_snapshot.get("lanes") or {}) if isinstance(operator_snapshot.get("lanes"), Mapping) else {}).get(lane_name) or {})
    runtime = dict(lane.get("runtime") or {})
    metrics = dict(runtime)
    metrics["next_candidate_count"] = int(lane.get("next_candidate_count") or 0)
    last_action = dict(lane.get("last_action") or {})
    return _lane_view(
        lane=lane_name,
        state=lane.get("state"),
        blocked=bool(lane.get("blocked")),
        degraded=_text(lane.get("state"), limit=64).lower() not in {"", "allow", "healthy", "ok", "pass"},
        reasons=lane.get("reasons") or [],
        action=(dict(operator_snapshot.get("governance") or {}).get("lanes") or {}).get(lane_name, {}).get("action", ""),
        risk_class=(dict(operator_snapshot.get("governance") or {}).get("lanes") or {}).get(lane_name, {}).get("risk_class", ""),
        metrics=metrics,
        last_activity_at=last_action.get("observed_at") or lane.get("last_completed_at") or lane.get("last_blocked_at"),
        refs=["orchestration/phase_e_operator_snapshot.py", "orchestration/autonomy_observation.py"],
    )


def _recovery_lane(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    self_healing = dict(snapshot.get("self_healing") or {})
    self_hardening = dict(snapshot.get("self_hardening") or {})
    stability_gate = dict(snapshot.get("stability_gate") or {})
    degrade_mode = _text(self_healing.get("degrade_mode"), limit=32).lower()
    open_incidents = int(self_healing.get("open_incidents") or 0)
    open_breakers = int(self_healing.get("circuit_breakers_open") or 0)
    state = "clear"
    blocked = False
    degraded = False
    reasons: list[str] = []
    if degrade_mode not in {"", "normal"}:
        state = "degraded"
        degraded = True
        reasons.append(f"degrade_mode:{degrade_mode}")
    if open_incidents > 0 or open_breakers > 0 or _text(stability_gate.get("state"), limit=32).lower() not in {"", "pass", "allow"}:
        state = "degraded"
        blocked = True
        degraded = True
        if open_incidents > 0:
            reasons.append(f"open_incidents:{open_incidents}")
        if open_breakers > 0:
            reasons.append(f"open_breakers:{open_breakers}")
        if _text(stability_gate.get("state"), limit=32).lower() not in {"", "pass", "allow"}:
            reasons.append(f"stability_gate:{_text(stability_gate.get('state'), limit=32).lower()}")
    return _lane_view(
        lane="recovery",
        state=state,
        blocked=blocked,
        degraded=degraded,
        reasons=reasons,
        action="recover" if degraded else "allow",
        risk_class="high" if degraded else "none",
        metrics={
            "open_incidents": open_incidents,
            "circuit_breakers_open": open_breakers,
            "resource_guard_state": _text(self_healing.get("resource_guard_state"), limit=32).lower(),
            "self_hardening_state": _text(self_hardening.get("state"), limit=32).lower(),
        },
        refs=["gateway/status_snapshot.py", "orchestration/self_hardening_runtime.py"],
    )


def _providers_lane(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    providers = dict(snapshot.get("providers") or {})
    unhealthy = sorted(
        name
        for name, payload in providers.items()
        if bool((payload or {}).get("api_configured")) and _text((payload or {}).get("state"), limit=32).lower() not in {"ok", "unsupported"}
    )
    ops = dict(snapshot.get("ops") or {})
    state = "clear" if not unhealthy else "degraded"
    return _lane_view(
        lane="providers",
        state=state,
        blocked=False,
        degraded=bool(unhealthy),
        reasons=unhealthy,
        action="recover" if unhealthy else "allow",
        risk_class="high" if int(ops.get("unhealthy_providers") or 0) >= 2 else ("medium" if unhealthy else "none"),
        metrics={
            "provider_count": len(providers),
            "unhealthy_provider_count": len(unhealthy),
            "budget_state": _text((snapshot.get("budget") or {}).get("state"), limit=32).lower(),
            "active_provider_count": int((snapshot.get("api_control") or {}).get("active_provider_count") or 0),
        },
        refs=["gateway/status_snapshot.py"],
    )


def build_phase_f_runtime_board(
    *,
    system_snapshot: Mapping[str, Any],
    observation_summary: Mapping[str, Any],
    operator_snapshot: Mapping[str, Any],
) -> dict[str, Any]:
    lanes = {
        "stack": _stack_lane(system_snapshot),
        "request_flow": _request_lane(system_snapshot),
        "communication": _communication_lane(observation_summary),
        "approval_auth": _approval_auth_lane(observation_summary, operator_snapshot),
        "improvement": _phase_e_lane(operator_snapshot, "improvement"),
        "memory_curation": _phase_e_lane(operator_snapshot, "memory_curation"),
        "recovery": _recovery_lane(system_snapshot),
        "providers": _providers_lane(system_snapshot),
    }
    summary = summarize_phase_f_runtime_board_lanes(lanes)
    summary.update(
        {
            "pending_approval_count": int((dict(operator_snapshot.get("approval") or {})).get("pending_count") or 0),
            "open_incidents": int((dict(system_snapshot.get("self_healing") or {})).get("open_incidents") or 0),
            "unhealthy_provider_count": int(
                sum(
                    1
                    for payload in dict(system_snapshot.get("providers") or {}).values()
                    if bool((payload or {}).get("api_configured"))
                    and _text((payload or {}).get("state"), limit=32).lower() not in {"ok", "unsupported"}
                )
            ),
        }
    )
    return {
        "contract_version": PHASE_F_RUNTIME_BOARD_VERSION,
        "generated_at": _iso_now(),
        "summary": summary,
        "lanes": lanes,
        "system": {
            "ops_state": _text((system_snapshot.get("ops") or {}).get("state"), limit=32).lower(),
            "mcp_runtime_state": _text((system_snapshot.get("mcp_runtime") or {}).get("state"), limit=32).lower(),
            "request_runtime_state": _text((system_snapshot.get("request_runtime") or {}).get("state"), limit=32).lower(),
            "stability_gate_state": _text((system_snapshot.get("stability_gate") or {}).get("state"), limit=32).lower(),
            "release_gate_state": _text((system_snapshot.get("ops_gate") or {}).get("state"), limit=32).lower(),
        },
    }


def render_phase_f_runtime_board(board: Mapping[str, Any]) -> str:
    summary = dict(board.get("summary") or {})
    lines = [
        "Phase F Runtime Board",
        f"contract_version: {board.get('contract_version', '')}",
        f"state: {summary.get('state', 'unknown')}",
        f"lane_count: {summary.get('lane_count', 0)}",
        f"blocked_lane_count: {summary.get('blocked_lane_count', 0)}",
        f"degraded_lane_count: {summary.get('degraded_lane_count', 0)}",
        f"recommended_action: {summary.get('recommended_action', 'allow')}",
        "",
        "Lanes:",
    ]
    for name, lane in dict(board.get("lanes") or {}).items():
        metrics = dict((lane or {}).get("metrics") or {})
        detail = []
        for key in list(metrics.keys())[:3]:
            detail.append(f"{key}={metrics[key]}")
        lines.append(
            f"- {name}: state={lane.get('state', '')} blocked={lane.get('blocked', False)} "
            f"degraded={lane.get('degraded', False)} risk={lane.get('risk_class', '')}"
            + (f" ({', '.join(detail)})" if detail else "")
        )
    return "\n".join(lines)


async def collect_phase_f_runtime_board() -> dict[str, Any]:
    from gateway.status_snapshot import collect_status_snapshot
    from orchestration.autonomy_observation import build_autonomy_observation_summary
    from orchestration.phase_e_operator_snapshot import collect_phase_e_operator_snapshot
    from orchestration.task_queue import get_queue

    queue = get_queue()
    system_snapshot_result = collect_status_snapshot()
    system_snapshot = await system_snapshot_result if inspect.isawaitable(system_snapshot_result) else system_snapshot_result
    observation_summary = build_autonomy_observation_summary()
    operator_snapshot_result = collect_phase_e_operator_snapshot(limit=5, queue=queue)
    operator_snapshot = (
        await operator_snapshot_result if inspect.isawaitable(operator_snapshot_result) else operator_snapshot_result
    )
    return build_phase_f_runtime_board(
        system_snapshot=system_snapshot,
        observation_summary=observation_summary,
        operator_snapshot=operator_snapshot,
    )
