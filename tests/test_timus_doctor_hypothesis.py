from __future__ import annotations

from hypothesis import given, strategies as st

from orchestration.timus_doctor import build_timus_doctor_report


@given(
    mcp_ok=st.booleans(),
    dispatcher_ok=st.booleans(),
    qdrant_ok=st.booleans(),
    dispatcher_ready=st.booleans(),
    dispatcher_status=st.sampled_from(["healthy", "starting", "degraded", "error"]),
    mcp_state=st.sampled_from(["healthy", "startup_grace", "recovering", "outage"]),
    budget_state=st.sampled_from(["ok", "warn", "soft_limit", "hard_limit"]),
)
def test_hypothesis_build_timus_doctor_report_counts_issues_consistently(
    mcp_ok: bool,
    dispatcher_ok: bool,
    qdrant_ok: bool,
    dispatcher_ready: bool,
    dispatcher_status: str,
    mcp_state: str,
    budget_state: str,
) -> None:
    report = build_timus_doctor_report(
        {
            "services": {
                "mcp": {"active": "active" if mcp_ok else "failed", "ok": mcp_ok, "uptime_seconds": 12.0},
                "dispatcher": {"active": "active" if dispatcher_ok else "failed", "ok": dispatcher_ok, "uptime_seconds": 10.0},
                "qdrant": {"active": "active" if qdrant_ok else "degraded", "ok": qdrant_ok, "uptime_seconds": 8.0},
            },
            "local": {"qdrant_ready": {"ok": qdrant_ok, "status_code": 200 if qdrant_ok else 503, "error": "" if qdrant_ok else "readyz failed"}},
            "ops": {"state": "ok", "critical_alerts": 0, "warnings": 0, "failing_services": 0, "unhealthy_providers": 0},
            "ops_gate": {"state": "pass", "release_blocked": False, "recommended_canary_percent": 0},
            "budget": {"state": budget_state, "message": budget_state, "window_days": 7},
            "mcp_runtime": {"state": mcp_state, "reason": mcp_state, "ready": mcp_state == "healthy", "warmup_pending": False},
            "request_runtime": {"state": "healthy", "reason": "steady_state", "chat_requests_total": 0, "chat_failed_total": 0, "task_failed_total": 0},
            "stability_gate": {"state": "pass", "circuit_breakers_open": 0, "quarantined_incidents": 0},
            "providers": {},
        },
        dispatcher_health={
            "ok": dispatcher_ok,
            "status_code": 200 if dispatcher_ok else 500,
            "url": "http://127.0.0.1:5010/health",
            "data": {
                "status": dispatcher_status,
                "phase": "ready" if dispatcher_ready else "waiting_for_mcp",
                "ready": dispatcher_ready,
                "tools_loaded": dispatcher_ready,
                "degraded_reasons": [],
                "mcp": {"reachable": True, "ready": True, "status": "healthy", "detail": "ready"},
            },
        },
    )

    assert report["summary"]["issue_count"] == len(report["issues"])
    assert report["summary"]["action_count"] == len(report["actions"])
    assert report["state"] in {"ok", "warn", "critical", "unknown"}
