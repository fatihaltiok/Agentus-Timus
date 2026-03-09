"""Escalation and rollout gating based on operational and budget health."""

from __future__ import annotations

import os
from typing import Any, Dict, List


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return max(0, int(raw))
    except ValueError:
        return default


def evaluate_ops_release_gate(
    ops_summary: Dict[str, Any],
    *,
    current_canary_percent: int = 0,
) -> Dict[str, Any]:
    safe_canary = max(0, min(100, int(current_canary_percent or 0)))
    warn_cap = min(100, max(0, _env_int("OPS_WARN_CANARY_CAP_PERCENT", 10)))

    alerts = list((ops_summary or {}).get("alerts", []) or [])
    critical_targets = [str(item.get("target", "")) for item in alerts if item.get("severity") == "critical"]
    warning_targets = [str(item.get("target", "")) for item in alerts if item.get("severity") != "critical"]
    critical_classes = sorted({str(item.get("error_class", "")) for item in alerts if item.get("severity") == "critical"})
    warning_classes = sorted({str(item.get("error_class", "")) for item in alerts if item.get("severity") != "critical"})

    state = str((ops_summary or {}).get("state", "unknown") or "unknown").strip().lower()
    critical_alerts = int((ops_summary or {}).get("critical_alerts", 0) or 0)
    warnings = int((ops_summary or {}).get("warnings", 0) or 0)
    failing_services = int((ops_summary or {}).get("failing_services", 0) or 0)
    unhealthy_providers = int((ops_summary or {}).get("unhealthy_providers", 0) or 0)
    slo_breached = int(((ops_summary or {}).get("slo", {}) or {}).get("breached", 0) or 0)

    if (
        state == "critical"
        or critical_alerts > 0
        or failing_services > 0
        or unhealthy_providers > 0
    ):
        return {
            "state": "blocked",
            "alert_severity": "critical",
            "release_blocked": True,
            "canary_blocked": True,
            "canary_deferred": True,
            "autonomy_hold": True,
            "recommended_canary_percent": 0,
            "reason": "critical_ops_or_budget_health",
            "critical_targets": critical_targets,
            "warning_targets": warning_targets,
            "critical_error_classes": critical_classes,
            "warning_error_classes": warning_classes,
        }

    if state == "warn" or warnings > 0 or slo_breached > 0:
        return {
            "state": "warn",
            "alert_severity": "warn",
            "release_blocked": False,
            "canary_blocked": False,
            "canary_deferred": True,
            "autonomy_hold": True,
            "recommended_canary_percent": min(safe_canary, warn_cap) if safe_canary > 0 else warn_cap,
            "reason": "ops_or_budget_drift",
            "critical_targets": critical_targets,
            "warning_targets": warning_targets,
            "critical_error_classes": critical_classes,
            "warning_error_classes": warning_classes,
        }

    return {
        "state": "pass",
        "alert_severity": "info",
        "release_blocked": False,
        "canary_blocked": False,
        "canary_deferred": False,
        "autonomy_hold": False,
        "recommended_canary_percent": safe_canary,
        "reason": "ops_green",
        "critical_targets": [],
        "warning_targets": [],
        "critical_error_classes": [],
        "warning_error_classes": [],
    }


def build_ops_gate_alert_message(
    ops_summary: Dict[str, Any],
    decision: Dict[str, Any],
) -> str:
    emoji = {
        "blocked": "🔴",
        "warn": "🟠",
        "pass": "🟢",
    }.get(str(decision.get("state", "warn")).lower(), "⚪")
    lines = [
        f"{emoji} *Ops Release Gate*",
        (
            f"State {decision.get('state', 'unknown')} | "
            f"ReleaseBlocked {decision.get('release_blocked', False)} | "
            f"CanaryDeferred {decision.get('canary_deferred', False)} | "
            f"RecommendedCanary {decision.get('recommended_canary_percent', 0)}%"
        ),
        (
            f"Ops state={ops_summary.get('state', 'unknown')} | "
            f"critical={ops_summary.get('critical_alerts', 0)} | "
            f"warn={ops_summary.get('warnings', 0)} | "
            f"services={ops_summary.get('failing_services', 0)} | "
            f"providers={ops_summary.get('unhealthy_providers', 0)}"
        ),
    ]
    if decision.get("critical_targets"):
        lines.append(f"Critical targets: {', '.join(decision.get('critical_targets', [])[:4])}")
    if decision.get("warning_targets"):
        lines.append(f"Warning targets: {', '.join(decision.get('warning_targets', [])[:4])}")
    return "\n".join(lines)
