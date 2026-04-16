from __future__ import annotations

from datetime import datetime
from typing import Any, Mapping, Sequence


def _iso_now() -> str:
    return datetime.now().astimezone().replace(microsecond=0).isoformat()


def _text(value: Any, *, limit: int = 160) -> str:
    text = str(value or "").strip()
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "..."


def _normalize_reason_list(values: Sequence[Any] | None, *, limit: int = 4) -> list[str]:
    return [
        _text(value, limit=96)
        for value in list(values or [])
        if _text(value, limit=96)
    ][:limit]


def _normalized_event_payload(event: Mapping[str, Any]) -> tuple[str, str, Mapping[str, Any]]:
    event_type = _text(event.get("event_type"), limit=80).lower()
    observed_at = _text(event.get("observed_at"), limit=64)
    payload = event.get("payload")
    return event_type, observed_at, payload if isinstance(payload, Mapping) else {}


def _is_improvement_event(event: Mapping[str, Any]) -> bool:
    event_type, _, payload = _normalized_event_payload(event)
    if event_type == "improvement_task_autonomy_event":
        return True
    source = _text(payload.get("source"), limit=80).lower()
    if source == "improvement_task_bridge":
        return True
    task_outcome_state = _text(payload.get("task_outcome_state"), limit=64).lower()
    if task_outcome_state in {"verified", "ended_unverified", "blocked", "verification_failed", "rolled_back"}:
        return True
    verification_state = _text(payload.get("verification_state"), limit=64).lower()
    return verification_state in {"verified", "not_verified", "blocked", "error", "rolled_back"}


def _is_memory_curation_event(event: Mapping[str, Any]) -> bool:
    event_type, _, _ = _normalized_event_payload(event)
    return event_type.startswith("memory_curation_") or event_type in {
        "memory_summarized",
        "memory_archived",
        "memory_devalued",
    }


def _lane_event_view(event: Mapping[str, Any], *, lane: str) -> dict[str, Any]:
    event_type, observed_at, payload = _normalized_event_payload(event)
    if lane == "improvement":
        if event_type == "improvement_task_autonomy_event":
            status = _text(payload.get("autoenqueue_state") or payload.get("rollout_guard_state"), limit=64)
            summary = _text(
                f"autoenqueue:{payload.get('autoenqueue_state') or 'unknown'}"
                f" guard:{payload.get('rollout_guard_state') or 'unknown'}",
                limit=160,
            )
            ref_id = _text(payload.get("candidate_id"), limit=64)
        else:
            status = _text(payload.get("task_outcome_state") or payload.get("verification_state") or event_type, limit=64)
            summary = _text(
                f"execution:{payload.get('task_outcome_state') or 'unknown'}"
                f" verification:{payload.get('verification_state') or 'unknown'}",
                limit=160,
            )
            ref_id = _text(payload.get("task_id"), limit=64)
    else:
        if event_type == "memory_curation_autonomy_blocked":
            status = _text(payload.get("state") or "blocked", limit=64)
            summary = _text(
                f"autonomy_blocked:{payload.get('state') or 'blocked'}"
                f" reasons:{','.join(_normalize_reason_list(payload.get('reasons') or [], limit=2))}",
                limit=160,
            )
        elif event_type == "memory_curation_autonomy_completed":
            status = _text(payload.get("status") or "completed", limit=64)
            summary = _text(f"autonomy_completed:{payload.get('status') or 'completed'}", limit=160)
        elif event_type == "memory_curation_completed":
            status = _text(payload.get("final_status") or "completed", limit=64)
            summary = _text(
                f"curation_completed:{payload.get('final_status') or 'completed'}"
                f" verification:{'passed' if bool(payload.get('verification_passed')) else 'failed'}",
                limit=160,
            )
        elif event_type in {"memory_summarized", "memory_archived", "memory_devalued"}:
            status = event_type.removeprefix("memory_")
            summary = _text(f"action:{status}", limit=160)
        else:
            status = _text(payload.get("stage") or event_type, limit=64)
            summary = _text(f"{event_type}:{payload.get('stage') or ''}", limit=160)
        ref_id = _text(payload.get("snapshot_id"), limit=64)
    return {
        "event_type": event_type,
        "observed_at": observed_at,
        "status": status,
        "summary": summary,
        "ref_id": ref_id,
    }


def _latest_lane_event(events: Sequence[Mapping[str, Any]], *, lane: str, matcher) -> dict[str, Any]:
    for event in reversed(list(events or [])):
        if matcher(event):
            return _lane_event_view(event, lane=lane)
    return {}


def _latest_lane_timestamp(events: Sequence[Mapping[str, Any]], matcher) -> str:
    for event in reversed(list(events or [])):
        if matcher(event):
            return _text(event.get("observed_at"), limit=64)
    return ""


def _system_view(system_snapshot: Mapping[str, Any]) -> dict[str, Any]:
    services_payload = system_snapshot.get("services")
    services = services_payload if isinstance(services_payload, Mapping) else {}
    ops_payload = system_snapshot.get("ops")
    ops = ops_payload if isinstance(ops_payload, Mapping) else {}
    mcp_runtime_payload = system_snapshot.get("mcp_runtime")
    mcp_runtime = mcp_runtime_payload if isinstance(mcp_runtime_payload, Mapping) else {}
    request_runtime_payload = system_snapshot.get("request_runtime")
    request_runtime = request_runtime_payload if isinstance(request_runtime_payload, Mapping) else {}
    stability_gate_payload = system_snapshot.get("stability_gate")
    stability_gate = stability_gate_payload if isinstance(stability_gate_payload, Mapping) else {}

    service_rows: dict[str, Any] = {}
    degraded_reasons: list[str] = []
    for name in ("mcp", "dispatcher", "qdrant"):
        service = services.get(name)
        if not isinstance(service, Mapping):
            continue
        service_rows[name] = {
            "active": _text(service.get("active"), limit=32),
            "ok": bool(service.get("ok")),
            "uptime_seconds": float(service.get("uptime_seconds") or 0.0),
        }
        if not bool(service.get("ok")):
            degraded_reasons.append(f"service:{name}:{_text(service.get('active'), limit=32) or 'unknown'}")

    state = _text(ops.get("state"), limit=32).lower() or "unknown"
    if state in {"unknown", ""}:
        state = "degraded" if degraded_reasons else "healthy"

    if _text(mcp_runtime.get("state"), limit=32).lower() not in {"", "healthy"}:
        degraded_reasons.append(f"mcp_runtime:{_text(mcp_runtime.get('state'), limit=32)}")
    if _text(request_runtime.get("state"), limit=32).lower() not in {"", "healthy", "idle"}:
        degraded_reasons.append(f"request_runtime:{_text(request_runtime.get('state'), limit=32)}")
    if _text(stability_gate.get("state"), limit=32).lower() not in {"", "pass"}:
        degraded_reasons.append(f"stability_gate:{_text(stability_gate.get('state'), limit=32)}")

    return {
        "state": state,
        "degraded_reasons": degraded_reasons[:6],
        "services": service_rows,
        "ops": {
            "state": _text(ops.get("state"), limit=32),
            "critical_alerts": int(ops.get("critical_alerts") or 0),
            "warnings": int(ops.get("warnings") or 0),
        },
        "mcp_runtime": {
            "state": _text(mcp_runtime.get("state"), limit=32),
            "reason": _text(mcp_runtime.get("reason"), limit=96),
            "ready": bool(mcp_runtime.get("ready")),
            "warmup_pending": bool(mcp_runtime.get("warmup_pending")),
        },
        "request_runtime": {
            "state": _text(request_runtime.get("state"), limit=32),
            "reason": _text(request_runtime.get("reason"), limit=96),
            "chat_requests_total": int(request_runtime.get("chat_requests_total") or 0),
            "task_failed_total": int(request_runtime.get("task_failed_total") or 0),
        },
    }


def _memory_candidate_view(candidate: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "candidate_id": _text(candidate.get("candidate_id"), limit=96),
        "action": _text(candidate.get("action"), limit=32),
        "category": _text(candidate.get("category"), limit=64),
        "tier": _text(candidate.get("tier"), limit=32),
        "reason": _text(candidate.get("reason"), limit=120),
        "item_count": int(candidate.get("item_count") or 0),
    }


def _improvement_lane_view(
    *,
    governance: Mapping[str, Any],
    candidate_views: Sequence[Mapping[str, Any]],
    runtime: Mapping[str, Any],
    events: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    last_action = _latest_lane_event(events, lane="improvement", matcher=_is_improvement_event)
    last_completed_at = _latest_lane_timestamp(
        events,
        lambda event: _is_improvement_event(event)
        and _text((event.get("payload") or {}).get("task_outcome_state"), limit=64).lower()
        in {"verified", "ended_unverified"},
    )
    last_failed_at = _latest_lane_timestamp(
        events,
        lambda event: _is_improvement_event(event)
        and _text(event.get("event_type"), limit=64).lower() == "task_execution_failed",
    )
    last_blocked_at = _latest_lane_timestamp(
        events,
        lambda event: (
            _is_improvement_event(event)
            and (
                _text((event.get("payload") or {}).get("task_outcome_state"), limit=64).lower() == "blocked"
                or _text((event.get("payload") or {}).get("autoenqueue_state"), limit=64).lower()
                not in {"", "enqueue_created", "enqueue_deduped"}
            )
        ),
    )
    last_rollback_at = _latest_lane_timestamp(
        events,
        lambda event: _is_improvement_event(event)
        and _text((event.get("payload") or {}).get("task_outcome_state"), limit=64).lower() == "rolled_back",
    )
    return {
        "lane": "improvement",
        "state": _text(governance.get("rollout_guard_state"), limit=64) or "unknown",
        "blocked": bool(governance.get("rollout_guard_blocked")),
        "reasons": _normalize_reason_list(governance.get("rollout_guard_reasons") or []),
        "last_action": last_action,
        "last_completed_at": last_completed_at,
        "last_failed_at": last_failed_at,
        "last_blocked_at": last_blocked_at,
        "last_rollback_at": last_rollback_at,
        "next_candidate_count": len(list(candidate_views or [])),
        "next_candidates": list(candidate_views or []),
        "runtime": {
            "autonomy_decisions_total": int(runtime.get("autonomy_decisions_total") or 0),
            "enqueue_creation_rate": float(runtime.get("enqueue_creation_rate") or 0.0),
            "verified_rate": float(runtime.get("verified_rate") or 0.0),
            "not_verified_rate": float(runtime.get("not_verified_rate") or 0.0),
        },
    }


def _memory_lane_view(
    *,
    status_payload: Mapping[str, Any],
    runtime: Mapping[str, Any],
    events: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    autonomy_governance_payload = status_payload.get("autonomy_governance")
    autonomy_governance = autonomy_governance_payload if isinstance(autonomy_governance_payload, Mapping) else {}
    latest_snapshot = {}
    for snapshot in list(status_payload.get("last_snapshots") or []):
        if isinstance(snapshot, Mapping):
            latest_snapshot = snapshot
            break
    last_action = _latest_lane_event(events, lane="memory_curation", matcher=_is_memory_curation_event)
    last_completed_at = _latest_lane_timestamp(
        events,
        lambda event: _text(event.get("event_type"), limit=64).lower() == "memory_curation_completed",
    )
    last_failed_at = _latest_lane_timestamp(
        events,
        lambda event: _text(event.get("event_type"), limit=64).lower() == "memory_curation_completed"
        and _text((event.get("payload") or {}).get("final_status"), limit=64).lower() == "verification_failed",
    )
    last_blocked_at = _latest_lane_timestamp(
        events,
        lambda event: _text(event.get("event_type"), limit=64).lower() == "memory_curation_autonomy_blocked",
    )
    last_rollback_at = _latest_lane_timestamp(
        events,
        lambda event: _text(event.get("event_type"), limit=64).lower() == "memory_curation_rollback",
    )
    return {
        "lane": "memory_curation",
        "state": _text(autonomy_governance.get("state"), limit=64) or "unknown",
        "blocked": bool(autonomy_governance.get("blocked")),
        "reasons": _normalize_reason_list(autonomy_governance.get("reasons") or []),
        "last_action": last_action,
        "last_completed_at": last_completed_at,
        "last_failed_at": last_failed_at,
        "last_blocked_at": last_blocked_at,
        "last_rollback_at": last_rollback_at,
        "last_snapshot_id": _text(latest_snapshot.get("snapshot_id"), limit=64),
        "last_snapshot_status": _text(latest_snapshot.get("status"), limit=64),
        "next_candidate_count": len(list(status_payload.get("pending_candidates") or [])),
        "next_candidates": [
            _memory_candidate_view(candidate)
            for candidate in list(status_payload.get("pending_candidates") or [])[:5]
            if isinstance(candidate, Mapping)
        ],
        "runtime": {
            "autonomy_completion_rate": float(runtime.get("autonomy_completion_rate") or 0.0),
            "verification_pass_rate": float(runtime.get("verification_pass_rate") or 0.0),
            "retrieval_pass_rate": float(runtime.get("retrieval_pass_rate") or 0.0),
            "rollback_rate": float(runtime.get("rollback_rate") or 0.0),
        },
        "current_metrics": {
            "active_items": int((status_payload.get("current_metrics") or {}).get("active_items") or 0),
            "archived_items": int((status_payload.get("current_metrics") or {}).get("archived_items") or 0),
            "summary_items": int((status_payload.get("current_metrics") or {}).get("summary_items") or 0),
            "stale_active_items": int((status_payload.get("current_metrics") or {}).get("stale_active_items") or 0),
        },
    }


def summarize_phase_e_operator_lanes(lanes: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    blocked_lanes = [
        _text(name, limit=64)
        for name, lane in dict(lanes or {}).items()
        if bool((lane or {}).get("blocked"))
    ]
    last_activity_at = max(
        [
            _text((dict(lane or {}).get("last_action") or {}).get("observed_at"), limit=64)
            for lane in dict(lanes or {}).values()
            if _text((dict(lane or {}).get("last_action") or {}).get("observed_at"), limit=64)
        ]
        or [""]
    )
    return {
        "blocked_lanes": blocked_lanes,
        "blocked_lane_count": len(blocked_lanes),
        "last_activity_at": last_activity_at,
    }


def build_phase_e_operator_snapshot(
    *,
    system_snapshot: Mapping[str, Any],
    observation_summary: Mapping[str, Any],
    recent_events: Sequence[Mapping[str, Any]],
    improvement_governance: Mapping[str, Any],
    improvement_candidate_views: Sequence[Mapping[str, Any]],
    memory_curation_status: Mapping[str, Any],
) -> dict[str, Any]:
    improvement_runtime_payload = observation_summary.get("improvement_runtime")
    improvement_runtime = improvement_runtime_payload if isinstance(improvement_runtime_payload, Mapping) else {}
    memory_runtime_payload = observation_summary.get("memory_curation_runtime")
    memory_runtime = memory_runtime_payload if isinstance(memory_runtime_payload, Mapping) else {}

    lanes = {
        "improvement": _improvement_lane_view(
            governance=improvement_governance,
            candidate_views=improvement_candidate_views,
            runtime=improvement_runtime,
            events=recent_events,
        ),
        "memory_curation": _memory_lane_view(
            status_payload=memory_curation_status,
            runtime=memory_runtime,
            events=recent_events,
        ),
    }
    lane_summary = summarize_phase_e_operator_lanes(lanes)
    return {
        "generated_at": _iso_now(),
        "summary": {
            **lane_summary,
            "system_state": _text((system_snapshot.get("ops") or {}).get("state"), limit=32).lower() or "unknown",
        },
        "system": _system_view(system_snapshot),
        "lanes": lanes,
    }


async def collect_phase_e_operator_snapshot(*, limit: int = 5, queue: Any | None = None) -> dict[str, Any]:
    from gateway.status_snapshot import collect_status_snapshot
    from orchestration.autonomy_observation import (
        build_autonomy_observation_summary,
        get_autonomy_observation_store,
    )
    from orchestration.improvement_candidates import build_candidate_operator_views
    from orchestration.improvement_task_autonomy import (
        build_improvement_task_governance_view,
        get_improvement_task_rollout_guard,
    )
    from orchestration.memory_curation import get_memory_curation_status
    from orchestration.self_improvement_engine import get_improvement_engine
    from orchestration.session_reflection import SessionReflectionLoop
    from orchestration.task_queue import get_queue

    safe_limit = max(1, min(10, int(limit or 5)))
    active_queue = queue or get_queue()
    system_snapshot = await collect_status_snapshot()
    observation_summary = build_autonomy_observation_summary()
    recent_events = get_autonomy_observation_store().iter_events()
    if len(recent_events) > 400:
        recent_events = recent_events[-400:]

    engine = get_improvement_engine()
    normalized_candidates = engine.get_normalized_suggestions(applied=False)
    try:
        combined_candidates = await SessionReflectionLoop().get_improvement_suggestions()
    except Exception:
        combined_candidates = normalized_candidates

    rollout_guard = get_improvement_task_rollout_guard(active_queue)
    improvement_governance = build_improvement_task_governance_view(
        queue=active_queue,
        rollout_guard=rollout_guard,
    )
    memory_curation_status = get_memory_curation_status(
        queue=active_queue,
        stale_days=30,
        limit=safe_limit,
    )

    return build_phase_e_operator_snapshot(
        system_snapshot=system_snapshot,
        observation_summary=observation_summary,
        recent_events=recent_events,
        improvement_governance=improvement_governance,
        improvement_candidate_views=build_candidate_operator_views(combined_candidates, limit=safe_limit),
        memory_curation_status=memory_curation_status,
    )
