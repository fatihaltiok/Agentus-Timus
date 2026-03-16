"""Operational observability summary built from existing Timus telemetry."""

from __future__ import annotations

import os
from typing import Any, Dict, List

from orchestration.self_stabilization_gate import evaluate_self_stabilization_gate


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def classify_ops_state(
    *,
    failing_services: int,
    unhealthy_providers: int,
    critical_alerts: int,
    warnings: int,
) -> str:
    if max(int(failing_services), int(unhealthy_providers), int(critical_alerts)) > 0:
        return "critical"
    if int(warnings) > 0:
        return "warn"
    return "ok"


def _severity_rank(severity: str) -> int:
    return {"critical": 0, "warn": 1, "info": 2}.get(str(severity or "warn").lower(), 3)


def _error_class_rank(error_class: str) -> int:
    return {
        "availability": 0,
        "budget": 1,
        "reliability": 2,
        "routing": 3,
        "orchestration": 4,
        "latency": 5,
    }.get(_normalized_error_class(error_class), 6)


def _normalized_error_class(raw: str) -> str:
    normalized = str(raw or "").strip().lower()
    if normalized in {"availability", "latency", "reliability", "routing", "budget", "orchestration"}:
        return normalized
    return "reliability"


def _make_alert(
    *,
    kind: str,
    severity: str,
    error_class: str,
    target: str,
    message: str,
    slo: str = "",
    value: float | int = 0,
) -> Dict[str, Any]:
    return {
        "kind": str(kind or "").strip().lower(),
        "severity": str(severity or "warn").strip().lower(),
        "error_class": _normalized_error_class(error_class),
        "target": str(target or "").strip(),
        "message": str(message or "").strip(),
        "slo": str(slo or "").strip(),
        "value": float(value or 0),
    }


def _count_by_error_class(alerts: List[Dict[str, Any]]) -> Dict[str, int]:
    counts = {
        "availability": 0,
        "latency": 0,
        "reliability": 0,
        "routing": 0,
        "budget": 0,
        "orchestration": 0,
    }
    for alert in alerts:
        bucket = _normalized_error_class(alert.get("error_class", "reliability"))
        counts[bucket] = counts.get(bucket, 0) + 1
    return counts


def _build_slo_summary(
    *,
    failing_services: int,
    provider_latency_alerts: List[Dict[str, Any]],
    slow_tool_alerts: List[Dict[str, Any]],
    llm_usage: Dict[str, Any],
    llm_success_threshold: float,
    llm_latency_threshold_ms: int,
    routing_alerts: List[Dict[str, Any]],
    tool_failure_alerts: List[Dict[str, Any]],
    budget_state: str,
) -> Dict[str, Any]:
    llm_total_requests = int((llm_usage or {}).get("total_requests", 0) or 0)
    llm_success_rate = float((llm_usage or {}).get("success_rate", 0.0) or 0.0)
    llm_avg_latency_ms = float((llm_usage or {}).get("avg_latency_ms", 0.0) or 0.0)

    items = [
        {
            "name": "service_availability",
            "target": "core",
            "breached": failing_services > 0,
            "message": f"{failing_services} failing services" if failing_services > 0 else "services healthy",
        },
        {
            "name": "provider_latency",
            "target": "providers",
            "breached": len(provider_latency_alerts) > 0,
            "message": (
                f"{len(provider_latency_alerts)} slow providers"
                if provider_latency_alerts
                else "provider latency within threshold"
            ),
        },
        {
            "name": "tool_reliability",
            "target": "tools",
            "breached": len(tool_failure_alerts) > 0,
            "message": (
                f"{len(tool_failure_alerts)} tool reliability outliers"
                if tool_failure_alerts
                else "tool success within threshold"
            ),
        },
        {
            "name": "tool_latency",
            "target": "tools",
            "breached": len(slow_tool_alerts) > 0,
            "message": (
                f"{len(slow_tool_alerts)} slow tools"
                if slow_tool_alerts
                else "tool latency within threshold"
            ),
        },
        {
            "name": "routing_confidence",
            "target": "routing",
            "breached": len(routing_alerts) > 0,
            "message": (
                f"{len(routing_alerts)} routing outliers"
                if routing_alerts
                else "routing confidence within threshold"
            ),
        },
        {
            "name": "llm_success_rate",
            "target": "llm",
            "breached": llm_total_requests >= 3 and llm_success_rate < llm_success_threshold,
            "message": (
                f"LLM success {llm_success_rate:.2f} < {llm_success_threshold:.2f}"
                if llm_total_requests >= 3 and llm_success_rate < llm_success_threshold
                else "LLM success within threshold"
            ),
        },
        {
            "name": "llm_latency",
            "target": "llm",
            "breached": llm_total_requests >= 3 and llm_avg_latency_ms >= llm_latency_threshold_ms,
            "message": (
                f"LLM avg {llm_avg_latency_ms:.0f} ms >= {llm_latency_threshold_ms} ms"
                if llm_total_requests >= 3 and llm_avg_latency_ms >= llm_latency_threshold_ms
                else "LLM latency within threshold"
            ),
        },
        {
            "name": "budget",
            "target": "budget",
            "breached": budget_state in {"warn", "soft_limit", "hard_limit"},
            "message": (
                f"budget {budget_state}"
                if budget_state in {"warn", "soft_limit", "hard_limit"}
                else "budget healthy"
            ),
        },
    ]
    return {
        "breached": sum(1 for item in items if item["breached"]),
        "healthy": sum(1 for item in items if not item["breached"]),
        "items": items,
    }


def build_ops_observability_summary(
    *,
    services: Dict[str, Dict[str, Any]],
    providers: Dict[str, Dict[str, Any]],
    tool_stats: List[dict],
    routing_stats: Dict[str, Any],
    llm_usage: Dict[str, Any],
    budget: Dict[str, Any],
    recall_stats: Dict[str, Any] | None = None,
    self_healing: Dict[str, Any] | None = None,
    hardening: Dict[str, Any] | None = None,
    limit: int = 5,
) -> Dict[str, Any]:
    """Combines service/provider/analytics signals into one ops summary."""
    safe_limit = max(1, min(20, int(limit)))
    tool_failure_threshold = _env_float("OPS_TOOL_FAILURE_THRESHOLD", 0.80)
    tool_slow_ms = _env_int("OPS_TOOL_SLOW_MS", 3000)
    provider_slow_ms = _env_int("OPS_PROVIDER_SLOW_MS", 2500)
    routing_conf_threshold = _env_float("OPS_ROUTING_LOW_CONF_THRESHOLD", 0.60)
    routing_success_threshold = _env_float("OPS_ROUTING_SUCCESS_THRESHOLD", 0.70)
    llm_success_threshold = _env_float("OPS_LLM_SUCCESS_THRESHOLD", 0.95)
    llm_latency_threshold_ms = _env_int("OPS_LLM_LATENCY_MS", 2000)
    recall_none_threshold = _env_float("OPS_RECALL_NONE_THRESHOLD", 0.20)
    recall_summary_threshold = _env_float("OPS_RECALL_SUMMARY_THRESHOLD", 0.35)
    recall_distance_threshold = _env_float("OPS_RECALL_DISTANCE_THRESHOLD", 0.20)

    service_alerts: List[Dict[str, Any]] = []
    for service_name, info in (services or {}).items():
        if not bool((info or {}).get("ok", False)):
            service_alerts.append(
                _make_alert(
                    kind="service",
                    severity="critical",
                    error_class="availability",
                    target=service_name,
                    message=f"Service {service_name} ist {info.get('active', 'unknown')}",
                    slo="service_availability",
                    value=1,
                )
            )

    provider_state_alerts: List[Dict[str, Any]] = []
    provider_latency_alerts: List[Dict[str, Any]] = []
    for provider_name, info in (providers or {}).items():
        state = str((info or {}).get("state", "unknown"))
        if state in {"error", "auth_error"}:
            provider_state_alerts.append(
                _make_alert(
                    kind="provider",
                    severity="critical" if state == "auth_error" else "warn",
                    error_class="availability",
                    target=provider_name,
                    message=f"Provider {provider_name}: {state}",
                    slo="service_availability",
                    value=1,
                )
            )
        latency_ms = float((info or {}).get("latency_ms", 0.0) or 0.0)
        if state == "ok" and latency_ms >= provider_slow_ms:
            provider_latency_alerts.append(
                _make_alert(
                    kind="provider",
                    severity="warn",
                    error_class="latency",
                    target=provider_name,
                    message=f"Provider {provider_name}: {latency_ms:.0f} ms",
                    slo="provider_latency",
                    value=latency_ms,
                )
            )

    tool_failure_alerts: List[Dict[str, Any]] = []
    slow_tool_alerts: List[Dict[str, Any]] = []
    for row in tool_stats[: max(len(tool_stats), safe_limit)]:
        total = int(row.get("total", 0) or 0)
        success_rate = float(row.get("success_rate", 1.0) or 0.0)
        avg_duration_ms = float(row.get("avg_duration_ms", 0.0) or 0.0)
        if total >= 3 and success_rate < tool_failure_threshold:
            tool_failure_alerts.append(
                _make_alert(
                    kind="tool",
                    severity="critical" if success_rate < 0.5 else "warn",
                    error_class="reliability",
                    target=row.get("tool_name", ""),
                    message=(
                        f"Tool {row.get('tool_name', '?')} @ {row.get('agent', '?')}: "
                        f"{success_rate:.2f} success"
                    ),
                    slo="tool_reliability",
                    value=success_rate,
                )
            )
        elif total >= 3 and avg_duration_ms >= tool_slow_ms:
            slow_tool_alerts.append(
                _make_alert(
                    kind="tool",
                    severity="warn",
                    error_class="latency",
                    target=row.get("tool_name", ""),
                    message=(
                        f"Tool {row.get('tool_name', '?')} @ {row.get('agent', '?')}: "
                        f"{avg_duration_ms:.0f} ms avg"
                    ),
                    slo="tool_latency",
                    value=avg_duration_ms,
                )
            )

    routing_alerts: List[Dict[str, Any]] = []
    for agent_name, info in ((routing_stats or {}).get("by_agent", {}) or {}).items():
        total = int((info or {}).get("total", 0) or 0)
        avg_conf = float((info or {}).get("avg_confidence", 1.0) or 0.0)
        success_rate = float((info or {}).get("success_rate", 1.0) or 0.0)
        if total >= 3 and avg_conf < routing_conf_threshold:
            routing_alerts.append(
                _make_alert(
                    kind="routing",
                    severity="warn",
                    error_class="routing",
                    target=agent_name,
                    message=f"Routing {agent_name}: conf {avg_conf:.2f}",
                    slo="routing_confidence",
                    value=avg_conf,
                )
            )
        if total >= 3 and success_rate < routing_success_threshold:
            routing_alerts.append(
                _make_alert(
                    kind="routing",
                    severity="critical" if success_rate < 0.5 else "warn",
                    error_class="orchestration",
                    target=agent_name,
                    message=f"Routing {agent_name}: success {success_rate:.2f}",
                    slo="routing_confidence",
                    value=success_rate,
                )
            )

    llm_alerts: List[Dict[str, Any]] = []
    llm_success_rate = float((llm_usage or {}).get("success_rate", 1.0) or 0.0)
    llm_total_requests = int((llm_usage or {}).get("total_requests", 0) or 0)
    llm_avg_latency_ms = float((llm_usage or {}).get("avg_latency_ms", 0.0) or 0.0)
    if llm_total_requests >= 3 and llm_success_rate < llm_success_threshold:
        llm_alerts.append(
            _make_alert(
                kind="llm_usage",
                severity="warn",
                error_class="reliability",
                target="llm",
                message=f"LLM success_rate {llm_success_rate:.2f}",
                slo="llm_success_rate",
                value=llm_success_rate,
            )
        )
    if llm_total_requests >= 3 and llm_avg_latency_ms >= llm_latency_threshold_ms:
        llm_alerts.append(
            _make_alert(
                kind="llm_usage",
                severity="warn",
                error_class="latency",
                target="llm",
                message=f"LLM avg latency {llm_avg_latency_ms:.0f} ms",
                slo="llm_latency",
                value=llm_avg_latency_ms,
            )
        )

    budget_alerts: List[Dict[str, Any]] = []
    budget_state = str((budget or {}).get("state", "ok") or "ok")
    if budget_state in {"hard_limit", "soft_limit", "warn"}:
        budget_alerts.append(
            _make_alert(
                kind="budget",
                severity="critical" if budget_state == "hard_limit" else "warn",
                error_class="budget",
                target="budget",
                message=str((budget or {}).get("message") or f"budget {budget_state}"),
                slo="budget",
                value=1,
            )
        )

    recall_alerts: List[Dict[str, Any]] = []
    recall_total_queries = int((recall_stats or {}).get("total_queries", 0) or 0)
    recall_none_rate = float((recall_stats or {}).get("none_rate", 0.0) or 0.0)
    recall_summary_rate = float((recall_stats or {}).get("summary_fallback_rate", 0.0) or 0.0)
    recall_top_distance = float((recall_stats or {}).get("avg_top_distance", 0.0) or 0.0)
    if recall_total_queries >= 3 and recall_none_rate >= recall_none_threshold:
        recall_alerts.append(
            _make_alert(
                kind="conversation_recall",
                severity="critical" if recall_none_rate >= 0.35 else "warn",
                error_class="orchestration",
                target="conversation_recall",
                message=f"Recall none_rate {recall_none_rate:.2f}",
                slo="conversation_recall",
                value=recall_none_rate,
            )
        )
    if recall_total_queries >= 3 and recall_summary_rate >= recall_summary_threshold:
        recall_alerts.append(
            _make_alert(
                kind="conversation_recall",
                severity="warn",
                error_class="orchestration",
                target="conversation_recall",
                message=f"Recall summary_fallback {recall_summary_rate:.2f}",
                slo="conversation_recall",
                value=recall_summary_rate,
            )
        )
    if recall_total_queries >= 3 and recall_top_distance >= recall_distance_threshold:
        recall_alerts.append(
            _make_alert(
                kind="conversation_recall",
                severity="warn",
                error_class="routing",
                target="conversation_recall",
                message=f"Recall avg distance {recall_top_distance:.2f}",
                slo="conversation_recall",
                value=recall_top_distance,
            )
        )

    stabilization_gate = evaluate_self_stabilization_gate(self_healing or {})
    self_healing_alerts: List[Dict[str, Any]] = []
    if stabilization_gate.get("state") == "blocked":
        self_healing_alerts.append(
            _make_alert(
                kind="self_healing",
                severity="critical",
                error_class="orchestration",
                target="self_healing",
                message=(
                    "Self-Healing gate blocked: "
                    f"degrade={stabilization_gate.get('degrade_mode', 'unknown')} | "
                    f"breakers={stabilization_gate.get('circuit_breakers_open', 0)} | "
                    f"open={stabilization_gate.get('open_incidents', 0)}"
                ),
                slo="service_availability",
                value=int(stabilization_gate.get("open_incidents", 0) or 0),
            )
        )
    elif stabilization_gate.get("state") == "warn":
        self_healing_alerts.append(
            _make_alert(
                kind="self_healing",
                severity="warn",
                error_class="orchestration",
                target="self_healing",
                message=(
                    "Self-Healing gate warn: "
                    f"degrade={stabilization_gate.get('degrade_mode', 'unknown')} | "
                    f"quarantine={stabilization_gate.get('quarantined_incidents', 0)} | "
                    f"cooldown={stabilization_gate.get('cooldown_incidents', 0)} | "
                    f"patterns={stabilization_gate.get('known_bad_patterns', 0)}"
                ),
                slo="service_availability",
                value=int(stabilization_gate.get("open_incidents", 0) or 0),
            )
        )

    hardening_alerts: List[Dict[str, Any]] = []
    hardening_state = str((hardening or {}).get("state", "unknown") or "unknown")
    hardening_last_status = str((hardening or {}).get("last_status", "") or "")
    hardening_last_event = str((hardening or {}).get("last_event", "") or "")
    hardening_last_pattern = str((hardening or {}).get("last_pattern_name", "") or "")
    hardening_last_reason = str((hardening or {}).get("last_reason", "") or "")
    hardening_effective_mode = str((hardening or {}).get("last_pattern_effective_fix_mode", "") or "")
    hardening_freeze_active = bool((hardening or {}).get("last_pattern_freeze_active"))
    hardening_verification_status = str((hardening or {}).get("last_verification_status", "") or "")
    if hardening_last_status in {"error", "rolled_back"}:
        hardening_alerts.append(
            _make_alert(
                kind="self_hardening",
                severity="critical" if hardening_last_status == "error" else "warn",
                error_class="orchestration",
                target="m18_hardening",
                message=(
                    f"M18 {hardening_last_event or 'event'}: "
                    f"{hardening_last_status} @ {hardening_last_pattern or 'unknown'}"
                    + (f" | {hardening_last_reason}" if hardening_last_reason else "")
                ),
                slo="hardening_runtime",
                value=1,
            )
        )
    elif hardening_verification_status == "error":
        hardening_alerts.append(
            _make_alert(
                kind="self_hardening",
                severity="warn",
                error_class="orchestration",
                target="m18_hardening",
                message=(
                    f"M18 verification error @ {hardening_last_pattern or 'unknown'}"
                    + (f" | {hardening_last_reason}" if hardening_last_reason else "")
                ),
                slo="hardening_runtime",
                value=1,
            )
        )
    elif hardening_effective_mode == "human_only" or hardening_freeze_active:
        hardening_alerts.append(
            _make_alert(
                kind="self_hardening",
                severity="warn",
                error_class="orchestration",
                target="m18_hardening",
                message=(
                    f"M18 escalated to human_only @ {hardening_last_pattern or 'unknown'}"
                    + (f" | {hardening_last_reason}" if hardening_last_reason else "")
                ),
                slo="hardening_runtime",
                value=1,
            )
        )
    elif hardening_last_status in {"blocked", "pending_approval", "skipped"}:
        hardening_alerts.append(
            _make_alert(
                kind="self_hardening",
                severity="warn",
                error_class="orchestration",
                target="m18_hardening",
                message=(
                    f"M18 {hardening_last_event or 'event'}: "
                    f"{hardening_last_status} @ {hardening_last_pattern or 'unknown'}"
                ),
                slo="hardening_runtime",
                value=1,
            )
        )

    all_alerts = (
        service_alerts
        + provider_state_alerts
        + provider_latency_alerts
        + budget_alerts
        + self_healing_alerts
        + hardening_alerts
        + recall_alerts
        + tool_failure_alerts
        + slow_tool_alerts
        + routing_alerts
        + llm_alerts
    )
    alerts = sorted(
        all_alerts,
        key=lambda alert: (
            _severity_rank(str(alert.get("severity", "warn"))),
            _error_class_rank(str(alert.get("error_class", "reliability"))),
            -float(alert.get("value", 0.0) or 0.0),
            str(alert.get("message", "")),
        ),
    )[:safe_limit]

    critical_alerts = sum(1 for alert in all_alerts if alert.get("severity") == "critical")
    warnings = sum(1 for alert in all_alerts if alert.get("severity") != "critical")
    failing_services = len(service_alerts)
    unhealthy_providers = len(provider_state_alerts)
    error_classes = _count_by_error_class(all_alerts)

    state = classify_ops_state(
        failing_services=failing_services,
        unhealthy_providers=unhealthy_providers,
        critical_alerts=critical_alerts,
        warnings=warnings,
    )

    top_outliers = sorted(
        all_alerts,
        key=lambda alert: (
            _severity_rank(str(alert.get("severity", "warn"))),
            -float(alert.get("value", 0.0) or 0.0),
            str(alert.get("message", "")),
        ),
    )[:safe_limit]
    slo = _build_slo_summary(
        failing_services=failing_services,
        provider_latency_alerts=provider_latency_alerts,
        slow_tool_alerts=slow_tool_alerts,
        llm_usage=llm_usage,
        llm_success_threshold=llm_success_threshold,
        llm_latency_threshold_ms=llm_latency_threshold_ms,
        routing_alerts=routing_alerts,
        tool_failure_alerts=tool_failure_alerts,
        budget_state=budget_state,
    )

    return {
        "state": state,
        "critical_alerts": critical_alerts,
        "warnings": warnings,
        "failing_services": failing_services,
        "unhealthy_providers": unhealthy_providers,
        "alerts": alerts,
        "top_tool_failures": tool_failure_alerts[:safe_limit],
        "top_routing_risks": routing_alerts[:safe_limit],
        "top_recall_risks": recall_alerts[:safe_limit],
        "top_outliers": top_outliers,
        "error_classes": error_classes,
        "slo": slo,
        "llm_success_rate": llm_success_rate,
        "llm_avg_latency_ms": llm_avg_latency_ms,
        "recall": recall_stats or {},
        "hardening": hardening
        or {
            "state": hardening_state,
            "last_event": hardening_last_event,
            "last_status": hardening_last_status,
            "last_pattern_name": hardening_last_pattern,
            "last_reason": hardening_last_reason,
        },
        "self_stabilization_gate": stabilization_gate,
    }
