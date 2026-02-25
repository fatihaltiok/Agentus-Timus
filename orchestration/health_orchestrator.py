"""
orchestration/health_orchestrator.py

M3.3 Health-Orchestrator:
- Priorisierte Recovery-Routing-Entscheidungen
- Degrade-Mode-Berechnung (normal | degraded | emergency)
"""

from __future__ import annotations

import os
from datetime import datetime
from typing import Any, Dict, Optional

from orchestration.task_queue import Priority, SelfHealingDegradeMode


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)).strip())
    except Exception:
        return default


def _normalize_severity(severity: str) -> str:
    raw = (severity or "").strip().lower()
    if raw in {"critical", "high", "medium", "low"}:
        return raw
    return "medium"


class HealthOrchestrator:
    """Koordiniert Routing und Degrade-Mode fuer Self-Healing."""

    def __init__(self, *, now_provider=None):
        self._now = now_provider or datetime.now

    def route_recovery(
        self,
        *,
        component: str,
        signal: str,
        severity: str,
        default_target_agent: str,
        default_priority: int,
        default_template: str,
    ) -> Dict[str, Any]:
        comp = (component or "").strip().lower()
        sig = (signal or "").strip().lower()
        sev = _normalize_severity(severity)

        if comp in {"mcp", "system"}:
            target_agent = "system"
        elif comp in {"queue", "providers"}:
            target_agent = "meta"
        else:
            target_agent = (default_target_agent or "meta").strip() or "meta"

        template_map = {
            ("mcp", "mcp_health"): "mcp_recovery",
            ("system", "system_pressure"): "system_pressure_relief",
            ("queue", "pending_backlog"): "queue_backlog_relief",
            ("providers", "task_failure_spike"): "provider_failover_diagnostics",
        }
        playbook_template = template_map.get((comp, sig), default_template)

        if sev in {"critical", "high"}:
            priority = Priority.CRITICAL if comp in {"mcp", "providers"} else Priority.HIGH
            lane = "self_healing_fast_lane"
            route_class = "expedite"
        elif sev == "medium":
            priority = min(int(default_priority), int(Priority.HIGH))
            lane = "self_healing_standard_lane"
            route_class = "standard"
        else:
            priority = max(int(default_priority), int(Priority.NORMAL))
            lane = "self_healing_observe_lane"
            route_class = "observe"

        return {
            "target_agent": target_agent,
            "priority": int(priority),
            "playbook_template": playbook_template,
            "lane": lane,
            "route_class": route_class,
            "route_reason": f"{comp}:{sig}:{sev}",
        }

    def evaluate_degrade_mode(
        self,
        *,
        metrics: Dict[str, Any],
        signals: Dict[str, Any],
        previous_mode: Optional[str] = None,
    ) -> Dict[str, Any]:
        open_incidents = int(metrics.get("open_incidents", 0) or 0)
        breakers_open = int(metrics.get("circuit_breakers_open", 0) or 0)
        open_by_severity = metrics.get("open_by_severity", {}) or {}
        high_open = int(open_by_severity.get("high", 0) or 0) + int(open_by_severity.get("critical", 0) or 0)

        unhealthy_signals = []
        for key, value in (signals or {}).items():
            payload = value if isinstance(value, dict) else {}
            if not bool(payload.get("ok", False)):
                unhealthy_signals.append(str(key))

        degraded_open_threshold = max(1, _env_int("AUTONOMY_SELF_HEALING_DEGRADED_OPEN_THRESHOLD", 2))
        degraded_breaker_threshold = max(1, _env_int("AUTONOMY_SELF_HEALING_DEGRADED_BREAKERS_OPEN_THRESHOLD", 1))
        emergency_open_threshold = max(1, _env_int("AUTONOMY_SELF_HEALING_EMERGENCY_OPEN_THRESHOLD", 4))
        emergency_breaker_threshold = max(1, _env_int("AUTONOMY_SELF_HEALING_EMERGENCY_BREAKERS_OPEN_THRESHOLD", 2))
        emergency_high_threshold = max(1, _env_int("AUTONOMY_SELF_HEALING_EMERGENCY_HIGH_SEVERITY_THRESHOLD", 2))

        reasons = []
        mode = SelfHealingDegradeMode.NORMAL
        if (
            open_incidents >= emergency_open_threshold
            or breakers_open >= emergency_breaker_threshold
            or high_open >= emergency_high_threshold
            or len(unhealthy_signals) >= 3
        ):
            mode = SelfHealingDegradeMode.EMERGENCY
            reasons.append("emergency_threshold_exceeded")
        elif (
            open_incidents >= degraded_open_threshold
            or breakers_open >= degraded_breaker_threshold
            or len(unhealthy_signals) >= 1
        ):
            mode = SelfHealingDegradeMode.DEGRADED
            reasons.append("degraded_threshold_exceeded")
        else:
            reasons.append("all_signals_nominal")

        if mode == SelfHealingDegradeMode.NORMAL and (previous_mode or "") == SelfHealingDegradeMode.EMERGENCY:
            if open_incidents > 0 or breakers_open > 0:
                mode = SelfHealingDegradeMode.DEGRADED
                reasons = ["post_emergency_stabilization"]

        score = float((open_incidents * 1.0) + (breakers_open * 2.0) + (high_open * 1.5) + len(unhealthy_signals))

        return {
            "mode": mode,
            "reason": reasons[0],
            "reason_codes": reasons,
            "score": round(score, 2),
            "observed_at": self._now().isoformat(),
            "inputs": {
                "open_incidents": open_incidents,
                "breakers_open": breakers_open,
                "high_severity_open": high_open,
                "unhealthy_signals": unhealthy_signals,
            },
        }
