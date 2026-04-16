from __future__ import annotations

import pytest

from orchestration.timus_doctor import (
    build_timus_doctor_report,
    collect_timus_doctor_report,
    render_timus_doctor_report,
)


def test_build_timus_doctor_report_flags_service_and_runtime_issues() -> None:
    report = build_timus_doctor_report(
        {
            "services": {
                "mcp": {"active": "active", "ok": True, "uptime_seconds": 120.0},
                "dispatcher": {"active": "active", "ok": True, "uptime_seconds": 90.0},
                "qdrant": {"active": "degraded", "ok": False, "detail": "readyz failed", "uptime_seconds": 30.0},
            },
            "local": {
                "qdrant_ready": {"ok": False, "status_code": 503, "error": "readyz failed"},
            },
            "ops": {
                "state": "warn",
                "critical_alerts": 1,
                "warnings": 2,
                "failing_services": 1,
                "unhealthy_providers": 1,
            },
            "ops_gate": {
                "state": "blocked",
                "release_blocked": True,
                "recommended_canary_percent": 0,
            },
            "budget": {
                "state": "warn",
                "message": "budget warn",
                "window_days": 7,
            },
            "mcp_runtime": {
                "state": "startup_grace",
                "reason": "lifecycle:warmup",
                "ready": False,
                "warmup_pending": True,
            },
            "request_runtime": {
                "state": "warn",
                "reason": "recent_failure",
                "chat_requests_total": 4,
                "chat_failed_total": 1,
                "task_failed_total": 1,
            },
            "stability_gate": {
                "state": "hold",
                "circuit_breakers_open": 1,
                "quarantined_incidents": 0,
            },
            "providers": {
                "openai": {"state": "error", "status_code": 401, "latency_ms": 200, "base_url": "https://api.openai.com", "api_configured": True},
                "openrouter": {"state": "ok", "status_code": 200, "latency_ms": 150, "base_url": "https://openrouter.ai", "api_configured": True},
            },
        },
        dispatcher_health={
            "ok": True,
            "status_code": 200,
            "url": "http://127.0.0.1:5010/health",
            "data": {
                "status": "starting",
                "phase": "waiting_for_mcp",
                "ready": False,
                "tools_loaded": False,
                "degraded_reasons": [],
                "mcp": {"reachable": False, "ready": False, "status": "unreachable", "detail": "waiting"},
            },
        },
    )

    assert report["contract_version"] == "timus_doctor_v1"
    assert report["state"] == "critical"
    assert report["ready"] is False
    assert report["summary"]["issue_count"] == len(report["issues"])
    assert report["summary"]["action_count"] == len(report["actions"])
    assert report["stack"]["runtime"]["dispatcher"]["status"] == "starting"
    assert report["stack"]["runtime"]["mcp"]["state"] == "startup_grace"
    assert any(item["component"] == "qdrant" for item in report["issues"])
    assert any(item["component"] == "dispatcher_runtime" for item in report["issues"])
    assert any(item["component"] == "ops_gate" for item in report["issues"])


@pytest.mark.asyncio
async def test_collect_timus_doctor_report_wraps_snapshot_and_probe(monkeypatch) -> None:
    async def _fake_collect_status_snapshot(mcp_base_url=None):
        return {
            "services": {
                "mcp": {"active": "active", "ok": True, "uptime_seconds": 10.0},
                "dispatcher": {"active": "active", "ok": True, "uptime_seconds": 9.0},
            },
            "local": {},
            "ops": {"state": "ok", "critical_alerts": 0, "warnings": 0, "failing_services": 0, "unhealthy_providers": 0},
            "ops_gate": {"state": "pass", "release_blocked": False, "recommended_canary_percent": 0},
            "budget": {"state": "ok", "message": "", "window_days": 7},
            "mcp_runtime": {"state": "healthy", "reason": "steady_state", "ready": True, "warmup_pending": False},
            "request_runtime": {"state": "healthy", "reason": "steady_state", "chat_requests_total": 1, "chat_failed_total": 0, "task_failed_total": 0},
            "stability_gate": {"state": "pass", "circuit_breakers_open": 0, "quarantined_incidents": 0},
            "providers": {},
        }

    monkeypatch.setattr("orchestration.timus_doctor.collect_status_snapshot", _fake_collect_status_snapshot)
    monkeypatch.setattr(
        "orchestration.timus_doctor._build_dispatcher_probe",
        lambda url: {
            "ok": True,
            "status_code": 200,
            "url": url,
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

    report = await collect_timus_doctor_report(dispatcher_health_url="http://127.0.0.1:5010/health")

    assert report["state"] == "ok"
    assert report["ready"] is True
    assert report["stack"]["runtime"]["dispatcher"]["status"] == "healthy"
    assert report["snapshot"]["services"]["mcp"]["ok"] is True


def test_render_timus_doctor_report_contains_core_sections() -> None:
    text = render_timus_doctor_report(
        {
            "state": "warn",
            "ready": False,
            "summary": {
                "ok_service_count": 2,
                "service_count": 3,
                "unhealthy_providers": 1,
                "issue_count": 2,
            },
            "stack": {
                "services": {
                    "mcp": {"active": "active", "ok": True},
                    "dispatcher": {"active": "active", "ok": True},
                    "qdrant": {"active": "degraded", "ok": False, "ready_ok": False},
                },
                "runtime": {
                    "mcp": {"state": "healthy", "reason": "steady_state"},
                    "dispatcher": {"status": "starting", "phase": "waiting_for_mcp", "ready": False},
                },
                "budget": {"state": "warn"},
            },
            "issues": [{"severity": "critical", "component": "qdrant", "detail": "readyz failed"}],
            "actions": ["Pruefe Qdrant-Readyz und Storage/Index-Zustand."],
        }
    )

    assert "Timus Doctor" in text
    assert "State" in text
    assert "Core" in text
    assert "Issues" in text
    assert "Actions" in text
    assert "qdrant" in text
