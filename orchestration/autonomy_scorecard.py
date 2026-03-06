"""M5.1 Autonomy Scorecard: vereinheitlichte KPI-Reife aus M1-M4."""

from __future__ import annotations

import os
from datetime import datetime
from typing import Any, Dict, Optional

from utils.policy_gate import get_policy_decision_metrics


def _clamp(value: float, minimum: float = 0.0, maximum: float = 100.0) -> float:
    '''
    pre: minimum <= maximum
    post: minimum <= __return__ <= maximum
    '''
    return max(minimum, min(maximum, float(value)))


def _round2(value: float) -> float:
    return round(float(value), 2)


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name, "true" if default else "false").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def _scorecard_control_enabled() -> bool:
    if _env_bool("AUTONOMY_COMPAT_MODE", True):
        return False
    return _env_bool("AUTONOMY_SCORECARD_CONTROL_ENABLED", False)


def _scorecard_adaptive_thresholds_enabled() -> bool:
    if _env_bool("AUTONOMY_COMPAT_MODE", True):
        return False
    return _env_bool("AUTONOMY_SCORECARD_ADAPTIVE_THRESHOLDS_ENABLED", False)


def _scorecard_governance_enabled() -> bool:
    if _env_bool("AUTONOMY_COMPAT_MODE", True):
        return False
    return _env_bool("AUTONOMY_SCORECARD_GOVERNANCE_ENABLED", False)


def _score_goals(goal_metrics: Dict[str, Any]) -> Dict[str, Any]:
    open_alignment = float(goal_metrics.get("open_alignment_rate", 0.0) or 0.0)
    conflicts = int(goal_metrics.get("conflict_count", 0) or 0)
    orphan_triggered = int(goal_metrics.get("orphan_triggered_tasks", 0) or 0)
    open_tasks = int(goal_metrics.get("open_tasks", 0) or 0)

    if open_tasks == 0:
        score = 80.0
    else:
        conflict_penalty = min(35.0, conflicts * 7.0)
        orphan_penalty = min(20.0, orphan_triggered * 4.0)
        score = open_alignment - conflict_penalty - orphan_penalty

    return {
        "score": _round2(_clamp(score)),
        "open_alignment_rate": _round2(open_alignment),
        "conflict_count": conflicts,
        "orphan_triggered_tasks": orphan_triggered,
    }


def _score_planning(
    planning_metrics: Dict[str, Any],
    replanning_metrics: Dict[str, Any],
    review_metrics: Dict[str, Any],
) -> Dict[str, Any]:
    deviation = float(planning_metrics.get("plan_deviation_score", 0.0) or 0.0)
    overdue = int(planning_metrics.get("overdue_commitments", 0) or 0)
    due_reviews = int(review_metrics.get("due_reviews", 0) or 0)
    escalated_reviews = int(review_metrics.get("escalated_last_7d", 0) or 0)
    events_last_24h = int(replanning_metrics.get("events_last_24h", 0) or 0)
    applied_last_24h = int(replanning_metrics.get("applied_last_24h", 0) or 0)
    commitments_total = int(planning_metrics.get("commitments_total", 0) or 0)
    active_plans = int(planning_metrics.get("active_plans", 0) or 0)

    if commitments_total == 0 and active_plans == 0:
        score = 70.0
    else:
        score = (
            100.0
            - min(45.0, deviation * 10.0)
            - min(30.0, overdue * 5.0)
            - min(15.0, due_reviews * 2.0)
            - min(10.0, escalated_reviews * 2.0)
        )
        if events_last_24h > 0 and applied_last_24h > 0:
            score += min(10.0, applied_last_24h * 2.0)

    return {
        "score": _round2(_clamp(score)),
        "plan_deviation_score": _round2(deviation),
        "overdue_commitments": overdue,
        "due_reviews": due_reviews,
        "escalated_reviews_7d": escalated_reviews,
        "replanning_events_24h": events_last_24h,
        "replanning_applied_24h": applied_last_24h,
    }


def _score_self_healing(healing_metrics: Dict[str, Any]) -> Dict[str, Any]:
    degrade_mode = str(healing_metrics.get("degrade_mode", "normal") or "normal").strip().lower()
    recovery_rate = float(healing_metrics.get("recovery_rate_24h", 0.0) or 0.0)
    open_incidents = int(healing_metrics.get("open_incidents", 0) or 0)
    open_escalated = int(healing_metrics.get("open_escalated_incidents", 0) or 0)
    breaker_open = int(healing_metrics.get("circuit_breakers_open", 0) or 0)
    created_24h = int(healing_metrics.get("created_last_24h", 0) or 0)
    recovered_24h = int(healing_metrics.get("recovered_last_24h", 0) or 0)

    if created_24h == 0 and open_incidents == 0 and breaker_open == 0 and degrade_mode == "normal":
        score = 100.0
    elif created_24h == 0 and open_incidents == 0:
        score = 85.0
    else:
        score = (
            recovery_rate
            - min(35.0, open_incidents * 7.0)
            - min(20.0, open_escalated * 10.0)
            - min(20.0, breaker_open * 10.0)
        )
        if created_24h > 0 and recovered_24h == 0:
            score -= 15.0

    degrade_penalty = {
        "normal": 0.0,
        "cautious": 15.0,
        "restricted": 30.0,
        "emergency": 45.0,
    }.get(degrade_mode, 20.0)
    score -= degrade_penalty

    return {
        "score": _round2(_clamp(score)),
        "degrade_mode": degrade_mode,
        "open_incidents": open_incidents,
        "open_escalated_incidents": open_escalated,
        "circuit_breakers_open": breaker_open,
        "recovery_rate_24h": _round2(recovery_rate),
    }


def _score_policy(policy_metrics: Dict[str, Any]) -> Dict[str, Any]:
    decisions_total = int(policy_metrics.get("decisions_total", 0) or 0)
    blocked_total = int(policy_metrics.get("blocked_total", 0) or 0)
    observed_total = int(policy_metrics.get("observed_total", 0) or 0)
    canary_deferred_total = int(policy_metrics.get("canary_deferred_total", 0) or 0)
    strict_force_off = bool(policy_metrics.get("strict_force_off", False))
    by_gate = policy_metrics.get("by_gate") if isinstance(policy_metrics.get("by_gate"), dict) else {}

    expected_gates = {"query", "tool", "delegation", "autonomous_task"}
    covered_gates = expected_gates.intersection({str(k) for k in by_gate.keys()})
    coverage_pct = (len(covered_gates) / len(expected_gates)) * 100.0

    if decisions_total > 0:
        block_rate = (blocked_total / decisions_total) * 100.0
        observe_rate = (observed_total / decisions_total) * 100.0
        deferred_rate = (canary_deferred_total / decisions_total) * 100.0
        integrity = 100.0 - min(40.0, deferred_rate * 1.5) - (30.0 if strict_force_off else 0.0)
        discipline = 100.0 - min(50.0, observe_rate)
        score = (0.45 * coverage_pct) + (0.35 * integrity) + (0.20 * discipline)
        score -= min(20.0, max(0.0, block_rate - 35.0) * 0.5)
    else:
        block_rate = 0.0
        observe_rate = 0.0
        deferred_rate = 0.0
        integrity = 60.0 - (30.0 if strict_force_off else 0.0)
        discipline = 50.0
        score = 35.0

    return {
        "score": _round2(_clamp(score)),
        "decisions_total": decisions_total,
        "block_rate_pct": _round2(block_rate),
        "observe_rate_pct": _round2(observe_rate),
        "canary_deferred_rate_pct": _round2(deferred_rate),
        "gate_coverage_pct": _round2(coverage_pct),
        "strict_force_off": strict_force_off,
        "covered_gates": sorted(covered_gates),
    }


def _autonomy_level(score: float) -> str:
    if score >= 85.0:
        return "very_high"
    if score >= 75.0:
        return "high"
    if score >= 60.0:
        return "medium"
    if score >= 45.0:
        return "developing"
    return "low"


def _adaptive_control_thresholds(
    *,
    queue,
    window_hours: int,
    baseline_days: int,
    promote_threshold: float,
    rollback_threshold: float,
) -> Dict[str, Any]:
    trends = queue.get_autonomy_scorecard_trends(
        window_hours=window_hours,
        baseline_days=baseline_days,
    )
    promote = float(promote_threshold)
    rollback = float(rollback_threshold)
    mode = "stable"
    reason = "insufficient_data"

    samples = int(trends.get("samples_window", 0) or 0)
    delta = float(trends.get("trend_delta", 0.0) or 0.0)
    volatility = float(trends.get("volatility_window", 0.0) or 0.0)
    avg_window = float(trends.get("avg_score_window", 0.0) or 0.0)

    if samples >= 3:
        if delta <= -4.0 or volatility >= 12.0:
            promote += 5.0
            rollback += 5.0
            mode = "tighten"
            reason = "declining_or_volatile"
        elif delta >= 4.0 and volatility <= 6.0 and avg_window >= max(50.0, promote - 8.0):
            promote -= 5.0
            rollback -= 5.0
            mode = "relax"
            reason = "improving_and_stable"
        else:
            mode = "stable"
            reason = "balanced_trend"

    promote = _clamp(promote, 60.0, 95.0)
    rollback = _clamp(rollback, 35.0, 90.0)
    if rollback > promote - 5.0:
        rollback = max(35.0, promote - 5.0)

    return {
        "mode": mode,
        "reason": reason,
        "promote_threshold": _round2(promote),
        "rollback_threshold": _round2(rollback),
        "trend": trends,
    }


def _evaluate_scorecard_governance(*, card: Dict[str, Any], trend: Dict[str, Any]) -> Dict[str, Any]:
    if not _scorecard_governance_enabled():
        return {
            "state": "allow",
            "reason": "governance_disabled",
            "reasons": [],
            "pillars_below_min": [],
            "pillars_below_critical": [],
            "min_pillar_threshold": 0.0,
            "critical_pillar_threshold": 0.0,
        }

    try:
        min_pillar = float(os.getenv("AUTONOMY_SCORECARD_MIN_PILLAR_SCORE", "60"))
    except Exception:
        min_pillar = 60.0
    try:
        critical_pillar = float(os.getenv("AUTONOMY_SCORECARD_CRITICAL_PILLAR_SCORE", "40"))
    except Exception:
        critical_pillar = 40.0
    freeze_declining = _env_bool("AUTONOMY_SCORECARD_FREEZE_ON_DECLINING", True)
    try:
        decline_delta = float(os.getenv("AUTONOMY_SCORECARD_DECLINE_DELTA", "-6"))
    except Exception:
        decline_delta = -6.0
    try:
        volatility_limit = float(os.getenv("AUTONOMY_SCORECARD_VOLATILITY_FREEZE_THRESHOLD", "12"))
    except Exception:
        volatility_limit = 12.0

    pillars_raw = card.get("pillars") if isinstance(card.get("pillars"), dict) else {}
    pillar_scores: Dict[str, float] = {}
    for key in ("goals", "planning", "self_healing", "policy"):
        raw = pillars_raw.get(key)
        if isinstance(raw, dict):
            try:
                pillar_scores[key] = float(raw.get("score", 0.0) or 0.0)
            except Exception:
                pillar_scores[key] = 0.0

    below_min = [k for k, v in pillar_scores.items() if v < min_pillar]
    below_critical = [k for k, v in pillar_scores.items() if v < critical_pillar]

    reasons: list[str] = []
    state = "allow"
    reason = "ok"

    if below_critical:
        state = "force_rollback"
        reason = "critical_pillar_breach"
        reasons.append("critical_pillar_breach")
    elif below_min:
        state = "freeze"
        reason = "min_pillar_breach"
        reasons.append("min_pillar_breach")

    trend_delta = float(trend.get("trend_delta", 0.0) or 0.0)
    volatility = float(trend.get("volatility_window", 0.0) or 0.0)
    if state == "allow" and freeze_declining and (trend_delta <= decline_delta or volatility >= volatility_limit):
        state = "freeze"
        reason = "declining_or_volatile_trend"
        reasons.append("declining_or_volatile_trend")

    return {
        "state": state,
        "reason": reason,
        "reasons": reasons,
        "pillars_below_min": sorted(below_min),
        "pillars_below_critical": sorted(below_critical),
        "min_pillar_threshold": _round2(min_pillar),
        "critical_pillar_threshold": _round2(critical_pillar),
        "decline_delta_threshold": _round2(decline_delta),
        "volatility_freeze_threshold": _round2(volatility_limit),
    }


def _read_control_runtime(queue) -> Dict[str, Any]:
    strict_state = queue.get_policy_runtime_state("strict_force_off")
    canary_state = queue.get_policy_runtime_state("canary_percent_override")
    action_state = queue.get_policy_runtime_state("scorecard_last_action")
    score_state = queue.get_policy_runtime_state("scorecard_last_score")
    governance_state = queue.get_policy_runtime_state("scorecard_governance_state")

    strict_force_off = False
    if strict_state:
        strict_force_off = str(strict_state.get("state_value") or "").strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }

    canary_override: Optional[int] = None
    if canary_state:
        try:
            canary_override = int(str(canary_state.get("state_value") or "").strip())
        except Exception:
            canary_override = None

    last_action = None
    last_action_at = None
    if action_state:
        last_action = str(action_state.get("state_value") or "").strip() or None
        last_action_at = str(action_state.get("updated_at") or "").strip() or None

    last_score: Optional[float] = None
    if score_state:
        try:
            last_score = float(str(score_state.get("state_value") or "").strip())
        except Exception:
            last_score = None

    governance_value = None
    governance_reason = None
    governance_updated_at = None
    if governance_state:
        governance_value = str(governance_state.get("state_value") or "").strip() or None
        governance_updated_at = str(governance_state.get("updated_at") or "").strip() or None
        meta = governance_state.get("metadata")
        if isinstance(meta, dict):
            governance_reason = str(meta.get("reason") or "").strip() or None

    return {
        "strict_force_off": strict_force_off,
        "canary_percent_override": canary_override,
        "scorecard_last_action": last_action,
        "scorecard_last_action_at": last_action_at,
        "scorecard_last_score": last_score,
        "scorecard_governance_state": governance_value,
        "scorecard_governance_reason": governance_reason,
        "scorecard_governance_updated_at": governance_updated_at,
    }


def build_autonomy_scorecard(*, queue=None, window_hours: int = 24) -> Dict[str, Any]:
    """Aggregiert M1-M4-KPIs zu einem kompakten Autonomie-Reifegrad."""
    if queue is None:
        from orchestration.task_queue import get_queue

        queue = get_queue()

    goal_metrics = queue.get_goal_alignment_metrics(include_conflicts=True)
    planning_metrics = queue.get_planning_metrics()
    replanning_metrics = queue.get_replanning_metrics()
    review_metrics = queue.get_commitment_review_metrics()
    healing_metrics = queue.get_self_healing_metrics()
    policy_metrics = get_policy_decision_metrics(window_hours=max(1, int(window_hours)))

    goals = _score_goals(goal_metrics)
    planning = _score_planning(planning_metrics, replanning_metrics, review_metrics)
    healing = _score_self_healing(healing_metrics)
    policy = _score_policy(policy_metrics)

    overall = (
        goals["score"] * 0.25
        + planning["score"] * 0.25
        + healing["score"] * 0.25
        + policy["score"] * 0.25
    )
    overall = _round2(_clamp(overall))

    pillars = [float(goals["score"]), float(planning["score"]), float(healing["score"]), float(policy["score"])]
    ready_for_very_high = (
        overall >= 85.0
        and min(pillars) >= 70.0
        and not bool(policy.get("strict_force_off", False))
        and str(healing.get("degrade_mode", "normal")) == "normal"
    )
    control_runtime = _read_control_runtime(queue)
    try:
        baseline_days = max(2, int(os.getenv("AUTONOMY_SCORECARD_TREND_BASELINE_DAYS", "30")))
    except Exception:
        baseline_days = 30
    trends = queue.get_autonomy_scorecard_trends(window_hours=max(1, int(window_hours)), baseline_days=baseline_days)

    return {
        "timestamp": datetime.now().isoformat(),
        "window_hours": max(1, int(window_hours)),
        "overall_score": overall,
        "overall_score_10": _round2(overall / 10.0),
        "autonomy_level": _autonomy_level(overall),
        "ready_for_very_high_autonomy": ready_for_very_high,
        "pillars": {
            "goals": goals,
            "planning": planning,
            "self_healing": healing,
            "policy": policy,
        },
        "weights": {
            "goals": 0.25,
            "planning": 0.25,
            "self_healing": 0.25,
            "policy": 0.25,
        },
        "control": control_runtime,
        "trends": trends,
    }


def evaluate_and_apply_scorecard_control(
    *,
    queue=None,
    window_hours: Optional[int] = None,
    scorecard: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """M5.2: nutzt die Scorecard fuer Promotion/Hold/Rollback-Entscheidungen."""
    if not _scorecard_control_enabled():
        return {"status": "disabled", "action": "none"}

    if queue is None:
        from orchestration.task_queue import get_queue

        queue = get_queue()

    try:
        window = max(
            1,
            int(
                window_hours
                if window_hours is not None
                else os.getenv("AUTONOMY_SCORECARD_WINDOW_HOURS", "24")
            ),
        )
    except Exception:
        window = 24
    card = scorecard if isinstance(scorecard, dict) else build_autonomy_scorecard(queue=queue, window_hours=window)
    overall = float(card.get("overall_score", 0.0) or 0.0)
    self_healing_mode = str(card.get("pillars", {}).get("self_healing", {}).get("degrade_mode", "normal") or "normal").strip().lower()

    try:
        promote_threshold = float(os.getenv("AUTONOMY_SCORECARD_PROMOTE_THRESHOLD", "80"))
    except Exception:
        promote_threshold = 80.0
    try:
        rollback_threshold = float(os.getenv("AUTONOMY_SCORECARD_ROLLBACK_THRESHOLD", "55"))
    except Exception:
        rollback_threshold = 55.0
    try:
        promote_step = max(1, int(os.getenv("AUTONOMY_SCORECARD_PROMOTE_STEP", "10")))
    except Exception:
        promote_step = 10
    try:
        max_canary = max(0, min(100, int(os.getenv("AUTONOMY_SCORECARD_MAX_CANARY", "100"))))
    except Exception:
        max_canary = 100
    try:
        cooldown_min = max(1, int(os.getenv("AUTONOMY_SCORECARD_CONTROL_COOLDOWN_MIN", "120")))
    except Exception:
        cooldown_min = 120
    try:
        baseline_days = max(2, int(os.getenv("AUTONOMY_SCORECARD_TREND_BASELINE_DAYS", "30")))
    except Exception:
        baseline_days = 30

    adaptive_mode = "off"
    adaptive_reason = "disabled"
    trend = queue.get_autonomy_scorecard_trends(window_hours=window, baseline_days=baseline_days)
    if _scorecard_adaptive_thresholds_enabled():
        adaptive = _adaptive_control_thresholds(
            queue=queue,
            window_hours=window,
            baseline_days=baseline_days,
            promote_threshold=promote_threshold,
            rollback_threshold=rollback_threshold,
        )
        promote_threshold = float(adaptive.get("promote_threshold", promote_threshold))
        rollback_threshold = float(adaptive.get("rollback_threshold", rollback_threshold))
        adaptive_mode = str(adaptive.get("mode", "stable"))
        adaptive_reason = str(adaptive.get("reason", "n/a"))
        trend = adaptive.get("trend") if isinstance(adaptive.get("trend"), dict) else trend

    governance = _evaluate_scorecard_governance(card=card, trend=trend)
    governance_state = str(governance.get("state", "allow"))

    runtime = _read_control_runtime(queue)
    current_canary = runtime.get("canary_percent_override")
    if current_canary is None:
        try:
            current_canary = max(0, min(100, int(os.getenv("AUTONOMY_CANARY_PERCENT", "0"))))
        except Exception:
            current_canary = 0
    current_canary = int(current_canary)

    last_action_at_raw = str(runtime.get("scorecard_last_action_at") or "")
    if last_action_at_raw:
        try:
            last_action_at = datetime.fromisoformat(last_action_at_raw)
        except Exception:
            last_action_at = None
    else:
        last_action_at = None

    now = datetime.now()
    now_iso = now.isoformat()
    queue.set_policy_runtime_state(
        "scorecard_governance_state",
        governance_state,
        metadata_update={
            "reason": str(governance.get("reason", "n/a")),
            "reasons": list(governance.get("reasons", [])),
            "pillars_below_min": list(governance.get("pillars_below_min", [])),
            "pillars_below_critical": list(governance.get("pillars_below_critical", [])),
            "trend_delta": float(trend.get("trend_delta", 0.0) or 0.0),
            "volatility_window": float(trend.get("volatility_window", 0.0) or 0.0),
            "updated_by": "scorecard_control",
        },
        observed_at=now_iso,
    )

    if governance_state == "force_rollback":
        reason = f"governance={governance.get('reason', 'force_rollback')}; score={_round2(overall)}, mode={self_healing_mode}"
        queue.set_policy_runtime_state(
            "strict_force_off",
            "true",
            metadata_update={
                "reason": reason,
                "action": "governance_force_rollback",
                "triggered_at": now_iso,
                "threshold": rollback_threshold,
            },
            observed_at=now_iso,
        )
        queue.set_policy_runtime_state(
            "canary_percent_override",
            "0",
            metadata_update={
                "reason": reason,
                "action": "governance_force_rollback",
                "triggered_at": now_iso,
            },
            observed_at=now_iso,
        )
        queue.set_policy_runtime_state(
            "scorecard_last_action",
            "governance_force_rollback",
            metadata_update={
                "reason": reason,
                "overall_score": _round2(overall),
                "triggered_at": now_iso,
            },
            observed_at=now_iso,
        )
        queue.set_policy_runtime_state(
            "scorecard_last_score",
            f"{_round2(overall):.2f}",
            metadata_update={"source": "scorecard_control_governance"},
            observed_at=now_iso,
        )
        return {
            "status": "ok",
            "action": "governance_force_rollback",
            "overall_score": _round2(overall),
            "current_canary_percent": current_canary,
            "next_canary_percent": 0,
            "strict_force_off": True,
            "reason": reason,
            "promote_threshold": _round2(promote_threshold),
            "rollback_threshold": _round2(rollback_threshold),
            "adaptive_mode": adaptive_mode,
            "adaptive_reason": adaptive_reason,
            "trend": trend,
            "governance": governance,
        }

    if governance_state == "freeze":
        reason = f"governance={governance.get('reason', 'freeze')}; score={_round2(overall)}, mode={self_healing_mode}"
        queue.set_policy_runtime_state(
            "scorecard_last_action",
            "governance_hold",
            metadata_update={
                "reason": reason,
                "overall_score": _round2(overall),
                "triggered_at": now_iso,
            },
            observed_at=now_iso,
        )
        queue.set_policy_runtime_state(
            "scorecard_last_score",
            f"{_round2(overall):.2f}",
            metadata_update={"source": "scorecard_control_governance_hold"},
            observed_at=now_iso,
        )
        return {
            "status": "ok",
            "action": "governance_hold",
            "overall_score": _round2(overall),
            "current_canary_percent": current_canary,
            "strict_force_off": bool(runtime.get("strict_force_off", False)),
            "reason": reason,
            "promote_threshold": _round2(promote_threshold),
            "rollback_threshold": _round2(rollback_threshold),
            "adaptive_mode": adaptive_mode,
            "adaptive_reason": adaptive_reason,
            "trend": trend,
            "governance": governance,
        }

    if last_action_at is not None:
        delta_min = (now - last_action_at).total_seconds() / 60.0
        if delta_min < cooldown_min:
            return {
                "status": "ok",
                "action": "cooldown_active",
                "overall_score": _round2(overall),
                "current_canary_percent": current_canary,
                "strict_force_off": bool(runtime.get("strict_force_off", False)),
                "cooldown_remaining_min": _round2(max(0.0, cooldown_min - delta_min)),
                "promote_threshold": _round2(promote_threshold),
                "rollback_threshold": _round2(rollback_threshold),
                "adaptive_mode": adaptive_mode,
                "adaptive_reason": adaptive_reason,
                "trend": trend,
                "governance": governance,
            }

    reason = f"score={_round2(overall)}, mode={self_healing_mode}"

    if overall <= rollback_threshold or self_healing_mode in {"restricted", "emergency"}:
        queue.set_policy_runtime_state(
            "strict_force_off",
            "true",
            metadata_update={
                "reason": reason,
                "action": "scorecard_rollback",
                "triggered_at": now_iso,
                "threshold": rollback_threshold,
            },
            observed_at=now_iso,
        )
        queue.set_policy_runtime_state(
            "canary_percent_override",
            "0",
            metadata_update={
                "reason": reason,
                "action": "scorecard_rollback",
                "triggered_at": now_iso,
            },
            observed_at=now_iso,
        )
        queue.set_policy_runtime_state(
            "scorecard_last_action",
            "rollback_applied",
            metadata_update={
                "reason": reason,
                "overall_score": _round2(overall),
                "triggered_at": now_iso,
            },
            observed_at=now_iso,
        )
        queue.set_policy_runtime_state(
            "scorecard_last_score",
            f"{_round2(overall):.2f}",
            metadata_update={"source": "scorecard_control"},
            observed_at=now_iso,
        )
        return {
            "status": "ok",
            "action": "rollback_applied",
            "overall_score": _round2(overall),
            "current_canary_percent": current_canary,
            "next_canary_percent": 0,
            "strict_force_off": True,
            "reason": reason,
            "promote_threshold": _round2(promote_threshold),
            "rollback_threshold": _round2(rollback_threshold),
            "adaptive_mode": adaptive_mode,
            "adaptive_reason": adaptive_reason,
            "trend": trend,
            "governance": governance,
        }

    if overall >= promote_threshold and self_healing_mode == "normal":
        next_canary = max(0, min(max_canary, current_canary + promote_step))
        if next_canary > current_canary:
            queue.set_policy_runtime_state(
                "canary_percent_override",
                str(next_canary),
                metadata_update={
                    "reason": reason,
                    "action": "scorecard_promote",
                    "triggered_at": now_iso,
                    "promote_step": promote_step,
                    "max_canary": max_canary,
                },
                observed_at=now_iso,
            )
            queue.set_policy_runtime_state(
                "strict_force_off",
                "false",
                metadata_update={
                    "reason": reason,
                    "action": "scorecard_promote",
                    "triggered_at": now_iso,
                },
                observed_at=now_iso,
            )
            queue.set_policy_runtime_state(
                "scorecard_last_action",
                "promote_canary",
                metadata_update={
                    "reason": reason,
                    "overall_score": _round2(overall),
                    "from_canary": current_canary,
                    "to_canary": next_canary,
                    "triggered_at": now_iso,
                },
                observed_at=now_iso,
            )
            queue.set_policy_runtime_state(
                "scorecard_last_score",
                f"{_round2(overall):.2f}",
                metadata_update={"source": "scorecard_control"},
                observed_at=now_iso,
            )
            return {
                "status": "ok",
                "action": "promote_canary",
                "overall_score": _round2(overall),
                "current_canary_percent": current_canary,
                "next_canary_percent": next_canary,
                "strict_force_off": False,
                "reason": reason,
                "promote_threshold": _round2(promote_threshold),
                "rollback_threshold": _round2(rollback_threshold),
                "adaptive_mode": adaptive_mode,
                "adaptive_reason": adaptive_reason,
                "trend": trend,
                "governance": governance,
            }

    queue.set_policy_runtime_state(
        "scorecard_last_score",
        f"{_round2(overall):.2f}",
        metadata_update={"source": "scorecard_control_hold"},
        observed_at=now_iso,
    )
    return {
        "status": "ok",
        "action": "hold",
        "overall_score": _round2(overall),
        "current_canary_percent": current_canary,
        "strict_force_off": bool(runtime.get("strict_force_off", False)),
        "promote_threshold": _round2(promote_threshold),
        "rollback_threshold": _round2(rollback_threshold),
        "adaptive_mode": adaptive_mode,
        "adaptive_reason": adaptive_reason,
        "trend": trend,
        "governance": governance,
    }
