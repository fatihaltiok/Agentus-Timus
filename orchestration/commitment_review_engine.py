"""
orchestration/commitment_review_engine.py

M2.4 Commitment Review Cycle:
- Checkpoint-Sync fuer offene Commitments
- Review-Auswertung mit Erwartung/Ist-Gap
- Eskalation in Replanning-Events bei hohem Risiko
"""

from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Any, Callable, Dict, Optional

from orchestration.task_queue import (
    CommitmentReviewStatus,
    CommitmentStatus,
    ReplanEventStatus,
    ReplanTrigger,
    TaskQueue,
    get_queue,
)

log = logging.getLogger("CommitmentReviewEngine")


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name, "true" if default else "false").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)).strip())
    except Exception:
        return default


def _planning_feature_enabled() -> bool:
    if _env_bool("AUTONOMY_COMPAT_MODE", True):
        return False
    return _env_bool("AUTONOMY_PLANNING_ENABLED", False)


def _replanning_feature_enabled() -> bool:
    if _env_bool("AUTONOMY_COMPAT_MODE", True):
        return False
    return _env_bool("AUTONOMY_REPLANNING_ENABLED", False)


class CommitmentReviewEngine:
    """Fuehrt Commitment-Review-Zyklen mit Eskalation auf Replan-Events aus."""

    def __init__(
        self,
        queue: TaskQueue | None = None,
        now_provider: Callable[[], datetime] | None = None,
    ):
        self.queue = queue or get_queue()
        self._now = now_provider or datetime.now

    def run_cycle(self) -> Dict[str, Any]:
        if not _planning_feature_enabled():
            return {
                "status": "disabled",
                "reviews_synced": 0,
                "reviews_due": 0,
                "reviews_completed": 0,
                "reviews_escalated": 0,
                "replan_events_created": 0,
                "avg_gap": 0.0,
            }

        sync_summary = self.queue.sync_commitment_review_checkpoints(
            limit=max(40, _env_int("AUTONOMY_REVIEW_MAX_COMMITMENTS_PER_CYCLE", 240))
        )
        due_reviews = self.queue.list_commitment_reviews(
            statuses=[CommitmentReviewStatus.SCHEDULED],
            due_only=True,
            limit=max(20, _env_int("AUTONOMY_REVIEW_MAX_DUE_PER_CYCLE", 120)),
        )

        summary: Dict[str, Any] = {
            "status": "ok",
            "reviews_synced": int(sync_summary.get("reviews_created", 0)) + int(sync_summary.get("reviews_updated", 0)),
            "reviews_due": len(due_reviews),
            "reviews_completed": 0,
            "reviews_escalated": 0,
            "replan_events_created": 0,
            "avg_gap": 0.0,
        }
        if not due_reviews:
            return summary

        now = self._now()
        gap_sum = 0.0
        gap_n = 0

        for review in due_reviews:
            review_id = int(review.get("id") or 0)
            commitment_id = str(review.get("commitment_id") or "")
            if not review_id or not commitment_id:
                continue

            commitment = self.queue.get_commitment(commitment_id)
            if not commitment:
                ok = self.queue.update_commitment_review(
                    review_id,
                    status=CommitmentReviewStatus.SKIPPED,
                    risk_level="low",
                    notes="commitment_missing",
                    reviewed_at=now.isoformat(),
                    metadata_update={"reason": "commitment_not_found"},
                )
                if ok:
                    summary["reviews_completed"] += 1
                continue

            expected = review.get("expected_progress")
            expected_progress = float(expected) if expected is not None else 0.0
            observed_progress = float(commitment.get("progress") or 0.0)
            gap = round(expected_progress - observed_progress, 2)
            gap_sum += gap
            gap_n += 1

            risk_level = self._risk_level(gap, commitment)
            escalate = risk_level in {"high", "critical"}
            target_status = CommitmentReviewStatus.ESCALATED if escalate else CommitmentReviewStatus.COMPLETED
            note = f"gap={gap:.2f}, expected={expected_progress:.2f}, observed={observed_progress:.2f}"

            ok = self.queue.update_commitment_review(
                review_id,
                status=target_status,
                expected_progress=expected_progress,
                observed_progress=observed_progress,
                progress_gap=gap,
                risk_level=risk_level,
                notes=note,
                reviewed_at=now.isoformat(),
                metadata_update={"engine": "commitment_review_engine"},
            )
            if not ok:
                continue

            summary["reviews_completed"] += 1
            if escalate:
                summary["reviews_escalated"] += 1
                if _replanning_feature_enabled():
                    created = self._emit_replan_event(
                        commitment=commitment,
                        review=review,
                        risk_level=risk_level,
                        gap=gap,
                        now=now,
                    )
                    if created:
                        summary["replan_events_created"] += 1

        if gap_n > 0:
            summary["avg_gap"] = round(gap_sum / gap_n, 2)

        if summary["reviews_due"] > 0:
            log.info(
                "📋 CommitmentReview: due=%s completed=%s escalated=%s replan_events=%s avg_gap=%.2f",
                summary["reviews_due"],
                summary["reviews_completed"],
                summary["reviews_escalated"],
                summary["replan_events_created"],
                float(summary["avg_gap"]),
            )

        return summary

    def _risk_level(self, gap: float, commitment: dict) -> str:
        # Invariante: gibt immer low|medium|high|critical zurück.
        # CrossHair kann arbitrary-dict Parameter nicht symbolisch ausführen;
        # die Invariante ist durch Hypothesis test_risk_level_valid (Th.61) abgedeckt.
        status = str(commitment.get("status") or "")
        if status == CommitmentStatus.BLOCKED:
            return "high"
        if gap >= 35.0:
            return "critical"
        if gap >= 20.0:
            return "high"
        if gap >= 10.0:
            return "medium"
        return "low"

    def _emit_replan_event(
        self,
        *,
        commitment: dict,
        review: dict,
        risk_level: str,
        gap: float,
        now: datetime,
    ) -> bool:
        commitment_id = str(commitment.get("id") or "")
        if not commitment_id:
            return False
        trigger = ReplanTrigger.PARTIAL_STAGNATION
        progress = float(commitment.get("progress") or 0.0)
        deadline = str(commitment.get("deadline") or "")
        if progress <= 0.0:
            trigger = ReplanTrigger.GOAL_DRIFT
        due_dt = review.get("review_due_at")
        event_key = (
            f"review:{review.get('id')}:{trigger}:{now.strftime('%Y-%m-%d')}:{int(round(gap * 10))}"
        )
        event = self.queue.log_replan_event(
            event_key=event_key,
            commitment_id=commitment_id,
            goal_id=(str(commitment.get("goal_id")) if commitment.get("goal_id") else None),
            trigger_type=trigger,
            severity=("high" if risk_level == "critical" else risk_level),
            status=ReplanEventStatus.DETECTED,
            details={
                "source": "commitment_review_engine",
                "review_id": int(review.get("id") or 0),
                "review_due_at": str(due_dt or ""),
                "gap": gap,
                "risk_level": risk_level,
                "deadline": deadline,
            },
        )
        return bool(event.get("created"))
