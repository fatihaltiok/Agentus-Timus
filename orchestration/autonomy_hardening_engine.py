"""M7: Rollout-Hardening Gate fuer Stabilitaet vor/autonomem Rollout."""

from __future__ import annotations

import os
from datetime import datetime
from typing import Any, Dict, Optional


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name, "true" if default else "false").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def _to_int(value: Any, default: int, minimum: int) -> int:
    try:
        return max(minimum, int(value))
    except Exception:
        return max(minimum, int(default))


def _to_float(value: Any, default: float, minimum: float) -> float:
    try:
        return max(minimum, float(value))
    except Exception:
        return max(minimum, float(default))


def _hardening_enabled() -> bool:
    if _env_bool("AUTONOMY_COMPAT_MODE", True):
        return False
    return _env_bool("AUTONOMY_HARDENING_ENABLED", False)


def _hardening_enforce() -> bool:
    if _env_bool("AUTONOMY_COMPAT_MODE", True):
        return False
    return _env_bool("AUTONOMY_HARDENING_ENFORCE", False)


def _window_hours() -> int:
    return _to_int(os.getenv("AUTONOMY_HARDENING_WINDOW_HOURS", "24"), default=24, minimum=1)


def _max_open_incidents() -> int:
    return _to_int(os.getenv("AUTONOMY_HARDENING_MAX_OPEN_INCIDENTS", "2"), default=2, minimum=0)


def _min_recovery_rate_24h() -> float:
    return _to_float(
        os.getenv("AUTONOMY_HARDENING_MIN_RECOVERY_RATE_24H", "70"),
        default=70.0,
        minimum=0.0,
    )


def _max_policy_block_rate_24h() -> float:
    return _to_float(
        os.getenv("AUTONOMY_HARDENING_MAX_POLICY_BLOCK_RATE_24H", "35"),
        default=35.0,
        minimum=0.0,
    )


def _max_pending_approvals() -> int:
    return _to_int(os.getenv("AUTONOMY_HARDENING_MAX_PENDING_APPROVALS", "5"), default=5, minimum=0)


def _min_autonomy_score() -> float:
    return _to_float(os.getenv("AUTONOMY_HARDENING_MIN_AUTONOMY_SCORE", "75"), default=75.0, minimum=0.0)


def _rollback_on_red() -> bool:
    if _env_bool("AUTONOMY_COMPAT_MODE", True):
        return False
    return _env_bool("AUTONOMY_HARDENING_ROLLBACK_ON_RED", True)


def _freeze_on_yellow() -> bool:
    if _env_bool("AUTONOMY_COMPAT_MODE", True):
        return False
    return _env_bool("AUTONOMY_HARDENING_FREEZE_ON_YELLOW", True)


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return int(default)


def _policy_block_rate(policy_metrics: Dict[str, Any]) -> float:
    decisions = _safe_int(policy_metrics.get("decisions_total"), 0)
    blocked = _safe_int(policy_metrics.get("blocked_total"), 0)
    if decisions <= 0:
        return 0.0
    return round((blocked / decisions) * 100.0, 2)


def _evaluate_state(
    *,
    open_incidents: int,
    recovery_rate_24h: float,
    policy_block_rate_24h: float,
    pending_approvals: int,
    autonomy_score: float,
) -> Dict[str, Any]:
    reasons: list[str] = []
    critical_reasons: list[str] = []

    max_open = _max_open_incidents()
    min_recovery = _min_recovery_rate_24h()
    max_policy_block = _max_policy_block_rate_24h()
    max_pending = _max_pending_approvals()
    min_score = _min_autonomy_score()

    if open_incidents > max_open:
        reasons.append(f"open_incidents>{max_open}")
    if recovery_rate_24h < min_recovery:
        reasons.append(f"recovery_rate_24h<{min_recovery}")
    if policy_block_rate_24h > max_policy_block:
        reasons.append(f"policy_block_rate_24h>{max_policy_block}")
    if pending_approvals > max_pending:
        reasons.append(f"pending_approvals>{max_pending}")
    if autonomy_score < min_score:
        reasons.append(f"autonomy_score<{min_score}")

    if open_incidents > max(max_open + 2, max_open * 2):
        critical_reasons.append("open_incidents_critical")
    if recovery_rate_24h < max(0.0, min_recovery - 30.0):
        critical_reasons.append("recovery_rate_critical")
    if policy_block_rate_24h > (max_policy_block + 20.0):
        critical_reasons.append("policy_block_rate_critical")
    if pending_approvals > (max_pending + 10):
        critical_reasons.append("pending_approvals_critical")
    if autonomy_score < max(0.0, min_score - 20.0):
        critical_reasons.append("autonomy_score_critical")

    state = "green"
    if critical_reasons:
        state = "red"
    elif reasons:
        state = "yellow"

    return {
        "state": state,
        "reasons": reasons,
        "critical_reasons": critical_reasons,
        "thresholds": {
            "max_open_incidents": max_open,
            "min_recovery_rate_24h": min_recovery,
            "max_policy_block_rate_24h": max_policy_block,
            "max_pending_approvals": max_pending,
            "min_autonomy_score": min_score,
        },
    }


def build_rollout_hardening_snapshot(
    *,
    queue=None,
    window_hours: Optional[int] = None,
    scorecard: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    if queue is None:
        from orchestration.task_queue import get_queue

        queue = get_queue()

    effective_window = max(1, int(window_hours or _window_hours()))

    healing_metrics = queue.get_self_healing_metrics()
    open_incidents = _safe_int(healing_metrics.get("open_incidents"), 0)
    recovery_rate_24h = _safe_float(healing_metrics.get("recovery_rate_24h"), 0.0)

    try:
        from utils.policy_gate import get_policy_decision_metrics

        policy_metrics = get_policy_decision_metrics(window_hours=effective_window)
    except Exception:
        policy_metrics = {
            "decisions_total": 0,
            "blocked_total": 0,
            "observed_total": 0,
            "strict_decisions": 0,
            "canary_deferred_total": 0,
        }
    policy_block_rate_24h = _policy_block_rate(policy_metrics)

    if not isinstance(scorecard, dict):
        try:
            from orchestration.autonomy_scorecard import build_autonomy_scorecard

            scorecard = build_autonomy_scorecard(queue=queue, window_hours=effective_window)
        except Exception:
            scorecard = {"overall_score": 0.0}

    autonomy_score = _safe_float((scorecard or {}).get("overall_score"), 0.0)
    pending_state = queue.get_policy_runtime_state("audit_change_pending_approval_count")
    pending_approvals = _safe_int((pending_state or {}).get("state_value"), 0)

    evaluation = _evaluate_state(
        open_incidents=open_incidents,
        recovery_rate_24h=recovery_rate_24h,
        policy_block_rate_24h=policy_block_rate_24h,
        pending_approvals=pending_approvals,
        autonomy_score=autonomy_score,
    )

    return {
        "timestamp": datetime.now().isoformat(),
        "window_hours": effective_window,
        "metrics": {
            "open_incidents": open_incidents,
            "recovery_rate_24h": round(recovery_rate_24h, 2),
            "policy_block_rate_24h": round(policy_block_rate_24h, 2),
            "pending_approvals": pending_approvals,
            "autonomy_score": round(autonomy_score, 2),
        },
        "evaluation": evaluation,
    }


def evaluate_and_apply_rollout_hardening(
    *,
    queue=None,
    window_hours: Optional[int] = None,
    scorecard: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    if not _hardening_enabled():
        return {"status": "disabled", "action": "none"}

    if queue is None:
        from orchestration.task_queue import get_queue

        queue = get_queue()

    snapshot = build_rollout_hardening_snapshot(
        queue=queue,
        window_hours=window_hours,
        scorecard=scorecard,
    )
    evaluation = snapshot.get("evaluation") if isinstance(snapshot.get("evaluation"), dict) else {}
    metrics = snapshot.get("metrics") if isinstance(snapshot.get("metrics"), dict) else {}
    state = str(evaluation.get("state") or "green").strip().lower() or "green"
    reasons = evaluation.get("reasons") if isinstance(evaluation.get("reasons"), list) else []
    now_iso = str(snapshot.get("timestamp") or datetime.now().isoformat())

    enforce = _hardening_enforce()
    action = "none"
    strict_force_off = None
    next_canary = None
    freeze_active = False

    if enforce:
        if state == "red" and _rollback_on_red():
            queue.set_policy_runtime_state(
                "strict_force_off",
                "true",
                metadata_update={"reason": "hardening_red", "source": "autonomy_hardening"},
                observed_at=now_iso,
            )
            queue.set_policy_runtime_state(
                "canary_percent_override",
                "0",
                metadata_update={"reason": "hardening_red", "source": "autonomy_hardening"},
                observed_at=now_iso,
            )
            action = "rollback_applied"
            strict_force_off = True
            next_canary = 0
            freeze_active = True
        elif state == "yellow" and _freeze_on_yellow():
            queue.set_policy_runtime_state(
                "hardening_rollout_freeze",
                "true",
                metadata_update={"reason": "hardening_yellow", "source": "autonomy_hardening"},
                observed_at=now_iso,
            )
            action = "freeze_applied"
            freeze_active = True
        else:
            queue.set_policy_runtime_state(
                "hardening_rollout_freeze",
                "false",
                metadata_update={"reason": "hardening_green", "source": "autonomy_hardening"},
                observed_at=now_iso,
            )
            action = "normal"
    else:
        # Beobachtungsmodus ohne Eingriff.
        freeze_state = queue.get_policy_runtime_state("hardening_rollout_freeze")
        freeze_active = str((freeze_state or {}).get("state_value") or "false").strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }

    queue.set_policy_runtime_state(
        "hardening_last_state",
        state,
        metadata_update={"reasons": reasons[:6], "enforce": enforce},
        observed_at=now_iso,
    )
    queue.set_policy_runtime_state(
        "hardening_last_action",
        action,
        metadata_update={"state": state, "enforce": enforce},
        observed_at=now_iso,
    )
    queue.set_policy_runtime_state(
        "hardening_last_reasons",
        ",".join(str(r) for r in reasons[:8]) or "none",
        metadata_update={"count": len(reasons)},
        observed_at=now_iso,
    )
    queue.set_policy_runtime_state(
        "hardening_last_checked_at",
        now_iso,
        metadata_update={"window_hours": snapshot.get("window_hours", 0)},
        observed_at=now_iso,
    )
    queue.set_policy_runtime_state(
        "hardening_policy_block_rate_24h",
        str(metrics.get("policy_block_rate_24h", 0.0)),
        metadata_update={"state": state},
        observed_at=now_iso,
    )
    queue.set_policy_runtime_state(
        "hardening_pending_approvals",
        str(metrics.get("pending_approvals", 0)),
        metadata_update={"state": state},
        observed_at=now_iso,
    )
    queue.set_policy_runtime_state(
        "hardening_recovery_rate_24h",
        str(metrics.get("recovery_rate_24h", 0.0)),
        metadata_update={"state": state},
        observed_at=now_iso,
    )
    queue.set_policy_runtime_state(
        "hardening_open_incidents",
        str(metrics.get("open_incidents", 0)),
        metadata_update={"state": state},
        observed_at=now_iso,
    )
    queue.set_policy_runtime_state(
        "hardening_autonomy_score",
        str(metrics.get("autonomy_score", 0.0)),
        metadata_update={"state": state},
        observed_at=now_iso,
    )

    return {
        "status": "ok",
        "state": state,
        "action": action,
        "enforce": enforce,
        "reasons": reasons,
        "strict_force_off": strict_force_off,
        "next_canary_percent": next_canary,
        "freeze_active": freeze_active,
        "snapshot": snapshot,
    }
