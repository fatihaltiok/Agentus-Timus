"""M6.1 Autonomy Audit Report: Mehr-Tages-Profil + Rollout-Empfehlung."""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Optional

from orchestration.autonomy_scorecard import build_autonomy_scorecard
from utils.policy_gate import get_policy_decision_metrics

AUDIT_REPORT_DIR = Path(__file__).resolve().parent.parent / "logs" / "autonomy_audit"


def _to_int(value: Any, default: int, minimum: int) -> int:
    try:
        return max(minimum, int(value))
    except Exception:
        return max(minimum, int(default))


def _rollout_recommendation(
    *,
    scorecard: Dict[str, Any],
    trends: Dict[str, Any],
    policy_metrics: Dict[str, Any],
) -> Dict[str, Any]:
    control = scorecard.get("control") if isinstance(scorecard.get("control"), dict) else {}
    governance_state = str(control.get("scorecard_governance_state") or "allow").strip().lower() or "allow"
    strict_force_off = bool(control.get("strict_force_off", False))
    last_action = str(control.get("scorecard_last_action") or "").strip().lower()
    trend_direction = str(trends.get("trend_direction", "stable") or "stable").strip().lower()
    trend_delta = float(trends.get("trend_delta", 0.0) or 0.0)
    volatility = float(trends.get("volatility_window", 0.0) or 0.0)
    overall = float(scorecard.get("overall_score", 0.0) or 0.0)
    ready_for_very_high = bool(scorecard.get("ready_for_very_high_autonomy", False))
    blocked_total = int(policy_metrics.get("blocked_total", 0) or 0)
    decisions_total = int(policy_metrics.get("decisions_total", 0) or 0)

    risk_flags: list[str] = []
    if strict_force_off:
        risk_flags.append("strict_force_off")
    if governance_state in {"freeze", "force_rollback"}:
        risk_flags.append(f"governance:{governance_state}")
    if trend_direction == "declining":
        risk_flags.append("trend_declining")
    if volatility >= 12.0:
        risk_flags.append("high_volatility")
    if decisions_total > 0 and (blocked_total / decisions_total) >= 0.45:
        risk_flags.append("high_policy_block_rate")

    if governance_state == "force_rollback" or strict_force_off or last_action in {
        "governance_force_rollback",
        "rollback_applied",
    }:
        recommendation = "rollback"
        reason = "hard_risk_signal"
    elif governance_state == "freeze" or trend_direction == "declining" or volatility >= 12.0:
        recommendation = "hold"
        reason = "stability_guard"
    elif ready_for_very_high and overall >= 85.0 and trend_direction in {"stable", "improving"}:
        recommendation = "promote"
        reason = "high_stable_readiness"
    elif overall >= 75.0 and trend_direction == "improving":
        recommendation = "promote"
        reason = "improving_profile"
    else:
        recommendation = "hold"
        reason = "insufficient_evidence"

    return {
        "recommendation": recommendation,
        "reason": reason,
        "risk_flags": sorted(set(risk_flags)),
        "governance_state": governance_state,
        "strict_force_off": strict_force_off,
        "trend_direction": trend_direction,
        "trend_delta": round(trend_delta, 2),
        "volatility_window": round(volatility, 2),
    }


def build_autonomy_audit_report(
    *,
    queue=None,
    window_days: int = 7,
    baseline_days: int = 30,
    scorecard: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    if queue is None:
        from orchestration.task_queue import get_queue

        queue = get_queue()

    window_d = _to_int(window_days, default=7, minimum=1)
    baseline_d = _to_int(baseline_days, default=30, minimum=2)
    window_hours = max(24, window_d * 24)

    card = scorecard if isinstance(scorecard, dict) else build_autonomy_scorecard(
        queue=queue,
        window_hours=window_hours,
    )
    trends = queue.get_autonomy_scorecard_trends(window_hours=window_hours, baseline_days=baseline_d)
    policy_metrics = get_policy_decision_metrics(window_hours=window_hours)
    rollout = _rollout_recommendation(scorecard=card, trends=trends, policy_metrics=policy_metrics)

    return {
        "timestamp": datetime.now().isoformat(),
        "window_days": window_d,
        "window_hours": window_hours,
        "baseline_days": baseline_d,
        "scorecard": {
            "overall_score": float(card.get("overall_score", 0.0) or 0.0),
            "overall_score_10": float(card.get("overall_score_10", 0.0) or 0.0),
            "autonomy_level": str(card.get("autonomy_level", "low") or "low"),
            "ready_for_very_high_autonomy": bool(card.get("ready_for_very_high_autonomy", False)),
            "control": card.get("control") if isinstance(card.get("control"), dict) else {},
            "pillars": card.get("pillars") if isinstance(card.get("pillars"), dict) else {},
        },
        "trends": trends,
        "policy_metrics": {
            "decisions_total": int(policy_metrics.get("decisions_total", 0) or 0),
            "blocked_total": int(policy_metrics.get("blocked_total", 0) or 0),
            "observed_total": int(policy_metrics.get("observed_total", 0) or 0),
            "strict_decisions": int(policy_metrics.get("strict_decisions", 0) or 0),
            "canary_deferred_total": int(policy_metrics.get("canary_deferred_total", 0) or 0),
            "scorecard_governance_state": policy_metrics.get("scorecard_governance_state"),
        },
        "rollout_policy": rollout,
    }


def export_autonomy_audit_report(
    *,
    queue=None,
    report: Optional[Dict[str, Any]] = None,
    output_dir: Optional[Path] = None,
    window_days: int = 7,
    baseline_days: int = 30,
) -> Dict[str, Any]:
    if queue is None:
        from orchestration.task_queue import get_queue

        queue = get_queue()

    final_report = report if isinstance(report, dict) else build_autonomy_audit_report(
        queue=queue,
        window_days=window_days,
        baseline_days=baseline_days,
    )

    out_dir = output_dir or AUDIT_REPORT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)

    now = datetime.now()
    filename = f"{now.strftime('%Y-%m-%d_%H%M%S')}_autonomy_audit_report.json"
    path = out_dir / filename
    with open(path, "w", encoding="utf-8") as f:
        json.dump(final_report, f, ensure_ascii=True, indent=2, default=str)
        f.write("\n")

    now_iso = now.isoformat()
    recommendation = str(
        final_report.get("rollout_policy", {}).get("recommendation", "hold")
    ).strip().lower() or "hold"
    queue.set_policy_runtime_state(
        "audit_report_last_path",
        str(path),
        metadata_update={
            "action": "export_audit_report",
            "recommendation": recommendation,
            "generated_at": now_iso,
        },
        observed_at=now_iso,
    )
    queue.set_policy_runtime_state(
        "audit_report_last_recommendation",
        recommendation,
        metadata_update={
            "action": "export_audit_report",
            "path": str(path),
            "generated_at": now_iso,
        },
        observed_at=now_iso,
    )
    queue.set_policy_runtime_state(
        "audit_report_last_exported_at",
        now_iso,
        metadata_update={
            "action": "export_audit_report",
            "path": str(path),
            "recommendation": recommendation,
        },
        observed_at=now_iso,
    )

    return {
        "status": "ok",
        "path": str(path),
        "recommendation": recommendation,
        "generated_at": now_iso,
        "report": final_report,
    }


def should_export_audit_report(
    *,
    queue=None,
    cadence_hours: int = 6,
) -> Dict[str, Any]:
    if queue is None:
        from orchestration.task_queue import get_queue

        queue = get_queue()

    cadence = max(1, _to_int(cadence_hours, default=6, minimum=1))
    state = queue.get_policy_runtime_state("audit_report_last_exported_at")
    if not state:
        return {"should_export": True, "reason": "no_previous_export", "cadence_hours": cadence}

    raw = str(state.get("state_value") or "").strip()
    try:
        last_dt = datetime.fromisoformat(raw) if raw else None
    except Exception:
        last_dt = None
    if last_dt is None:
        return {"should_export": True, "reason": "invalid_previous_timestamp", "cadence_hours": cadence}

    now = datetime.now()
    due_at = last_dt + timedelta(hours=cadence)
    if now >= due_at:
        return {
            "should_export": True,
            "reason": "cadence_elapsed",
            "cadence_hours": cadence,
            "last_exported_at": last_dt.isoformat(),
        }

    remaining_h = (due_at - now).total_seconds() / 3600.0
    return {
        "should_export": False,
        "reason": "cadence_not_elapsed",
        "cadence_hours": cadence,
        "last_exported_at": last_dt.isoformat(),
        "remaining_hours": round(max(0.0, remaining_h), 2),
    }

