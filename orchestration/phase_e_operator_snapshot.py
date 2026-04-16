from __future__ import annotations

from datetime import datetime
from typing import Any, Mapping, Sequence

_ACTION_PRIORITY = {
    "allow": 0,
    "hold": 1,
    "freeze": 2,
    "rollback": 3,
}

_RISK_PRIORITY = {
    "none": 0,
    "low": 1,
    "medium": 2,
    "high": 3,
    "critical": 4,
}

_NAMED_GOVERNANCE_SIGNALS = (
    "strict_force_off",
    "rollout_frozen",
    "rollback_active",
    "verification_backpressure",
    "retrieval_backpressure",
    "degraded_mode",
)

_EXPLAINABILITY_FAILURE_RESULTS = {"failed", "verification_failed", "error"}
_EXPLAINABILITY_BLOCK_RESULTS = {
    "blocked",
    "strict_force_off",
    "cooldown_active",
    "verification_backpressure",
    "retrieval_backpressure",
    "rollout_frozen",
    "rollback_active",
    "runtime_degraded",
    "storage_degraded",
}
_EXPLAINABILITY_ROLLBACK_RESULTS = {"rolled_back", "rollback", "rollback_started", "rollback_progress"}


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


def _merge_unique_texts(values: Sequence[Any] | None, *, limit: int = 6) -> list[str]:
    merged: list[str] = []
    seen: set[str] = set()
    for value in list(values or []):
        item = _text(value, limit=96)
        if not item or item in seen:
            continue
        seen.add(item)
        merged.append(item)
        if len(merged) >= limit:
            break
    return merged


def _pick_highest(values: Sequence[str] | None, *, ranking: Mapping[str, int], default: str) -> str:
    best_value = default
    best_rank = int(ranking.get(default, 0))
    for raw_value in list(values or []):
        value = _text(raw_value, limit=64).lower()
        rank = int(ranking.get(value, -1))
        if rank > best_rank:
            best_value = value
            best_rank = rank
    return best_value


def _governance_action_for_state(state: Any) -> str:
    normalized = _text(state, limit=64).lower()
    if normalized in {"allow", "healthy", "ok", "pass"}:
        return "allow"
    if normalized in {"strict_force_off", "rollout_frozen"}:
        return "freeze"
    if normalized in {"rollback_active", "rollback_cooldown", "rolled_back"}:
        return "rollback"
    return "hold"


def _governance_risk_for_state(state: Any) -> str:
    normalized = _text(state, limit=64).lower()
    if normalized in {"", "allow", "healthy", "ok", "pass"}:
        return "none"
    if normalized in {"disabled", "cadence_skip", "no_candidates", "insufficient_history"}:
        return "low"
    if normalized in {"cooldown_active", "startup_grace", "warn"}:
        return "medium"
    if normalized in {
        "rollout_frozen",
        "rollback_active",
        "rollback_cooldown",
        "verification_blocked",
        "verification_backpressure",
        "retrieval_backpressure",
        "runtime_degraded",
        "storage_degraded",
        "degraded",
    }:
        return "high"
    if normalized in {"strict_force_off", "runtime_critical", "critical"}:
        return "critical"
    return "medium"


def _build_signal_view(
    *,
    lane: str,
    signal: str,
    active: bool = False,
    shadowed: bool = False,
    reasons: Sequence[Any] | None = None,
) -> dict[str, Any]:
    effective_state = signal if active else "allow"
    return {
        "active": bool(active),
        "shadowed": bool(shadowed),
        "lane": _text(lane, limit=64),
        "reasons": _merge_unique_texts(reasons),
        "action": _governance_action_for_state(effective_state),
        "risk_class": _governance_risk_for_state(effective_state),
    }


def _normalized_event_payload(event: Mapping[str, Any]) -> tuple[str, str, Mapping[str, Any]]:
    event_type = _text(event.get("event_type"), limit=80).lower()
    observed_at = _text(event.get("observed_at"), limit=64)
    payload = event.get("payload")
    return event_type, observed_at, payload if isinstance(payload, Mapping) else {}


def _explainability_refs(payload: Mapping[str, Any], *, ref_id: str = "") -> dict[str, Any]:
    request_id = _text(payload.get("request_id"), limit=64)
    incident_key = _text(payload.get("incident_key"), limit=96)
    task_id = _text(payload.get("task_id"), limit=64)
    snapshot_id = _text(payload.get("snapshot_id"), limit=64)
    refs = {
        "request_id": request_id,
        "incident_key": incident_key,
        "task_id": task_id,
        "snapshot_id": snapshot_id,
        "ref_id": _text(ref_id, limit=64),
    }
    return {key: value for key, value in refs.items() if value}


def _improvement_explainability_entry(event: Mapping[str, Any]) -> dict[str, Any]:
    event_type, observed_at, payload = _normalized_event_payload(event)
    result = (
        _text(payload.get("task_outcome_state"), limit=64).lower()
        or _text(payload.get("verification_state"), limit=64).lower()
        or _text(payload.get("autoenqueue_state"), limit=64).lower()
        or _text(payload.get("rollout_guard_state"), limit=64).lower()
        or event_type
    )
    if event_type == "improvement_task_autonomy_event":
        action = "autonomy_decision"
        why = _text(
            (list(payload.get("rollout_guard_reasons") or [])[:1] or [payload.get("rollout_guard_state") or payload.get("autoenqueue_state")])[0],
            limit=120,
        )
        what_changed = _text(payload.get("candidate_id") or payload.get("compiled_task_id"), limit=120)
        ref_id = _text(payload.get("candidate_id") or payload.get("compiled_task_id"), limit=64)
    else:
        action = "task_execution"
        why = _text(payload.get("error_class") or payload.get("verification_state") or payload.get("task_outcome_state"), limit=120)
        what_changed = _text(payload.get("task_id") or payload.get("compiled_task_id") or payload.get("candidate_id"), limit=120)
        ref_id = _text(payload.get("task_id") or payload.get("compiled_task_id"), limit=64)
    return {
        "when": observed_at,
        "lane": "improvement",
        "event_type": event_type,
        "action": action,
        "result": result,
        "why": why,
        "what_changed": what_changed,
        "refs": _explainability_refs(payload, ref_id=ref_id),
    }


def _memory_explainability_entry(event: Mapping[str, Any]) -> dict[str, Any]:
    event_type, observed_at, payload = _normalized_event_payload(event)
    action = "memory_event"
    result = event_type
    why = ""
    what_changed = ""
    if event_type == "memory_curation_autonomy_started":
        action = "autonomy_cycle"
        result = "started"
        what_changed = _text(f"candidate_count:{payload.get('candidate_count')}", limit=120)
    elif event_type == "memory_curation_autonomy_completed":
        action = "autonomy_cycle"
        result = _text(payload.get("status"), limit=64).lower() or "completed"
        why = _text(payload.get("status"), limit=120)
        what_changed = _text(f"snapshot:{payload.get('snapshot_id')}", limit=120)
    elif event_type == "memory_curation_autonomy_blocked":
        action = "autonomy_cycle"
        result = _text(payload.get("state"), limit=64).lower() or "blocked"
        why = _text((list(payload.get("reasons") or [])[:1] or [payload.get("state")])[0], limit=120)
        what_changed = _text(f"snapshot:{payload.get('snapshot_id')}", limit=120)
    elif event_type == "memory_curation_started":
        action = "curation_run"
        result = "started"
        what_changed = _text(f"snapshot:{payload.get('snapshot_id')}", limit=120)
    elif event_type == "memory_curation_completed":
        action = "curation_run"
        result = _text(payload.get("final_status"), limit=64).lower() or "completed"
        why = _text("verification_passed" if bool(payload.get("verification_passed")) else payload.get("final_status"), limit=120)
        what_changed = _text(f"actions:{payload.get('actions_applied')} snapshot:{payload.get('snapshot_id')}", limit=120)
    elif event_type == "memory_summarized":
        action = "summarize"
        result = "applied"
        what_changed = _text(payload.get("summary_key") or payload.get("source_category"), limit=120)
    elif event_type == "memory_archived":
        action = "archive"
        result = "applied"
        what_changed = _text(payload.get("archived_key") or payload.get("archived_category"), limit=120)
    elif event_type == "memory_devalued":
        action = "devalue"
        result = "applied"
        what_changed = _text(payload.get("key") or payload.get("category"), limit=120)
    elif event_type == "memory_curation_rollback_started":
        action = "rollback"
        result = "rollback_started"
        what_changed = _text(payload.get("snapshot_id"), limit=120)
    elif event_type == "memory_curation_rollback_progress":
        action = "rollback"
        result = "rollback_progress"
        why = _text(payload.get("stage"), limit=120)
        what_changed = _text(payload.get("snapshot_id"), limit=120)
    elif event_type == "memory_curation_rollback":
        action = "rollback"
        result = "rolled_back"
        what_changed = _text(payload.get("snapshot_id"), limit=120)
    return {
        "when": observed_at,
        "lane": "memory_curation",
        "event_type": event_type,
        "action": action,
        "result": result,
        "why": why,
        "what_changed": what_changed,
        "refs": _explainability_refs(payload, ref_id=_text(payload.get("snapshot_id"), limit=64)),
    }


def _explainability_entry(event: Mapping[str, Any]) -> dict[str, Any]:
    if _is_improvement_event(event):
        return _improvement_explainability_entry(event)
    if _is_memory_curation_event(event):
        return _memory_explainability_entry(event)
    return {}


def summarize_phase_e_explainability_entries(entries: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    items = list(entries or [])
    lanes = _merge_unique_texts([_text(item.get("lane"), limit=64) for item in items], limit=4)
    latest_at = max([_text(item.get("when"), limit=64) for item in items if _text(item.get("when"), limit=64)] or [""])
    failure_count = sum(1 for item in items if _text(item.get("result"), limit=64).lower() in _EXPLAINABILITY_FAILURE_RESULTS)
    blocked_count = sum(1 for item in items if _text(item.get("result"), limit=64).lower() in _EXPLAINABILITY_BLOCK_RESULTS)
    rollback_count = sum(1 for item in items if _text(item.get("result"), limit=64).lower() in _EXPLAINABILITY_ROLLBACK_RESULTS)
    return {
        "count": len(items),
        "lanes": lanes,
        "latest_at": latest_at,
        "failure_count": failure_count,
        "blocked_count": blocked_count,
        "rollback_count": rollback_count,
    }


def build_phase_e_explainability(*, recent_events: Sequence[Mapping[str, Any]], limit: int = 6) -> dict[str, Any]:
    normalized_items = [
        item
        for item in (_explainability_entry(event) for event in list(recent_events or []))
        if item
    ]
    normalized_items = sorted(normalized_items, key=lambda item: _text(item.get("when"), limit=64), reverse=True)
    recent_feed = normalized_items[: max(1, int(limit))]

    def _first_matching(predicate) -> dict[str, Any]:
        for item in recent_feed:
            if predicate(item):
                return dict(item)
        return {}

    latest_by_lane = {
        lane: _first_matching(lambda item, lane_name=lane: _text(item.get("lane"), limit=64) == lane_name)
        for lane in ("improvement", "memory_curation")
    }
    latest_block = _first_matching(lambda item: _text(item.get("result"), limit=64).lower() in _EXPLAINABILITY_BLOCK_RESULTS)
    latest_failure = _first_matching(lambda item: _text(item.get("result"), limit=64).lower() in _EXPLAINABILITY_FAILURE_RESULTS)
    latest_rollback = _first_matching(lambda item: _text(item.get("result"), limit=64).lower() in _EXPLAINABILITY_ROLLBACK_RESULTS)

    return {
        **summarize_phase_e_explainability_entries(recent_feed),
        "latest_by_lane": latest_by_lane,
        "latest_block": latest_block,
        "latest_failure": latest_failure,
        "latest_rollback": latest_rollback,
        "recent_feed": recent_feed,
    }


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


def _approval_risk_class(*, recommendation: Any, requested_action: Any, approval_reason: Any) -> str:
    rec = _text(recommendation, limit=64).lower()
    action = _text(requested_action, limit=64).lower()
    reason = _text(approval_reason, limit=96).lower()
    if rec == "rollback" or action == "rollback":
        return "critical"
    if rec == "promote" or action == "promote_canary":
        return "high"
    if "approval" in reason or action == "hold":
        return "medium"
    return "low"


def _approval_lane(payload: Mapping[str, Any], *, recommendation: Any, requested_action: Any) -> str:
    explicit_lane = _text(payload.get("lane") or payload.get("approval_scope"), limit=64).lower()
    if explicit_lane:
        return explicit_lane
    rec = _text(recommendation, limit=64).lower()
    action = _text(requested_action, limit=64).lower()
    if rec in {"rollback", "promote"} or action in {"rollback", "promote_canary"}:
        return "improvement"
    return "system"


def _approval_evidence_view(
    *,
    row: Mapping[str, Any],
    payload: Mapping[str, Any],
    limit: int = 3,
) -> dict[str, Any]:
    scorecard = payload.get("scorecard")
    scorecard_payload = scorecard if isinstance(scorecard, Mapping) else {}
    evidence: dict[str, Any] = {
        "audit_id": _text(row.get("audit_id"), limit=64),
        "report_path": _text(row.get("report_path"), limit=160),
        "overall_score": scorecard_payload.get("overall_score"),
        "autonomy_level": _text(scorecard_payload.get("autonomy_level"), limit=32),
        "window_days": payload.get("window_days"),
        "baseline_days": payload.get("baseline_days"),
    }
    compact: dict[str, Any] = {}
    count = 0
    for key, value in evidence.items():
        if value in {None, "", []}:
            continue
        compact[key] = value
        count += 1
        if count >= limit:
            break
    return compact


def _approval_rollback_path(plan: Mapping[str, Any]) -> dict[str, Any]:
    action = _text(plan.get("action"), limit=64).lower()
    current_canary = int(plan.get("current_canary") or 0)
    next_canary = int(plan.get("next_canary") or 0)
    if action == "promote_canary":
        return {
            "available": True,
            "action": "rollback",
            "target_canary": current_canary,
            "strict_force_off": True,
        }
    if action == "rollback":
        return {
            "available": False,
            "action": "manual_recovery",
            "target_canary": next_canary,
            "strict_force_off": bool(plan.get("strict_force_off")),
        }
    return {
        "available": False,
        "action": "none",
        "target_canary": current_canary,
        "strict_force_off": bool(plan.get("strict_force_off")),
    }


def _build_improvement_governance_lane(governance: Mapping[str, Any]) -> dict[str, Any]:
    state = _text(governance.get("rollout_guard_state"), limit=64).lower() or "allow"
    blocked = bool(governance.get("rollout_guard_blocked"))
    reasons = _normalize_reason_list(governance.get("rollout_guard_reasons") or [])
    shadowed_states = [
        _text(item, limit=64).lower()
        for item in list(governance.get("shadowed_guard_states") or [])
        if _text(item, limit=64)
    ]
    shadowed_reason_map = {
        _text(key, limit=64).lower(): _normalize_reason_list(values, limit=3)
        for key, values in dict(governance.get("shadowed_guard_reasons") or {}).items()
        if _text(key, limit=64)
    }
    verification_backpressure = dict(governance.get("verification_backpressure") or {})
    signals = {
        "strict_force_off": _build_signal_view(
            lane="improvement",
            signal="strict_force_off",
            active=state == "strict_force_off",
            shadowed="strict_force_off" in shadowed_states,
            reasons=reasons if state == "strict_force_off" else shadowed_reason_map.get("strict_force_off", []),
        ),
        "rollout_frozen": _build_signal_view(
            lane="improvement",
            signal="rollout_frozen",
            active=state == "rollout_frozen",
            shadowed="rollout_frozen" in shadowed_states,
            reasons=reasons if state == "rollout_frozen" else shadowed_reason_map.get("rollout_frozen", []),
        ),
        "rollback_active": _build_signal_view(
            lane="improvement",
            signal="rollback_active",
            active=state == "rollback_active",
            shadowed="rollback_active" in shadowed_states,
            reasons=reasons if state == "rollback_active" else shadowed_reason_map.get("rollback_active", []),
        ),
        "verification_backpressure": _build_signal_view(
            lane="improvement",
            signal="verification_backpressure",
            active=bool(verification_backpressure.get("active")),
            shadowed=bool(verification_backpressure.get("shadowed")) or "verification_backpressure" in shadowed_states,
            reasons=(
                list(verification_backpressure.get("reasons") or [])
                or (reasons if state == "verification_backpressure" else shadowed_reason_map.get("verification_backpressure", []))
            ),
        ),
        "retrieval_backpressure": _build_signal_view(lane="improvement", signal="retrieval_backpressure"),
        "degraded_mode": _build_signal_view(lane="improvement", signal="degraded_mode"),
    }
    active_states = [state] if blocked and state != "allow" else []
    return {
        "lane": "improvement",
        "state": state,
        "blocked": blocked,
        "action": _governance_action_for_state(state),
        "risk_class": _governance_risk_for_state(state),
        "reasons": reasons,
        "active_states": active_states,
        "shadowed_states": shadowed_states[:4],
        "signals": signals,
    }


def _build_memory_governance_lane(status_payload: Mapping[str, Any]) -> dict[str, Any]:
    autonomy_governance_payload = status_payload.get("autonomy_governance")
    autonomy_governance = autonomy_governance_payload if isinstance(autonomy_governance_payload, Mapping) else {}
    quality_governance_payload = status_payload.get("quality_governance")
    quality_governance = quality_governance_payload if isinstance(quality_governance_payload, Mapping) else {}
    state = _text(autonomy_governance.get("state"), limit=64).lower() or "allow"
    blocked = bool(autonomy_governance.get("blocked"))
    reasons = _normalize_reason_list(autonomy_governance.get("reasons") or [])
    retrieval_state = _text(quality_governance.get("state"), limit=64).lower()
    retrieval_blocked = bool(quality_governance.get("blocked"))
    degrade_mode = _text(autonomy_governance.get("degrade_mode"), limit=64).lower()
    semantic_store_available = bool(autonomy_governance.get("semantic_store_available", True))
    retrieval_active = state == "retrieval_backpressure" or retrieval_state == "retrieval_backpressure"
    retrieval_shadowed = retrieval_blocked and not retrieval_active
    rollback_active = state in {"rollback_cooldown"}
    degraded_active = (
        state in {"runtime_degraded", "storage_degraded"}
        or degrade_mode in {"degraded", "emergency"}
        or not semantic_store_available
    )
    signals = {
        "strict_force_off": _build_signal_view(lane="memory_curation", signal="strict_force_off"),
        "rollout_frozen": _build_signal_view(lane="memory_curation", signal="rollout_frozen"),
        "rollback_active": _build_signal_view(
            lane="memory_curation",
            signal="rollback_active",
            active=rollback_active,
            reasons=reasons if rollback_active else [],
        ),
        "verification_backpressure": _build_signal_view(lane="memory_curation", signal="verification_backpressure"),
        "retrieval_backpressure": _build_signal_view(
            lane="memory_curation",
            signal="retrieval_backpressure",
            active=retrieval_active,
            shadowed=retrieval_shadowed,
            reasons=list(quality_governance.get("reasons") or []),
        ),
        "degraded_mode": _build_signal_view(
            lane="memory_curation",
            signal="degraded_mode",
            active=degraded_active,
            reasons=(
                reasons
                if degraded_active and state in {"runtime_degraded", "storage_degraded"}
                else [f"degrade_mode:{degrade_mode}"] if degrade_mode in {"degraded", "emergency"} else []
            )
            + ([] if semantic_store_available else ["semantic_store_unavailable"]),
        ),
    }
    active_states = [state] if blocked and state != "allow" else []
    shadowed_states = ["retrieval_backpressure"] if retrieval_shadowed else []
    return {
        "lane": "memory_curation",
        "state": state,
        "blocked": blocked,
        "action": _governance_action_for_state(state),
        "risk_class": _governance_risk_for_state(state),
        "reasons": reasons,
        "active_states": active_states,
        "shadowed_states": shadowed_states,
        "signals": signals,
    }


def _build_system_governance_lane(system_view: Mapping[str, Any]) -> dict[str, Any]:
    state = _text(system_view.get("state"), limit=64).lower() or "unknown"
    reasons = _normalize_reason_list(system_view.get("degraded_reasons") or [], limit=6)
    blocked = state not in {"healthy", "ok", "pass", ""}
    active_states = ["degraded_mode"] if blocked else []
    return {
        "lane": "system",
        "state": state,
        "blocked": blocked,
        "action": _governance_action_for_state(state),
        "risk_class": _governance_risk_for_state(state),
        "reasons": reasons,
        "active_states": active_states,
        "shadowed_states": [],
        "signals": {
            "strict_force_off": _build_signal_view(lane="system", signal="strict_force_off"),
            "rollout_frozen": _build_signal_view(lane="system", signal="rollout_frozen"),
            "rollback_active": _build_signal_view(lane="system", signal="rollback_active"),
            "verification_backpressure": _build_signal_view(lane="system", signal="verification_backpressure"),
            "retrieval_backpressure": _build_signal_view(lane="system", signal="retrieval_backpressure"),
            "degraded_mode": _build_signal_view(
                lane="system",
                signal="degraded_mode",
                active=blocked,
                reasons=reasons,
            ),
        },
    }


def summarize_phase_e_pending_approvals(items: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    pending_items = list(items or [])
    requested_actions = _merge_unique_texts(
        [_text(item.get("requested_action"), limit=64).lower() for item in pending_items],
        limit=6,
    )
    lanes = _merge_unique_texts(
        [_text(item.get("lane"), limit=64).lower() for item in pending_items],
        limit=6,
    )
    risk_classes = [
        _text(item.get("risk_class"), limit=32).lower()
        for item in pending_items
        if _text(item.get("risk_class"), limit=32)
    ]
    pending_minutes_values = [
        float(item.get("pending_minutes") or 0.0)
        for item in pending_items
        if item.get("pending_minutes") not in {None, ""}
    ]
    return {
        "pending_count": len(pending_items),
        "highest_risk_class": _pick_highest(risk_classes, ranking=_RISK_PRIORITY, default="none"),
        "requested_actions": requested_actions,
        "lanes": lanes,
        "oldest_pending_minutes": max(pending_minutes_values or [0.0]),
    }


def build_phase_e_approval_surface(*, queue: Any, limit: int = 5) -> dict[str, Any]:
    if queue is None or not hasattr(queue, "list_autonomy_change_requests"):
        items: list[dict[str, Any]] = []
        summary = summarize_phase_e_pending_approvals(items)
        return {
            "state": "clear",
            "blocked": False,
            **summary,
            "items": items,
        }

    rows = list(queue.list_autonomy_change_requests(statuses=["pending_approval"], limit=max(1, int(limit))) or [])
    rows = list(reversed(rows))
    items: list[dict[str, Any]] = []
    for row in rows:
        payload_value = row.get("payload")
        payload = payload_value if isinstance(payload_value, Mapping) else {}
        plan_value = payload.get("proposed_plan")
        plan = plan_value if isinstance(plan_value, Mapping) else {}
        recommendation = _text(row.get("recommendation"), limit=64).lower() or _text(plan.get("recommendation"), limit=64).lower()
        requested_action = _text(plan.get("action"), limit=64).lower() or recommendation or "hold"
        approval_reason = _text(payload.get("approval_reason") or row.get("reason"), limit=120)
        risk_class = _approval_risk_class(
            recommendation=recommendation,
            requested_action=requested_action,
            approval_reason=approval_reason,
        )
        items.append(
            {
                "request_id": _text(row.get("id"), limit=64),
                "audit_id": _text(row.get("audit_id"), limit=64),
                "lane": _approval_lane(payload, recommendation=recommendation, requested_action=requested_action),
                "risk_class": risk_class,
                "requested_action": requested_action or "hold",
                "recommendation": recommendation or "hold",
                "status": _text(row.get("status"), limit=32) or "pending_approval",
                "pending_minutes": float(row.get("pending_minutes") or 0.0) if row.get("pending_minutes") not in {None, ""} else None,
                "pending_since": _text(payload.get("pending_since") or row.get("updated_at"), limit=64),
                "updated_at": _text(row.get("updated_at"), limit=64),
                "approval_reason": approval_reason,
                "approval_required_actions": [
                    _text(item, limit=32).lower()
                    for item in list(payload.get("approval_required_actions") or [])
                    if _text(item, limit=32)
                ][:4],
                "rationale": _text(plan.get("reason") or approval_reason, limit=160),
                "evidence": _approval_evidence_view(row=row, payload=payload, limit=4),
                "rollback_path": _approval_rollback_path(plan),
            }
        )
    summary = summarize_phase_e_pending_approvals(items)
    return {
        "state": "approval_required" if summary["pending_count"] > 0 else "clear",
        "blocked": summary["pending_count"] > 0,
        **summary,
        "items": items,
    }


def _aggregate_governance_signals(lanes: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    aggregated: dict[str, Any] = {}
    for signal_name in _NAMED_GOVERNANCE_SIGNALS:
        lanes_with_signal: list[str] = []
        reasons: list[str] = []
        actions: list[str] = []
        risks: list[str] = []
        active = False
        shadowed = False
        for lane_name, lane in dict(lanes or {}).items():
            signal = dict((lane or {}).get("signals") or {}).get(signal_name)
            if not isinstance(signal, Mapping):
                continue
            if bool(signal.get("active")) or bool(signal.get("shadowed")):
                lanes_with_signal.append(_text(lane_name, limit=64))
            if bool(signal.get("active")):
                active = True
            if bool(signal.get("shadowed")):
                shadowed = True
            reasons.extend(list(signal.get("reasons") or []))
            actions.append(_text(signal.get("action"), limit=32).lower())
            risks.append(_text(signal.get("risk_class"), limit=32).lower())
        aggregated[signal_name] = {
            "active": active,
            "shadowed": shadowed,
            "lanes": _merge_unique_texts(lanes_with_signal, limit=4),
            "reasons": _merge_unique_texts(reasons, limit=6),
            "action": _pick_highest(actions, ranking=_ACTION_PRIORITY, default="allow"),
            "risk_class": _pick_highest(risks, ranking=_RISK_PRIORITY, default="none"),
        }
    return aggregated


def summarize_phase_e_governance_lanes(lanes: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    blocked_lanes = [
        _text(name, limit=64)
        for name, lane in dict(lanes or {}).items()
        if bool((lane or {}).get("blocked"))
    ]
    active_states = _merge_unique_texts(
        [
            item
            for lane in dict(lanes or {}).values()
            for item in list((lane or {}).get("active_states") or [])
        ],
        limit=8,
    )
    prefixed_reasons = [
        f"{_text(name, limit=64)}:{reason}"
        for name, lane in dict(lanes or {}).items()
        for reason in list((lane or {}).get("reasons") or [])
    ]
    lane_actions = [
        _text((lane or {}).get("action"), limit=32).lower()
        for lane in dict(lanes or {}).values()
        if _text((lane or {}).get("action"), limit=32)
    ]
    lane_risks = [
        _text((lane or {}).get("risk_class"), limit=32).lower()
        for lane in dict(lanes or {}).values()
        if _text((lane or {}).get("risk_class"), limit=32)
    ]
    best_state = "allow"
    best_state_score = (-1, -1)
    for lane in dict(lanes or {}).values():
        if not bool((lane or {}).get("blocked")):
            continue
        state = _text((lane or {}).get("state"), limit=64).lower()
        if not state:
            continue
        state_score = (
            int(_RISK_PRIORITY.get(_governance_risk_for_state(state), 0)),
            int(_ACTION_PRIORITY.get(_governance_action_for_state(state), 0)),
        )
        if state_score > best_state_score:
            best_state = state
            best_state_score = state_score
    return {
        "blocked_lanes": blocked_lanes,
        "blocked_lane_count": len(blocked_lanes),
        "active_states": active_states,
        "state": best_state,
        "action": _pick_highest(lane_actions, ranking=_ACTION_PRIORITY, default="allow"),
        "highest_risk_class": _pick_highest(lane_risks, ranking=_RISK_PRIORITY, default="none"),
        "reasons": _merge_unique_texts(prefixed_reasons, limit=6),
    }


def build_phase_e_governance_surface(
    *,
    system_view: Mapping[str, Any],
    improvement_governance: Mapping[str, Any],
    memory_curation_status: Mapping[str, Any],
) -> dict[str, Any]:
    lanes = {
        "improvement": _build_improvement_governance_lane(improvement_governance),
        "memory_curation": _build_memory_governance_lane(memory_curation_status),
        "system": _build_system_governance_lane(system_view),
    }
    summary = summarize_phase_e_governance_lanes(lanes)
    signals = _aggregate_governance_signals(lanes)
    active_signal_count = sum(1 for signal in signals.values() if bool((signal or {}).get("active")))
    shadowed_signal_count = sum(1 for signal in signals.values() if bool((signal or {}).get("shadowed")))
    return {
        **summary,
        "blocked": bool(summary.get("blocked_lane_count")),
        "active_signal_count": active_signal_count,
        "shadowed_signal_count": shadowed_signal_count,
        "signals": signals,
        "lanes": lanes,
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
    approval_surface: Mapping[str, Any],
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
    system_view = _system_view(system_snapshot)
    lane_summary = summarize_phase_e_operator_lanes(lanes)
    explainability = build_phase_e_explainability(recent_events=recent_events, limit=6)
    governance = build_phase_e_governance_surface(
        system_view=system_view,
        improvement_governance=improvement_governance,
        memory_curation_status=memory_curation_status,
    )
    return {
        "generated_at": _iso_now(),
        "summary": {
            **lane_summary,
            "system_state": _text((system_snapshot.get("ops") or {}).get("state"), limit=32).lower() or "unknown",
            "governance_state": _text(governance.get("state"), limit=64),
            "governance_action": _text(governance.get("action"), limit=32),
            "governance_risk_class": _text(governance.get("highest_risk_class"), limit=32),
            "approval_pending_count": int(approval_surface.get("pending_count") or 0),
            "approval_highest_risk_class": _text(approval_surface.get("highest_risk_class"), limit=32),
            "explainability_latest_at": _text(explainability.get("latest_at"), limit=64),
            "explainability_count": int(explainability.get("count") or 0),
        },
        "system": system_view,
        "lanes": lanes,
        "governance": governance,
        "approval": dict(approval_surface or {}),
        "explainability": explainability,
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
    approval_surface = build_phase_e_approval_surface(queue=active_queue, limit=safe_limit)

    return build_phase_e_operator_snapshot(
        system_snapshot=system_snapshot,
        observation_summary=observation_summary,
        recent_events=recent_events,
        improvement_governance=improvement_governance,
        improvement_candidate_views=build_candidate_operator_views(combined_candidates, limit=safe_limit),
        memory_curation_status=memory_curation_status,
        approval_surface=approval_surface,
    )
