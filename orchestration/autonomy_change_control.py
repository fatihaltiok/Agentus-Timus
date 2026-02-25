"""M6.2/M6.3 Audit -> Change-Request -> Apply + optional Approval Layer."""

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name, "true" if default else "false").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def _change_requests_enabled() -> bool:
    if _env_bool("AUTONOMY_COMPAT_MODE", True):
        return False
    return _env_bool("AUTONOMY_AUDIT_CHANGE_REQUESTS_ENABLED", False)


def _approval_enabled() -> bool:
    if _env_bool("AUTONOMY_COMPAT_MODE", True):
        return False
    return _env_bool("AUTONOMY_AUDIT_CHANGE_APPROVAL_ENABLED", False)


def _approval_auto_approve() -> bool:
    if _env_bool("AUTONOMY_COMPAT_MODE", True):
        return False
    return _env_bool("AUTONOMY_AUDIT_CHANGE_AUTO_APPROVE", False)


def _approval_auto_approver() -> str:
    return str(os.getenv("AUTONOMY_AUDIT_CHANGE_AUTO_APPROVER", "system") or "system").strip() or "system"


def _approval_required_actions() -> set[str]:
    raw = str(os.getenv("AUTONOMY_AUDIT_CHANGE_APPROVAL_REQUIRED_ACTIONS", "rollback,promote") or "")
    items = {p.strip().lower() for p in raw.split(",") if p.strip()}
    return items or {"rollback", "promote"}


def _approval_promote_min_step() -> int:
    return _to_int(os.getenv("AUTONOMY_AUDIT_CHANGE_APPROVAL_PROMOTE_MIN_STEP", "10"), default=10, minimum=1)


def _approval_sla_hours() -> int:
    return _to_int(os.getenv("AUTONOMY_AUDIT_CHANGE_APPROVAL_SLA_HOURS", "12"), default=12, minimum=1)


def _approval_escalation_enabled() -> bool:
    if _env_bool("AUTONOMY_COMPAT_MODE", True):
        return False
    return _env_bool("AUTONOMY_AUDIT_CHANGE_APPROVAL_ESCALATION_ENABLED", True)


def _approval_escalation_task_enabled() -> bool:
    if _env_bool("AUTONOMY_COMPAT_MODE", True):
        return False
    return _env_bool("AUTONOMY_AUDIT_CHANGE_APPROVAL_ESCALATION_TASK_ENABLED", True)


def _approval_escalation_min_interval_min() -> int:
    return _to_int(
        os.getenv("AUTONOMY_AUDIT_CHANGE_APPROVAL_ESCALATION_MIN_INTERVAL_MIN", "60"),
        default=60,
        minimum=1,
    )


def _approval_auto_reject_on_timeout() -> bool:
    if _env_bool("AUTONOMY_COMPAT_MODE", True):
        return False
    return _env_bool("AUTONOMY_AUDIT_CHANGE_APPROVAL_AUTO_REJECT_ON_TIMEOUT", False)


def _to_int(value: Any, default: int, minimum: int) -> int:
    try:
        return max(minimum, int(value))
    except Exception:
        return max(minimum, int(default))


def _parse_iso(value: Optional[str]) -> Optional[datetime]:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw)
    except Exception:
        return None


def _load_report_from_path(path: Optional[str]) -> Optional[Dict[str, Any]]:
    p = Path(str(path or "").strip())
    if not p.exists() or not p.is_file():
        return None
    try:
        loaded = json.loads(p.read_text(encoding="utf-8"))
        return loaded if isinstance(loaded, dict) else None
    except Exception:
        return None


def _build_audit_id(*, report: Dict[str, Any], report_path: Optional[str]) -> str:
    ts = str(report.get("timestamp") or "")
    recommendation = str(report.get("rollout_policy", {}).get("recommendation") or "")
    score = str(report.get("scorecard", {}).get("overall_score") or "")
    source = f"{ts}|{report_path or ''}|{recommendation}|{score}"
    return hashlib.sha256(source.encode("utf-8", errors="ignore")).hexdigest()[:24]


def _action_plan_for_request(*, queue, request: Dict[str, Any]) -> Dict[str, Any]:
    recommendation = str(request.get("recommendation") or "hold").strip().lower() or "hold"
    current_canary_state = queue.get_policy_runtime_state("canary_percent_override")
    hardening_freeze_state = queue.get_policy_runtime_state("hardening_rollout_freeze")
    hardening_freeze_active = str((hardening_freeze_state or {}).get("state_value") or "false").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    try:
        current_canary = int(
            str((current_canary_state or {}).get("state_value") or os.getenv("AUTONOMY_CANARY_PERCENT", "0")).strip()
        )
    except Exception:
        current_canary = 0
    current_canary = max(0, min(100, current_canary))

    action = "hold"
    next_canary = current_canary
    strict_force_off = None
    reason = str(request.get("reason") or "audit_change_request")
    promote_step = 0

    if recommendation == "rollback":
        action = "rollback"
        next_canary = 0
        strict_force_off = True
    elif recommendation == "promote":
        if hardening_freeze_active:
            action = "hold"
            reason = "hardening_freeze_active"
            return {
                "recommendation": recommendation,
                "action": action,
                "reason": reason,
                "current_canary": current_canary,
                "next_canary": current_canary,
                "strict_force_off": strict_force_off,
                "promote_step": promote_step,
                "promote_jump": 0,
                "hardening_freeze_active": True,
            }
        promote_step = _to_int(os.getenv("AUTONOMY_AUDIT_CHANGE_PROMOTE_STEP", "5"), default=5, minimum=1)
        max_canary = max(
            0,
            min(
                100,
                _to_int(
                    os.getenv("AUTONOMY_AUDIT_CHANGE_MAX_CANARY", "100"),
                    default=100,
                    minimum=1,
                ),
            ),
        )
        next_canary = max(0, min(max_canary, current_canary + promote_step))
        if next_canary > current_canary:
            action = "promote_canary"
            strict_force_off = False
        else:
            action = "hold"
            reason = "promote_noop_max_canary_reached"

    return {
        "recommendation": recommendation,
        "action": action,
        "reason": reason,
        "current_canary": current_canary,
        "next_canary": next_canary,
        "strict_force_off": strict_force_off,
        "promote_step": promote_step,
        "promote_jump": max(0, next_canary - current_canary),
        "hardening_freeze_active": hardening_freeze_active,
    }


def _approval_requirement(plan: Dict[str, Any]) -> Dict[str, Any]:
    if not _approval_enabled():
        return {"required": False, "reason": "approval_disabled"}

    required_actions = _approval_required_actions()
    recommendation = str(plan.get("recommendation") or "hold").strip().lower()
    action = str(plan.get("action") or "hold").strip().lower()
    jump = int(plan.get("promote_jump", 0) or 0)

    if recommendation == "rollback" and "rollback" in required_actions:
        return {"required": True, "reason": "rollback_requires_approval"}
    if recommendation == "promote" and "promote" in required_actions:
        min_jump = _approval_promote_min_step()
        if action == "promote_canary" and jump >= min_jump:
            return {"required": True, "reason": f"promote_jump_requires_approval:{jump}"}
    if action == "hold" and "hold" in required_actions:
        return {"required": True, "reason": "hold_requires_approval"}

    return {"required": False, "reason": "not_required"}


def _update_pending_approval_runtime(*, queue, observed_at: Optional[str] = None) -> int:
    pending = queue.list_autonomy_change_requests(statuses=["pending_approval"], limit=500)
    count = len(pending)
    now_iso = observed_at or datetime.now().isoformat()
    queue.set_policy_runtime_state(
        "audit_change_pending_approval_count",
        str(count),
        metadata_update={"source": "audit_change_control"},
        observed_at=now_iso,
    )
    return count


def _pending_since_for_request(request: Dict[str, Any]) -> Optional[datetime]:
    payload = request.get("payload")
    if not isinstance(payload, dict):
        payload = {}
    pending_since = _parse_iso(str(payload.get("pending_since") or "").strip())
    if pending_since is not None:
        return pending_since
    for key in ("updated_at", "created_at"):
        parsed = _parse_iso(str(request.get(key) or "").strip())
        if parsed is not None:
            return parsed
    return None


def resolve_change_request_id(
    *,
    queue=None,
    request_id: str,
    statuses: Optional[list[str]] = None,
    limit: int = 500,
) -> Dict[str, Any]:
    if queue is None:
        from orchestration.task_queue import get_queue

        queue = get_queue()

    rid = str(request_id or "").strip()
    if not rid:
        return {"status": "error", "error": "missing_request_id"}
    if len(rid) >= 16 and queue.get_autonomy_change_request(rid):
        return {"status": "ok", "request_id": rid, "resolution": "exact"}

    candidates = queue.list_autonomy_change_requests(statuses=statuses, limit=max(1, int(limit)))
    matches = [str(item.get("id") or "") for item in candidates if str(item.get("id") or "").startswith(rid)]
    matches = [m for m in matches if m]
    if len(matches) == 1:
        return {"status": "ok", "request_id": matches[0], "resolution": "prefix"}
    if not matches:
        return {"status": "error", "error": "request_not_found", "request_id": rid}
    return {"status": "error", "error": "request_id_ambiguous", "request_id": rid, "matches": matches[:5]}


def list_pending_approval_change_requests(
    *,
    queue=None,
    limit: int = 20,
) -> Dict[str, Any]:
    if queue is None:
        from orchestration.task_queue import get_queue

        queue = get_queue()

    now = datetime.now()
    rows = queue.list_autonomy_change_requests(statuses=["pending_approval"], limit=max(1, int(limit)))
    rows = list(reversed(rows))  # aelteste zuerst
    items: list[Dict[str, Any]] = []
    for row in rows:
        since = _pending_since_for_request(row)
        pending_min = None
        if since is not None:
            pending_min = round(max(0.0, (now - since).total_seconds() / 60.0), 2)
        payload = row.get("payload") if isinstance(row.get("payload"), dict) else {}
        items.append(
            {
                "id": str(row.get("id") or ""),
                "audit_id": str(row.get("audit_id") or ""),
                "recommendation": str(row.get("recommendation") or "hold"),
                "reason": str(row.get("reason") or ""),
                "status": str(row.get("status") or "pending_approval"),
                "pending_minutes": pending_min,
                "pending_since": str(payload.get("pending_since") or row.get("updated_at") or ""),
                "updated_at": str(row.get("updated_at") or ""),
            }
        )
    return {"status": "ok", "count": len(items), "items": items}


def create_change_request_from_audit(
    *,
    queue=None,
    report: Optional[Dict[str, Any]] = None,
    report_path: Optional[str] = None,
    source: str = "autonomy_audit_report",
) -> Dict[str, Any]:
    if queue is None:
        from orchestration.task_queue import get_queue

        queue = get_queue()

    final_report = report if isinstance(report, dict) else _load_report_from_path(report_path)
    if not isinstance(final_report, dict):
        return {"status": "error", "error": "audit_report_missing"}

    recommendation = str(
        final_report.get("rollout_policy", {}).get("recommendation", "hold")
    ).strip().lower() or "hold"
    audit_id = _build_audit_id(report=final_report, report_path=report_path)
    report_file = str(report_path or "").strip() or None
    if report_file is None:
        state = queue.get_policy_runtime_state("audit_report_last_path")
        if state:
            report_file = str(state.get("state_value") or "").strip() or None

    payload = {
        "timestamp": final_report.get("timestamp"),
        "window_days": final_report.get("window_days"),
        "baseline_days": final_report.get("baseline_days"),
        "rollout_policy": final_report.get("rollout_policy", {}),
        "scorecard": {
            "overall_score": final_report.get("scorecard", {}).get("overall_score"),
            "autonomy_level": final_report.get("scorecard", {}).get("autonomy_level"),
        },
    }
    created = queue.create_autonomy_change_request(
        audit_id=audit_id,
        recommendation=recommendation,
        source=source,
        report_path=report_file,
        payload=payload,
        status="proposed",
        reason=str(final_report.get("rollout_policy", {}).get("reason") or "audit_recommendation"),
    )
    created["audit_id"] = audit_id
    created["report_path"] = report_file
    created["created"] = bool(created.get("created", False))
    created["status"] = "ok"
    return created


def set_change_request_approval(
    *,
    queue=None,
    request_id: str,
    approved: bool,
    approver: str = "human",
    note: Optional[str] = None,
) -> Dict[str, Any]:
    if queue is None:
        from orchestration.task_queue import get_queue

        queue = get_queue()

    rid = str(request_id or "").strip()
    if not rid:
        return {"status": "error", "error": "missing_request_id"}
    resolved = resolve_change_request_id(queue=queue, request_id=rid)
    if resolved.get("status") != "ok":
        return resolved
    rid = str(resolved.get("request_id") or "")
    request = queue.get_autonomy_change_request(rid)
    if not request:
        return {"status": "error", "error": "request_not_found", "request_id": rid}

    current_status = str(request.get("status") or "proposed").strip().lower()
    if current_status in {"applied", "rejected", "error", "skipped"}:
        return {
            "status": "ok",
            "action": "approval_noop",
            "request_id": rid,
            "request_status": current_status,
        }

    now_iso = datetime.now().isoformat()
    decision = "approved" if approved else "rejected"
    queue.update_autonomy_change_request(
        rid,
        status=decision,
        action=("approved" if approved else "rejected"),
        reason=note or str(request.get("reason") or "manual_decision"),
        payload_update={
            "approval": {
                "decision": decision,
                "approver": str(approver or "human"),
                "note": note,
                "decided_at": now_iso,
            }
        },
        # applied_at bleibt dem tatsaechlichen Apply-Schritt vorbehalten.
        applied_at=None,
    )
    queue.set_policy_runtime_state(
        "audit_change_last_approval_status",
        decision,
        metadata_update={"request_id": rid, "approver": str(approver or "human"), "note": note or ""},
        observed_at=now_iso,
    )
    queue.set_policy_runtime_state(
        "audit_change_last_approval_request_id",
        rid,
        metadata_update={"decision": decision},
        observed_at=now_iso,
    )
    queue.set_policy_runtime_state(
        "audit_change_last_approver",
        str(approver or "human"),
        metadata_update={"decision": decision, "request_id": rid},
        observed_at=now_iso,
    )
    queue.set_policy_runtime_state(
        "audit_change_last_approval_at",
        now_iso,
        metadata_update={"decision": decision, "request_id": rid},
        observed_at=now_iso,
    )
    pending_count = _update_pending_approval_runtime(queue=queue, observed_at=now_iso)
    return {
        "status": "ok",
        "action": decision,
        "request_id": rid,
        "pending_approval_count": pending_count,
    }


def enforce_pending_approval_sla(
    *,
    queue=None,
    limit: int = 100,
) -> Dict[str, Any]:
    if not _change_requests_enabled():
        return {"status": "disabled", "action": "none"}

    if queue is None:
        from orchestration.task_queue import get_queue

        queue = get_queue()

    listed = list_pending_approval_change_requests(queue=queue, limit=max(1, int(limit)))
    pending_count = int(listed.get("count", 0) or 0)
    now = datetime.now()
    now_iso = now.isoformat()
    queue.set_policy_runtime_state(
        "audit_change_last_sla_check_at",
        now_iso,
        metadata_update={"pending": pending_count},
        observed_at=now_iso,
    )
    if pending_count == 0:
        _update_pending_approval_runtime(queue=queue, observed_at=now_iso)
        return {"status": "ok", "action": "none", "pending_approval_count": 0}

    sla_hours = _approval_sla_hours()
    auto_reject = _approval_auto_reject_on_timeout()
    escalation_enabled = _approval_escalation_enabled()
    create_escalation_task = _approval_escalation_task_enabled()
    escalation_interval_min = _approval_escalation_min_interval_min()

    timed_out = 0
    auto_rejected = 0
    escalated = 0
    escalation_tasks = 0
    touched_requests: list[str] = []

    for item in listed.get("items", []):
        rid = str(item.get("id") or "")
        if not rid:
            continue
        pending_min = float(item.get("pending_minutes") or 0.0)
        if pending_min < (float(sla_hours) * 60.0):
            continue
        timed_out += 1
        touched_requests.append(rid)

        if auto_reject:
            decision = set_change_request_approval(
                queue=queue,
                request_id=rid,
                approved=False,
                approver="system_timeout",
                note=f"approval_timeout:{sla_hours}h",
            )
            if decision.get("status") == "ok":
                auto_rejected += 1
            continue

        if not escalation_enabled:
            continue

        request = queue.get_autonomy_change_request(rid)
        if not request:
            continue
        payload = request.get("payload")
        if not isinstance(payload, dict):
            payload = {}

        last_escalated = _parse_iso(str(payload.get("approval_escalated_at") or "").strip())
        if last_escalated is not None:
            elapsed_min = (now - last_escalated).total_seconds() / 60.0
            if elapsed_min < float(escalation_interval_min):
                continue

        escalation_count = int(payload.get("approval_escalation_count", 0) or 0) + 1
        payload_update: Dict[str, Any] = {
            "approval_escalated_at": now_iso,
            "approval_escalation_count": escalation_count,
            "approval_timeout_sla_hours": sla_hours,
        }

        if create_escalation_task:
            try:
                task_meta = json.dumps(
                    {
                        "source": "autonomy_change_control",
                        "type": "approval_escalation",
                        "request_id": rid,
                        "audit_id": str(request.get("audit_id") or ""),
                        "recommendation": str(request.get("recommendation") or "hold"),
                        "pending_minutes": pending_min,
                    },
                    ensure_ascii=True,
                )
                task_id = queue.add(
                    description=(
                        "Audit-ChangeRequest wartet auf Freigabe: "
                        f"{rid[:8]} ({str(request.get('recommendation') or 'hold')})"
                    ),
                    priority=1,
                    task_type="triggered",
                    target_agent="meta",
                    metadata=task_meta,
                )
                payload_update["approval_escalation_task_id"] = task_id
                escalation_tasks += 1
            except Exception:
                pass

        queue.update_autonomy_change_request(
            rid,
            status="pending_approval",
            action="awaiting_approval",
            reason=f"approval_timeout:{sla_hours}h",
            payload_update=payload_update,
        )
        queue.set_policy_runtime_state(
            "audit_change_last_escalation_request_id",
            rid,
            metadata_update={"pending_minutes": pending_min, "sla_hours": sla_hours},
            observed_at=now_iso,
        )
        queue.set_policy_runtime_state(
            "audit_change_last_escalation_at",
            now_iso,
            metadata_update={"request_id": rid, "sla_hours": sla_hours},
            observed_at=now_iso,
        )
        escalated += 1

    pending_after = _update_pending_approval_runtime(queue=queue, observed_at=now_iso)
    return {
        "status": "ok",
        "action": "sla_checked",
        "pending_approval_count": pending_after,
        "timed_out": timed_out,
        "auto_rejected": auto_rejected,
        "escalated": escalated,
        "escalation_tasks_created": escalation_tasks,
        "touched_requests": touched_requests[:20],
    }


def _apply_change_request(
    *,
    queue,
    request: Dict[str, Any],
) -> Dict[str, Any]:
    request_id = str(request.get("id") or "").strip()
    if not request_id:
        return {"status": "error", "error": "missing_request_id"}

    now = datetime.now()
    now_iso = now.isoformat()
    plan = _action_plan_for_request(queue=queue, request=request)
    recommendation = str(plan.get("recommendation") or "hold")

    min_interval = _to_int(
        os.getenv("AUTONOMY_AUDIT_CHANGE_REQUEST_MIN_INTERVAL_MIN", "30"),
        default=30,
        minimum=1,
    )
    last_applied_state = queue.get_policy_runtime_state("audit_change_last_applied_at")
    last_applied_dt = _parse_iso((last_applied_state or {}).get("state_value")) if isinstance(last_applied_state, dict) else None
    if last_applied_dt is not None:
        elapsed_min = (now - last_applied_dt).total_seconds() / 60.0
        if elapsed_min < min_interval:
            reason = f"min_interval_active:{round(min_interval - elapsed_min, 2)}min"
            queue.update_autonomy_change_request(
                request_id,
                status="skipped",
                action="none",
                reason=reason,
                payload_update={"cooldown_remaining_min": round(max(0.0, min_interval - elapsed_min), 2)},
            )
            queue.set_policy_runtime_state(
                "audit_change_last_status",
                "skipped",
                metadata_update={"reason": reason},
                observed_at=now_iso,
            )
            return {
                "status": "ok",
                "action": "skipped",
                "request_id": request_id,
                "recommendation": recommendation,
                "reason": reason,
            }

    action = str(plan.get("action") or "hold")
    reason = str(plan.get("reason") or "audit_change_request")
    current_canary = int(plan.get("current_canary", 0) or 0)
    next_canary_raw = plan.get("next_canary", current_canary)
    next_canary = int(current_canary if next_canary_raw is None else next_canary_raw)
    strict_force_off = plan.get("strict_force_off")

    if action == "rollback":
        queue.set_policy_runtime_state(
            "strict_force_off",
            "true",
            metadata_update={"reason": reason, "action": "audit_change_rollback", "request_id": request_id},
            observed_at=now_iso,
        )
        queue.set_policy_runtime_state(
            "canary_percent_override",
            "0",
            metadata_update={"reason": reason, "action": "audit_change_rollback", "request_id": request_id},
            observed_at=now_iso,
        )
    elif action == "promote_canary":
        queue.set_policy_runtime_state(
            "canary_percent_override",
            str(next_canary),
            metadata_update={
                "reason": reason,
                "action": "audit_change_promote",
                "request_id": request_id,
                "from_canary": current_canary,
                "to_canary": next_canary,
            },
            observed_at=now_iso,
        )
        queue.set_policy_runtime_state(
            "strict_force_off",
            "false",
            metadata_update={"reason": reason, "action": "audit_change_promote", "request_id": request_id},
            observed_at=now_iso,
        )

    queue.update_autonomy_change_request(
        request_id,
        status="applied",
        action=action,
        reason=reason,
        payload_update={
            "applied_at": now_iso,
            "recommendation": recommendation,
            "current_canary": current_canary,
            "next_canary": next_canary,
            "strict_force_off": strict_force_off,
            "approval_required": False,
        },
        applied_at=now_iso,
    )

    queue.set_policy_runtime_state("audit_change_last_request_id", request_id, metadata_update={"action": action}, observed_at=now_iso)
    queue.set_policy_runtime_state("audit_change_last_audit_id", str(request.get("audit_id") or ""), metadata_update={"action": action}, observed_at=now_iso)
    queue.set_policy_runtime_state("audit_change_last_action", action, metadata_update={"request_id": request_id, "reason": reason}, observed_at=now_iso)
    queue.set_policy_runtime_state("audit_change_last_status", "applied", metadata_update={"request_id": request_id}, observed_at=now_iso)
    queue.set_policy_runtime_state("audit_change_last_applied_at", now_iso, metadata_update={"request_id": request_id, "action": action}, observed_at=now_iso)
    _update_pending_approval_runtime(queue=queue, observed_at=now_iso)

    return {
        "status": "ok",
        "action": action,
        "request_id": request_id,
        "audit_id": str(request.get("audit_id") or ""),
        "recommendation": recommendation,
        "current_canary_percent": current_canary,
        "next_canary_percent": next_canary,
        "strict_force_off": strict_force_off,
        "reason": reason,
    }


def evaluate_and_apply_pending_approved_change_requests(
    *,
    queue=None,
    limit: int = 5,
) -> Dict[str, Any]:
    if not _change_requests_enabled():
        return {"status": "disabled", "action": "none"}

    if queue is None:
        from orchestration.task_queue import get_queue

        queue = get_queue()

    approved = queue.list_autonomy_change_requests(statuses=["approved"], limit=max(1, int(limit)))
    if not approved:
        _update_pending_approval_runtime(queue=queue)
        return {"status": "ok", "action": "none", "processed": 0}

    results: list[Dict[str, Any]] = []
    for request in list(reversed(approved)):
        results.append(_apply_change_request(queue=queue, request=request))
    _update_pending_approval_runtime(queue=queue)
    return {
        "status": "ok",
        "action": "applied_approved_requests",
        "processed": len(results),
        "results": results,
    }


def evaluate_and_apply_audit_change_request(
    *,
    queue=None,
    report: Optional[Dict[str, Any]] = None,
    report_path: Optional[str] = None,
) -> Dict[str, Any]:
    if not _change_requests_enabled():
        return {"status": "disabled", "action": "none"}

    if queue is None:
        from orchestration.task_queue import get_queue

        queue = get_queue()

    created = create_change_request_from_audit(queue=queue, report=report, report_path=report_path)
    if created.get("status") != "ok":
        return created

    request = queue.get_autonomy_change_request(str(created.get("id") or ""))
    if not request:
        return {"status": "error", "error": "request_missing_after_create"}

    request_id = str(request.get("id") or "")
    current_status = str(request.get("status") or "proposed").strip().lower()

    if current_status in {"applied", "skipped", "rejected", "error"}:
        _update_pending_approval_runtime(queue=queue)
        return {
            "status": "ok",
            "action": "duplicate_noop",
            "request_id": request_id,
            "audit_id": str(request.get("audit_id") or ""),
            "request_status": current_status,
            "recommendation": str(request.get("recommendation") or "hold"),
        }

    if current_status == "pending_approval":
        _update_pending_approval_runtime(queue=queue)
        if _approval_auto_approve():
            approval = set_change_request_approval(
                queue=queue,
                request_id=request_id,
                approved=True,
                approver=_approval_auto_approver(),
                note="auto_approve_enabled",
            )
            if approval.get("status") == "ok":
                request = queue.get_autonomy_change_request(request_id) or request
                return _apply_change_request(queue=queue, request=request)
        return {
            "status": "ok",
            "action": "awaiting_approval",
            "request_id": request_id,
            "audit_id": str(request.get("audit_id") or ""),
            "recommendation": str(request.get("recommendation") or "hold"),
            "request_status": "pending_approval",
        }

    if current_status == "approved":
        return _apply_change_request(queue=queue, request=request)

    plan = _action_plan_for_request(queue=queue, request=request)
    approval_need = _approval_requirement(plan)
    if bool(approval_need.get("required", False)):
        if _approval_auto_approve():
            approval = set_change_request_approval(
                queue=queue,
                request_id=request_id,
                approved=True,
                approver=_approval_auto_approver(),
                note=str(approval_need.get("reason") or "auto_approve"),
            )
            if approval.get("status") == "ok":
                request = queue.get_autonomy_change_request(request_id) or request
                return _apply_change_request(queue=queue, request=request)

        now_iso = datetime.now().isoformat()
        queue.update_autonomy_change_request(
            request_id,
            status="pending_approval",
            action="awaiting_approval",
            reason=str(approval_need.get("reason") or "approval_required"),
            payload_update={
                "approval_required": True,
                "approval_reason": str(approval_need.get("reason") or "approval_required"),
                "approval_required_actions": sorted(_approval_required_actions()),
                "proposed_plan": plan,
                "pending_since": now_iso,
            },
        )
        queue.set_policy_runtime_state("audit_change_last_request_id", request_id, metadata_update={"action": "awaiting_approval"}, observed_at=now_iso)
        queue.set_policy_runtime_state("audit_change_last_action", "awaiting_approval", metadata_update={"request_id": request_id}, observed_at=now_iso)
        queue.set_policy_runtime_state("audit_change_last_status", "pending_approval", metadata_update={"request_id": request_id}, observed_at=now_iso)
        pending_count = _update_pending_approval_runtime(queue=queue, observed_at=now_iso)
        return {
            "status": "ok",
            "action": "awaiting_approval",
            "request_id": request_id,
            "audit_id": str(request.get("audit_id") or ""),
            "recommendation": str(request.get("recommendation") or "hold"),
            "approval_reason": str(approval_need.get("reason") or "approval_required"),
            "pending_approval_count": pending_count,
        }

    return _apply_change_request(queue=queue, request=request)
