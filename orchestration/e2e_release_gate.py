"""Escalation and release/canary gating based on the E2E regression matrix."""

from __future__ import annotations

from typing import Any, Dict, List


def evaluate_e2e_release_gate(
    matrix: Dict[str, Any],
    *,
    current_canary_percent: int = 0,
) -> Dict[str, Any]:
    summary = (matrix or {}).get("summary", {}) or {}
    flows = list((matrix or {}).get("flows", []) or [])
    safe_canary = max(0, min(100, int(current_canary_percent or 0)))

    blocking_flows = [
        flow.get("flow", "")
        for flow in flows
        if bool(flow.get("blocking", False)) and flow.get("status") == "fail"
    ]
    warning_flows = [
        flow.get("flow", "")
        for flow in flows
        if flow.get("status") == "warn"
    ]
    failed_flows = [
        flow.get("flow", "")
        for flow in flows
        if flow.get("status") == "fail"
    ]

    blocking_failed = int(summary.get("blocking_failed", 0) or 0)
    failed = int(summary.get("failed", 0) or 0)
    warned = int(summary.get("warned", 0) or 0)

    if blocking_failed > 0:
        return {
            "state": "blocked",
            "alert_severity": "critical",
            "release_blocked": True,
            "canary_blocked": True,
            "canary_deferred": True,
            "recommended_canary_percent": 0,
            "reason": "blocking_e2e_failures",
            "blocking_flows": blocking_flows,
            "failed_flows": failed_flows,
            "warning_flows": warning_flows,
        }

    if failed > 0 or warned > 0:
        return {
            "state": "warn",
            "alert_severity": "warn",
            "release_blocked": False,
            "canary_blocked": False,
            "canary_deferred": True,
            "recommended_canary_percent": safe_canary,
            "reason": "non_blocking_e2e_drift",
            "blocking_flows": blocking_flows,
            "failed_flows": failed_flows,
            "warning_flows": warning_flows,
        }

    return {
        "state": "pass",
        "alert_severity": "info",
        "release_blocked": False,
        "canary_blocked": False,
        "canary_deferred": False,
        "recommended_canary_percent": safe_canary,
        "reason": "all_core_flows_green",
        "blocking_flows": [],
        "failed_flows": [],
        "warning_flows": [],
    }


def build_e2e_gate_alert_message(
    matrix: Dict[str, Any],
    decision: Dict[str, Any],
) -> str:
    summary = (matrix or {}).get("summary", {}) or {}
    emoji = {
        "blocked": "🔴",
        "warn": "🟠",
        "pass": "🟢",
    }.get(str(decision.get("state", "warn")).lower(), "⚪")
    lines = [
        f"{emoji} *E2E Release Gate*",
        (
            f"State {decision.get('state', 'unknown')} | "
            f"ReleaseBlocked {decision.get('release_blocked', False)} | "
            f"CanaryDeferred {decision.get('canary_deferred', False)} | "
            f"RecommendedCanary {decision.get('recommended_canary_percent', 0)}%"
        ),
        (
            f"Summary total={summary.get('total', 0)} passed={summary.get('passed', 0)} "
            f"warned={summary.get('warned', 0)} failed={summary.get('failed', 0)} "
            f"blocking_failed={summary.get('blocking_failed', 0)}"
        ),
    ]
    if decision.get("blocking_flows"):
        lines.append(f"Blocking: {', '.join(decision.get('blocking_flows', []))}")
    if decision.get("failed_flows"):
        lines.append(f"Failed: {', '.join(decision.get('failed_flows', []))}")
    if decision.get("warning_flows"):
        lines.append(f"Warnings: {', '.join(decision.get('warning_flows', []))}")
    return "\n".join(lines)
