"""Phase E E3.2: controlled hardening-task creation from E3 bridge decisions."""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta
from typing import Any, Iterable, Mapping


_READY_BRIDGE_STATES = {"developer_bridge_ready", "self_modify_ready"}


def _text(value: Any, *, limit: int = 240) -> str:
    text = str(value or "").strip()
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "..."


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)).strip())
    except Exception:
        return default


def _parse_iso(value: Any) -> datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw)
        if parsed.tzinfo is not None:
            return parsed.astimezone().replace(tzinfo=None)
        return parsed
    except Exception:
        return None


def get_improvement_task_enqueue_cooldown_minutes() -> int:
    return max(0, _env_int("AUTONOMY_IMPROVEMENT_AUTOENQUEUE_COOLDOWN_MINUTES", 180))


def _priority_for_task(task: Mapping[str, Any]) -> int:
    try:
        score = float(task.get("priority_score") or 0.0)
    except Exception:
        score = 0.0
    if score >= 2.0:
        return 1
    if score >= 1.0:
        return 2
    return 3


def _dedup_key(task: Mapping[str, Any], bridge: Mapping[str, Any]) -> str:
    candidate_id = _text(task.get("candidate_id"), limit=80) or "unknown"
    target_file = _text(bridge.get("target_file_path"), limit=200) or _text(task.get("category"), limit=64) or "runtime"
    fix_mode = _text(bridge.get("effective_fix_mode"), limit=64) or "observe_only"
    return f"improvement_hardening:{candidate_id}:{target_file}:{fix_mode}"


def _description(task: Mapping[str, Any], bridge: Mapping[str, Any]) -> str:
    title = _text(task.get("title"), limit=120) or _text(task.get("category"), limit=64) or "runtime"
    problem = _text(task.get("problem"), limit=280)
    action = _text(task.get("proposed_action"), limit=280)
    root_cause = _text(task.get("likely_root_cause"), limit=120)
    bridge_state = _text(bridge.get("bridge_state"), limit=64)
    route_target = _text(bridge.get("route_target"), limit=64)
    lines = [
        f"[PHASE E E3.2] Improvement Hardening Task fuer {title}.",
        f"Problem: {problem or 'n/a'}",
        f"Proposed Action: {action or 'n/a'}",
        f"Likely Root Cause: {root_cause or 'n/a'}",
        f"Bridge State: {bridge_state or 'n/a'} -> Route: {route_target or 'n/a'}",
    ]
    return "\n".join(lines)


def build_improvement_hardening_task_metadata(
    task: Mapping[str, Any],
    promotion: Mapping[str, Any],
    bridge: Mapping[str, Any],
    *,
    goal_id: str | None = None,
) -> dict[str, Any]:
    evidence = task.get("evidence")
    evidence = evidence if isinstance(evidence, Mapping) else {}
    return {
        "source": "improvement_task_bridge",
        "pattern_name": _text(task.get("candidate_id"), limit=80),
        "component": _text(task.get("category"), limit=64),
        "candidate_id": _text(task.get("candidate_id"), limit=80),
        "compiled_task_id": _text(task.get("task_id"), limit=80),
        "title": _text(task.get("title"), limit=120),
        "category": _text(task.get("category"), limit=64),
        "task_kind": _text(task.get("task_kind"), limit=64),
        "problem": _text(task.get("problem"), limit=280),
        "proposed_action": _text(task.get("proposed_action"), limit=280),
        "likely_root_cause": _text(task.get("likely_root_cause"), limit=120),
        "safe_fix_class": _text(task.get("safe_fix_class"), limit=96),
        "requested_fix_mode": _text(promotion.get("requested_fix_mode"), limit=64),
        "execution_mode": _text(bridge.get("effective_fix_mode"), limit=64),
        "effective_fix_mode": _text(bridge.get("effective_fix_mode"), limit=64),
        "promotion_state": _text(promotion.get("promotion_state"), limit=64),
        "bridge_state": _text(bridge.get("bridge_state"), limit=64),
        "route_target": _text(bridge.get("route_target"), limit=64),
        "target_file_path": _text(bridge.get("target_file_path"), limit=200),
        "change_type": _text(bridge.get("change_type"), limit=96),
        "rollout_stage": _text(promotion.get("rollout_stage"), limit=64),
        "rollout_reason": _text(bridge.get("reason"), limit=120),
        "goal_id": _text(goal_id, limit=80),
        "required_checks": list(bridge.get("required_checks") or []),
        "required_test_targets": list(bridge.get("required_test_targets") or []),
        "verified_paths": list(evidence.get("verified_paths") or []),
        "verified_functions": list(evidence.get("verified_functions") or []),
        "event_types": list(evidence.get("event_types") or []),
        "components": list(evidence.get("components") or []),
        "signals": list(evidence.get("signals") or []),
        "improvement_dedup_key": _dedup_key(task, bridge),
    }


def build_improvement_hardening_task_payload(
    task: Mapping[str, Any],
    promotion: Mapping[str, Any],
    bridge: Mapping[str, Any],
    *,
    goal_id: str | None = None,
) -> dict[str, Any]:
    bridge_state = _text(bridge.get("bridge_state"), limit=64)
    allow_task = bool(bridge.get("allow_task"))
    route_target = _text(bridge.get("route_target"), limit=64)
    ready = allow_task and bridge_state in _READY_BRIDGE_STATES and bool(route_target)
    metadata = build_improvement_hardening_task_metadata(task, promotion, bridge, goal_id=goal_id)
    return {
        "candidate_id": _text(task.get("candidate_id"), limit=80),
        "compiled_task_id": _text(task.get("task_id"), limit=80),
        "creation_state": "task_payload_ready" if ready else "not_creatable",
        "bridge_state": bridge_state,
        "description": _description(task, bridge),
        "priority": _priority_for_task(task),
        "task_type": "triggered",
        "target_agent": route_target if ready else "",
        "goal_id": _text(goal_id, limit=80),
        "metadata": metadata,
    }


def build_improvement_hardening_task_payloads(
    tasks: Iterable[Mapping[str, Any]],
    promotions: Iterable[Mapping[str, Any]],
    bridges: Iterable[Mapping[str, Any]],
    *,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    promotions_by_task = {_text(item.get("task_id"), limit=80): item for item in promotions}
    bridges_by_task = {_text(item.get("task_id"), limit=80): item for item in bridges}
    payloads: list[dict[str, Any]] = []
    for task in tasks:
        task_id = _text(task.get("task_id"), limit=80)
        promotion = promotions_by_task.get(task_id)
        bridge = bridges_by_task.get(task_id)
        if not promotion or not bridge:
            continue
        payloads.append(build_improvement_hardening_task_payload(task, promotion, bridge))
    if limit is None:
        return payloads
    return payloads[: max(0, int(limit))]


def _has_open_improvement_task(queue: Any, dedup_key: str) -> bool:
    if not dedup_key:
        return False
    for task in queue.get_all(limit=200):
        status = _text(task.get("status"), limit=32).lower()
        if status not in {"pending", "in_progress"}:
            continue
        raw_metadata = task.get("metadata")
        try:
            metadata = json.loads(raw_metadata) if isinstance(raw_metadata, str) else (raw_metadata or {})
        except Exception:
            metadata = {}
        if _text(metadata.get("improvement_dedup_key"), limit=240) == dedup_key:
            return True
    return False


def _find_recent_terminal_improvement_task(
    queue: Any,
    dedup_key: str,
    *,
    cooldown_minutes: int,
) -> dict[str, str]:
    if not dedup_key or cooldown_minutes <= 0:
        return {}

    now = datetime.now()
    cooldown_window = timedelta(minutes=max(0, int(cooldown_minutes)))
    for task in queue.get_all(limit=400):
        status = _text(task.get("status"), limit=32).lower()
        if status in {"pending", "in_progress"}:
            continue
        raw_metadata = task.get("metadata")
        try:
            metadata = json.loads(raw_metadata) if isinstance(raw_metadata, str) else (raw_metadata or {})
        except Exception:
            metadata = {}
        if _text(metadata.get("improvement_dedup_key"), limit=240) != dedup_key:
            continue
        reference_dt = _parse_iso(task.get("completed_at")) or _parse_iso(task.get("created_at"))
        if reference_dt is None:
            continue
        if now < (reference_dt + cooldown_window):
            return {
                "status": status,
                "task_id": _text(task.get("id"), limit=80),
                "completed_at": _text(task.get("completed_at"), limit=80),
            }
    return {}


def enqueue_improvement_hardening_task(
    queue: Any,
    task: Mapping[str, Any],
    promotion: Mapping[str, Any],
    bridge: Mapping[str, Any],
    *,
    goal_id: str | None = None,
) -> dict[str, Any]:
    payload = build_improvement_hardening_task_payload(task, promotion, bridge, goal_id=goal_id)
    metadata = payload.get("metadata")
    metadata = metadata if isinstance(metadata, Mapping) else {}
    dedup_key = _text(metadata.get("improvement_dedup_key"), limit=240)

    if _text(payload.get("creation_state"), limit=64) != "task_payload_ready":
        return {
            "status": "not_created",
            "reason": f"creation_state:{_text(payload.get('creation_state'), limit=64)}",
            "task_id": "",
            "target_agent": "",
        }

    if _has_open_improvement_task(queue, dedup_key):
        return {
            "status": "deduped",
            "reason": "open_task_exists",
            "task_id": "",
            "target_agent": _text(payload.get("target_agent"), limit=64),
        }

    cooldown_minutes = get_improvement_task_enqueue_cooldown_minutes()
    recent_terminal = _find_recent_terminal_improvement_task(
        queue,
        dedup_key,
        cooldown_minutes=cooldown_minutes,
    )
    if recent_terminal:
        return {
            "status": "cooldown_active",
            "reason": f"recent_{_text(recent_terminal.get('status'), limit=32) or 'terminal'}_task_within_cooldown",
            "task_id": _text(recent_terminal.get("task_id"), limit=80),
            "target_agent": _text(payload.get("target_agent"), limit=64),
            "cooldown_minutes": int(cooldown_minutes),
        }

    from orchestration.task_queue import TaskType

    task_id = queue.add(
        description=_text(payload.get("description"), limit=4000),
        priority=int(payload.get("priority") or 2),
        task_type=TaskType.TRIGGERED,
        target_agent=_text(payload.get("target_agent"), limit=64),
        goal_id=_text(payload.get("goal_id"), limit=80) or None,
        metadata=json.dumps(metadata, ensure_ascii=True),
    )
    return {
        "status": "created",
        "reason": "task_created",
        "task_id": _text(task_id, limit=80),
        "target_agent": _text(payload.get("target_agent"), limit=64),
    }
