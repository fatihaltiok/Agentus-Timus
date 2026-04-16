from __future__ import annotations

import deal

from orchestration.timus_doctor import build_timus_doctor_report


@deal.post(lambda r: r == 1)
def _contract_timus_doctor_marks_unready_when_mcp_service_is_down() -> int:
    report = build_timus_doctor_report(
        {
            "services": {
                "mcp": {"active": "failed", "ok": False, "uptime_seconds": 0.0},
                "dispatcher": {"active": "active", "ok": True, "uptime_seconds": 10.0},
            },
            "local": {},
            "ops": {"state": "warn", "critical_alerts": 0, "warnings": 1, "failing_services": 1, "unhealthy_providers": 0},
            "ops_gate": {"state": "pass", "release_blocked": False, "recommended_canary_percent": 0},
            "budget": {"state": "ok", "message": "", "window_days": 7},
            "mcp_runtime": {"state": "outage", "reason": "mcp_service_or_health_unhealthy", "ready": False, "warmup_pending": False},
            "request_runtime": {"state": "healthy", "reason": "steady_state", "chat_requests_total": 0, "chat_failed_total": 0, "task_failed_total": 0},
            "stability_gate": {"state": "pass", "circuit_breakers_open": 0, "quarantined_incidents": 0},
            "providers": {},
        },
        dispatcher_health={
            "ok": True,
            "status_code": 200,
            "url": "http://127.0.0.1:5010/health",
            "data": {
                "status": "healthy",
                "phase": "ready",
                "ready": True,
                "tools_loaded": True,
                "degraded_reasons": [],
                "mcp": {"reachable": True, "ready": True, "status": "healthy", "detail": "ready"},
            },
        },
    )
    return 1 if (not report["ready"] and report["state"] == "critical") else 0


@deal.post(lambda r: r == 1)
def _contract_timus_doctor_issue_count_matches_items_crosshair() -> int:
    report = build_timus_doctor_report(
        {
            "services": {
                "mcp": {"active": "active", "ok": True, "uptime_seconds": 10.0},
                "dispatcher": {"active": "active", "ok": True, "uptime_seconds": 10.0},
            },
            "local": {},
            "ops": {"state": "ok", "critical_alerts": 0, "warnings": 0, "failing_services": 0, "unhealthy_providers": 0},
            "ops_gate": {"state": "pass", "release_blocked": False, "recommended_canary_percent": 0},
            "budget": {"state": "warn", "message": "budget warn", "window_days": 7},
            "mcp_runtime": {"state": "healthy", "reason": "steady_state", "ready": True, "warmup_pending": False},
            "request_runtime": {"state": "healthy", "reason": "steady_state", "chat_requests_total": 0, "chat_failed_total": 0, "task_failed_total": 0},
            "stability_gate": {"state": "pass", "circuit_breakers_open": 0, "quarantined_incidents": 0},
            "providers": {},
        },
        dispatcher_health={
            "ok": True,
            "status_code": 200,
            "url": "http://127.0.0.1:5010/health",
            "data": {
                "status": "healthy",
                "phase": "ready",
                "ready": True,
                "tools_loaded": True,
                "degraded_reasons": [],
                "mcp": {"reachable": True, "ready": True, "status": "healthy", "detail": "ready"},
            },
        },
    )
    return 1 if report["summary"]["issue_count"] == len(report["issues"]) else 0
