"""
orchestration/replanning_engine.py

M2.2 Re-Planning:
- Trigger-Erkennung fuer Commitments (Timeout, Partial-Stall, Drift, Konflikt)
- Automatische Replan-Events und Recovery-Commitments
"""

from __future__ import annotations

import hashlib
import logging
import os
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

from orchestration.task_queue import (
    CommitmentStatus,
    GoalStatus,
    PlanHorizon,
    ReplanEventStatus,
    ReplanTrigger,
    TaskQueue,
    get_queue,
)

log = logging.getLogger("ReplanningEngine")


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name, "true" if default else "false").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)).strip())
    except Exception:
        return default


def _replanning_feature_enabled() -> bool:
    if _env_bool("AUTONOMY_COMPAT_MODE", True):
        return False
    return _env_bool("AUTONOMY_REPLANNING_ENABLED", False)


def _parse_iso(value: str | None) -> Optional[datetime]:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
        if parsed.tzinfo is not None:
            return parsed.astimezone().replace(tzinfo=None)
        return parsed
    except Exception:
        return None


class ReplanningEngine:
    """Erkennt Replanning-Trigger und fuehrt additive Recovery-Aktionen aus."""

    def __init__(
        self,
        queue: TaskQueue | None = None,
        now_provider: Callable[[], datetime] | None = None,
    ):
        self.queue = queue or get_queue()
        self._now = now_provider or datetime.now

    def run_cycle(self) -> Dict[str, Any]:
        if not _replanning_feature_enabled():
            return {
                "status": "disabled",
                "commitments_scanned": 0,
                "priority_candidates": 0,
                "top_priority_score": 0.0,
                "events_detected": 0,
                "events_created": 0,
                "duplicates_skipped": 0,
                "actions_applied": 0,
                "actions_failed": 0,
            }

        candidates = self.queue.list_replanning_candidates(
            limit=max(20, _env_int("AUTONOMY_REPLAN_MAX_COMMITMENTS_PER_CYCLE", 240)),
            include_blocked=True,
        )
        if not candidates:
            return {
                "status": "no_commitments",
                "commitments_scanned": 0,
                "priority_candidates": 0,
                "top_priority_score": 0.0,
                "events_detected": 0,
                "events_created": 0,
                "duplicates_skipped": 0,
                "actions_applied": 0,
                "actions_failed": 0,
            }

        now = self._now()
        conflicts = self.queue.detect_goal_conflicts(limit=80)
        conflict_goal_ids: Set[str] = set()
        for conflict in conflicts:
            aid = str(conflict.get("goal_a_id") or "")
            bid = str(conflict.get("goal_b_id") or "")
            if aid:
                conflict_goal_ids.add(aid)
            if bid:
                conflict_goal_ids.add(bid)

        summary: Dict[str, Any] = {
            "status": "ok",
            "commitments_scanned": len(candidates),
            "priority_candidates": sum(1 for c in candidates if float(c.get("priority_score") or 0.0) >= 3.0),
            "top_priority_score": float(candidates[0].get("priority_score") or 0.0),
            "events_detected": 0,
            "events_created": 0,
            "duplicates_skipped": 0,
            "actions_applied": 0,
            "actions_failed": 0,
            "trigger_counts": {},
        }

        goal_status_cache: Dict[str, str] = {}
        for commitment in candidates:
            triggers = self._detect_triggers(
                commitment=commitment,
                now=now,
                conflict_goal_ids=conflict_goal_ids,
                goal_status_cache=goal_status_cache,
            )
            for trigger, severity, details in triggers:
                summary["events_detected"] += 1
                summary["trigger_counts"][trigger] = summary["trigger_counts"].get(trigger, 0) + 1

                event_key = self._event_key(commitment, trigger, details, now)
                event = self.queue.log_replan_event(
                    event_key=event_key,
                    commitment_id=str(commitment.get("id", "")),
                    goal_id=(str(commitment.get("goal_id")) if commitment.get("goal_id") else None),
                    trigger_type=trigger,
                    severity=severity,
                    status=ReplanEventStatus.DETECTED,
                    details=details,
                )

                if not event.get("created"):
                    summary["duplicates_skipped"] += 1
                    continue
                summary["events_created"] += 1

                action = self._apply_action(
                    commitment=commitment,
                    trigger=trigger,
                    details=details,
                    now=now,
                    event_id=int(event["id"]),
                    event_key=event_key,
                )
                if action.get("ok"):
                    summary["actions_applied"] += 1
                    self.queue.update_replan_event_status(
                        int(event["id"]),
                        ReplanEventStatus.APPLIED,
                        action=str(action.get("action") or ""),
                        details_update=dict(action.get("details") or {}),
                    )
                else:
                    summary["actions_failed"] += 1
                    self.queue.update_replan_event_status(
                        int(event["id"]),
                        ReplanEventStatus.FAILED,
                        action=str(action.get("action") or "replan_failed"),
                        details_update={"error": str(action.get("error") or "unknown")},
                    )

        if summary["events_detected"] > 0:
            log.info(
                "🔁 Replanning: detected=%s created=%s applied=%s failed=%s dup=%s top_prio=%.2f",
                summary["events_detected"],
                summary["events_created"],
                summary["actions_applied"],
                summary["actions_failed"],
                summary["duplicates_skipped"],
                float(summary.get("top_priority_score", 0.0)),
            )
        return summary

    def _detect_triggers(
        self,
        *,
        commitment: dict,
        now: datetime,
        conflict_goal_ids: Set[str],
        goal_status_cache: Dict[str, str],
    ) -> List[Tuple[str, str, Dict[str, Any]]]:
        triggers: List[Tuple[str, str, Dict[str, Any]]] = []
        status = str(commitment.get("status") or "")
        progress = float(commitment.get("progress") or 0.0)
        deadline_raw = str(commitment.get("deadline") or "")
        updated_raw = str(commitment.get("updated_at") or "")
        goal_id = str(commitment.get("goal_id") or "")
        deadline_dt = _parse_iso(deadline_raw)
        updated_dt = _parse_iso(updated_raw)

        if deadline_dt and deadline_dt < now and status in {
            CommitmentStatus.PENDING,
            CommitmentStatus.IN_PROGRESS,
            CommitmentStatus.BLOCKED,
        }:
            overdue_minutes = int((now - deadline_dt).total_seconds() // 60)
            triggers.append(
                (
                    ReplanTrigger.DEADLINE_TIMEOUT,
                    "high",
                    {
                        "reason": "deadline_passed",
                        "deadline": deadline_raw,
                        "overdue_minutes": max(0, overdue_minutes),
                    },
                )
            )

        partial_hours = max(1, _env_int("AUTONOMY_REPLAN_PARTIAL_STALL_HOURS", 24))
        partial_threshold = now - timedelta(hours=partial_hours)
        if (
            updated_dt
            and updated_dt < partial_threshold
            and status in {CommitmentStatus.PENDING, CommitmentStatus.IN_PROGRESS}
            and progress > 0.0
            and progress < 100.0
        ):
            triggers.append(
                (
                    ReplanTrigger.PARTIAL_STAGNATION,
                    "medium",
                    {
                        "reason": "partial_stall",
                        "progress": progress,
                        "last_update": updated_raw,
                        "stall_hours": partial_hours,
                    },
                )
            )

        drift_hours = max(1, _env_int("AUTONOMY_REPLAN_DRIFT_HOURS", 48))
        drift_threshold = now - timedelta(hours=drift_hours)
        if (
            updated_dt
            and updated_dt < drift_threshold
            and status in {CommitmentStatus.PENDING, CommitmentStatus.IN_PROGRESS}
            and progress <= 0.0
        ):
            triggers.append(
                (
                    ReplanTrigger.GOAL_DRIFT,
                    "medium",
                    {
                        "reason": "no_progress_drift",
                        "last_update": updated_raw,
                        "drift_hours": drift_hours,
                    },
                )
            )

        if goal_id:
            conflict_reason: Optional[str] = None
            if goal_id in conflict_goal_ids:
                conflict_reason = "goal_conflict_detected"
            else:
                if goal_id not in goal_status_cache:
                    goal = self.queue.get_goal(goal_id)
                    goal_status_cache[goal_id] = str(goal.get("status") if goal else "")
                if goal_status_cache.get(goal_id) == GoalStatus.BLOCKED:
                    conflict_reason = "goal_blocked"

            if conflict_reason:
                triggers.append(
                    (
                        ReplanTrigger.GOAL_CONFLICT,
                        "high",
                        {"reason": conflict_reason, "goal_id": goal_id},
                    )
                )

        return triggers

    def _event_key(self, commitment: dict, trigger: str, details: Dict[str, Any], now: datetime) -> str:
        commitment_id = str(commitment.get("id", ""))
        bucket = now.strftime("%Y-%m-%d")
        base = "|".join(
            [
                commitment_id,
                trigger,
                bucket,
                str(commitment.get("goal_id") or ""),
                str(commitment.get("deadline") or ""),
                str(details.get("reason") or ""),
            ]
        )
        digest = hashlib.sha1(base.encode("utf-8")).hexdigest()[:16]
        return f"{commitment_id}:{trigger}:{bucket}:{digest}"

    def _apply_action(
        self,
        *,
        commitment: dict,
        trigger: str,
        details: Dict[str, Any],
        now: datetime,
        event_id: int,
        event_key: str,
    ) -> Dict[str, Any]:
        commitment_id = str(commitment.get("id", ""))
        if not commitment_id:
            return {"ok": False, "action": "invalid_commitment", "error": "missing commitment id"}

        metadata_update = {
            "replan_last_trigger": trigger,
            "replan_last_event_id": event_id,
            "replan_last_event_key": event_key,
            "replan_last_at": now.isoformat(),
        }
        metadata_update.update(details)

        actions: List[str] = []

        if trigger in {ReplanTrigger.DEADLINE_TIMEOUT, ReplanTrigger.GOAL_DRIFT, ReplanTrigger.GOAL_CONFLICT}:
            ok = self.queue.update_commitment_status(
                commitment_id,
                CommitmentStatus.BLOCKED,
                metadata_update=metadata_update,
            )
            if not ok:
                return {"ok": False, "action": "block_commitment", "error": "commitment not found"}
            actions.append("commitment_blocked")
        elif trigger == ReplanTrigger.PARTIAL_STAGNATION:
            ok = self.queue.update_commitment_status(
                commitment_id,
                CommitmentStatus.IN_PROGRESS,
                metadata_update=metadata_update,
            )
            if not ok:
                return {"ok": False, "action": "nudge_commitment", "error": "commitment not found"}
            actions.append("commitment_nudged")

        recovery_id: Optional[str] = None
        if trigger in {
            ReplanTrigger.DEADLINE_TIMEOUT,
            ReplanTrigger.PARTIAL_STAGNATION,
            ReplanTrigger.GOAL_DRIFT,
        }:
            recovery_id = self._create_recovery_commitment(
                commitment=commitment,
                trigger=trigger,
                event_id=event_id,
                event_key=event_key,
                now=now,
            )
            if recovery_id:
                actions.append(f"recovery:{recovery_id[:8]}")
            else:
                actions.append("recovery:skipped")

        return {
            "ok": True,
            "action": "+".join(actions),
            "details": {"recovery_commitment_id": recovery_id} if recovery_id else {},
        }

    def _create_recovery_commitment(
        self,
        *,
        commitment: dict,
        trigger: str,
        event_id: int,
        event_key: str,
        now: datetime,
    ) -> Optional[str]:
        plan_id = str(commitment.get("plan_id") or "")
        title = str(commitment.get("title") or "").strip()
        owner = str(commitment.get("owner_agent") or "meta").strip() or "meta"
        goal_id = str(commitment.get("goal_id") or "") or None
        success_metric = str(commitment.get("success_metric") or "delivery_done").strip() or "delivery_done"
        if not plan_id or not title:
            return None

        horizon = PlanHorizon.DAILY
        plan = self.queue.get_plan(plan_id)
        if plan and plan.get("horizon"):
            horizon = str(plan.get("horizon"))

        original_deadline = _parse_iso(str(commitment.get("deadline") or ""))
        new_deadline = self._next_recovery_deadline(
            trigger=trigger,
            horizon=horizon,
            base_deadline=original_deadline,
            now=now,
        )
        recovery_title = f"Recovery [{trigger}]: {title}"
        if len(recovery_title) > 160:
            recovery_title = recovery_title[:157].rstrip() + "..."

        metadata = {
            "is_recovery": True,
            "recovery_for": str(commitment.get("id") or ""),
            "replan_trigger": trigger,
            "replan_event_id": event_id,
            "replan_event_key": event_key,
            "generated_at": now.isoformat(),
        }
        try:
            return self.queue.create_commitment(
                plan_id=plan_id,
                goal_id=goal_id,
                title=recovery_title,
                owner_agent=owner,
                deadline=new_deadline.isoformat(),
                success_metric=f"recovery: {success_metric}",
                status=CommitmentStatus.PENDING,
                progress=0.0,
                metadata=metadata,
            )
        except Exception:
            return None

    def _next_recovery_deadline(
        self,
        *,
        trigger: str,
        horizon: str,
        base_deadline: Optional[datetime],
        now: datetime,
    ) -> datetime:
        if trigger == ReplanTrigger.PARTIAL_STAGNATION:
            if horizon == PlanHorizon.DAILY:
                delta = timedelta(hours=6)
            elif horizon == PlanHorizon.WEEKLY:
                delta = timedelta(days=1)
            else:
                delta = timedelta(days=2)
        elif trigger == ReplanTrigger.DEADLINE_TIMEOUT:
            if horizon == PlanHorizon.DAILY:
                delta = timedelta(hours=12)
            elif horizon == PlanHorizon.WEEKLY:
                delta = timedelta(days=2)
            else:
                delta = timedelta(days=5)
        else:
            if horizon == PlanHorizon.DAILY:
                delta = timedelta(days=1)
            elif horizon == PlanHorizon.WEEKLY:
                delta = timedelta(days=3)
            else:
                delta = timedelta(days=7)

        anchor = base_deadline or now
        candidate = anchor + delta
        if candidate <= now:
            candidate = now + delta
        return candidate
