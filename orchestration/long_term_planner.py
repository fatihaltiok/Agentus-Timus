"""
orchestration/long_term_planner.py

M2.1 Langzeitplanung:
- Rolling Plans fuer Daily / Weekly / Monthly
- Commitments mit Deadline, Owner-Agent und Erfolgsmetriken
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, List, Tuple

from orchestration.task_queue import GoalStatus, PlanHorizon, TaskQueue, get_queue

log = logging.getLogger("LongTermPlanner")


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name, "true" if default else "false").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def _planning_feature_enabled() -> bool:
    if _env_bool("AUTONOMY_COMPAT_MODE", True):
        return False
    return _env_bool("AUTONOMY_PLANNING_ENABLED", False)


class LongTermPlanner:
    """Erstellt Rolling-Plans und Commitments aus aktiven Zielen."""

    def __init__(
        self,
        queue: TaskQueue | None = None,
        now_provider: Callable[[], datetime] | None = None,
    ):
        self.queue = queue or get_queue()
        self._now = now_provider or datetime.now

    def run_cycle(self) -> Dict[str, Any]:
        if not _planning_feature_enabled():
            return {"status": "disabled", "plans_touched": 0, "commitments_touched": 0}

        goals = self.queue.list_goals(status=GoalStatus.ACTIVE, limit=80)
        blocked = self.queue.list_goals(status=GoalStatus.BLOCKED, limit=20)
        merged = goals + blocked
        if not merged:
            return {"status": "no_goals", "plans_touched": 0, "commitments_touched": 0}

        windows = self._build_windows(self._now())
        summary = {
            "status": "ok",
            "plans_touched": 0,
            "plan_items_touched": 0,
            "commitments_touched": 0,
            "horizons": {},
        }

        for horizon, (start_iso, end_iso) in windows.items():
            plan_id = self.queue.create_or_get_plan(
                horizon=horizon,
                window_start=start_iso,
                window_end=end_iso,
                source="long_term_planner",
                metadata={"generated_at": self._now().isoformat()},
            )
            selected = self._select_goals_for_horizon(horizon, merged)
            item_count = 0
            commitment_count = 0

            for goal in selected:
                goal_id = str(goal.get("id", ""))
                title = str(goal.get("title", "")).strip()
                if not goal_id or not title:
                    continue
                owner = self.queue.infer_goal_owner_agent(goal_id, default="meta")
                item_id = self.queue.add_plan_item(
                    plan_id=plan_id,
                    goal_id=goal_id,
                    title=title,
                    owner_agent=owner,
                    deadline=end_iso,
                    success_metric=self._success_metric_for_horizon(horizon),
                    priority_score=float(goal.get("priority_score") or 0.0),
                )
                if item_id:
                    item_count += 1

                cid = self.queue.create_commitment(
                    plan_id=plan_id,
                    goal_id=goal_id,
                    title=title,
                    owner_agent=owner,
                    deadline=end_iso,
                    success_metric=self._success_metric_for_horizon(horizon),
                    metadata={"horizon": horizon},
                )
                if cid:
                    commitment_count += 1

            summary["plans_touched"] += 1
            summary["plan_items_touched"] += item_count
            summary["commitments_touched"] += commitment_count
            summary["horizons"][horizon] = {
                "plan_id": plan_id,
                "goals_selected": len(selected),
                "plan_items_touched": item_count,
                "commitments_touched": commitment_count,
                "window_start": start_iso,
                "window_end": end_iso,
            }

        log.info(
            "🗓️ LongTermPlanner: %d Planfenster, %d Commitments",
            summary["plans_touched"],
            summary["commitments_touched"],
        )
        return summary

    def _build_windows(self, now: datetime) -> Dict[str, Tuple[str, str]]:
        daily_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        daily_end = daily_start + timedelta(days=1)

        week_start = (daily_start - timedelta(days=daily_start.weekday())).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        week_end = week_start + timedelta(days=7)

        month_start = daily_start.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        if month_start.month == 12:
            month_end = month_start.replace(year=month_start.year + 1, month=1, day=1)
        else:
            month_end = month_start.replace(month=month_start.month + 1, day=1)

        return {
            PlanHorizon.DAILY: (daily_start.isoformat(), daily_end.isoformat()),
            PlanHorizon.WEEKLY: (week_start.isoformat(), week_end.isoformat()),
            PlanHorizon.MONTHLY: (month_start.isoformat(), month_end.isoformat()),
        }

    def _select_goals_for_horizon(self, horizon: str, goals: List[dict]) -> List[dict]:
        ordered = sorted(goals, key=lambda g: float(g.get("priority_score") or 0.0), reverse=True)
        if horizon == PlanHorizon.DAILY:
            return ordered[:3]
        if horizon == PlanHorizon.WEEKLY:
            return ordered[:6]
        return ordered[:10]

    def _success_metric_for_horizon(self, horizon: str) -> str:
        if horizon == PlanHorizon.DAILY:
            return ">=1 task completed today"
        if horizon == PlanHorizon.WEEKLY:
            return "goal progress delta >= 20%"
        return "goal status in {completed,active with >=50% progress}"
