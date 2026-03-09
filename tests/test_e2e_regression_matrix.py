from __future__ import annotations

from types import SimpleNamespace

import pytest

from orchestration.e2e_regression_matrix import build_e2e_regression_matrix
from tools.self_improvement_tool.tool import get_e2e_regression_matrix


def test_build_e2e_regression_matrix_marks_all_core_flows_pass():
    matrix = build_e2e_regression_matrix(
        snapshot={
            "services": {
                "mcp": {"ok": True, "active": "active", "uptime_seconds": 120},
                "dispatcher": {"ok": True, "active": "active", "uptime_seconds": 120},
            },
            "local": {
                "mcp_health": {"data": {"status": "healthy"}, "latency_ms": 220},
                "agent_status": {"ok": True},
                "autonomy_health": {"ok": True},
            },
            "ops": {"state": "ok"},
            "restart": {"exists": True, "status": "completed", "phase": "done", "age_seconds": 10},
        },
        email_status={
            "success": True,
            "authenticated": True,
            "backend": "resend",
        },
        browser_eval_results=[
            {"name": "booking_search", "passed": True},
            {"name": "login_flow", "passed": True},
            {"name": "contact_form", "passed": True},
        ],
    )

    assert matrix["summary"]["overall"] == "pass"
    assert matrix["summary"]["blocking_failed"] == 0
    flows = {flow["flow"]: flow for flow in matrix["flows"]}
    assert flows["telegram_status"]["status"] == "pass"
    assert flows["email_backend"]["status"] == "pass"
    assert flows["restart_recovery"]["status"] == "pass"
    assert flows["meta_visual_browser"]["status"] == "pass"


def test_build_e2e_regression_matrix_detects_blocking_failure():
    matrix = build_e2e_regression_matrix(
        snapshot={
            "services": {
                "mcp": {"ok": False, "active": "failed", "uptime_seconds": 500},
                "dispatcher": {"ok": True, "active": "active", "uptime_seconds": 500},
            },
            "local": {
                "mcp_health": {"data": {"status": "down"}},
                "agent_status": {"ok": False},
                "autonomy_health": {"ok": False},
            },
            "ops": {"state": "critical"},
            "restart": {"exists": True, "status": "failed", "phase": "shutdown", "age_seconds": 40},
        },
        email_status={
            "success": False,
            "authenticated": False,
            "backend": "resend",
            "error": "missing key",
        },
        browser_eval_results=[
            {"name": "booking_search", "passed": True},
            {"name": "login_flow", "passed": False},
        ],
    )

    assert matrix["summary"]["overall"] == "fail"
    assert matrix["summary"]["blocking_failed"] >= 1


def test_build_e2e_regression_matrix_warns_on_drift_signals():
    matrix = build_e2e_regression_matrix(
        snapshot={
            "services": {
                "mcp": {"ok": True, "active": "active", "uptime_seconds": 180},
                "dispatcher": {"ok": True, "active": "active", "uptime_seconds": 180},
            },
            "local": {
                "mcp_health": {"data": {"status": "healthy"}, "latency_ms": 2100},
                "agent_status": {"ok": True},
                "autonomy_health": {"ok": False},
            },
            "ops": {"state": "warn", "warnings": 2},
            "restart": {"exists": True, "status": "completed", "phase": "done", "age_seconds": 20},
        },
        email_status={
            "success": True,
            "authenticated": True,
            "backend": "resend",
        },
        browser_eval_results=[
            {"name": "booking_search", "passed": True},
            {"name": "login_flow", "passed": True},
            {"name": "contact_form", "passed": True},
        ],
    )

    flows = {flow["flow"]: flow for flow in matrix["flows"]}
    assert matrix["summary"]["overall"] == "warn"
    assert flows["telegram_status"]["status"] == "warn"
    assert flows["restart_recovery"]["status"] == "warn"


def test_build_e2e_regression_matrix_warns_during_startup_grace():
    matrix = build_e2e_regression_matrix(
        snapshot={
            "services": {
                "mcp": {"ok": True, "active": "active", "uptime_seconds": 9},
                "dispatcher": {"ok": True, "active": "active", "uptime_seconds": 11},
            },
            "local": {
                "mcp_health": {"data": {"status": "starting"}, "latency_ms": 40},
                "agent_status": {"ok": False},
                "autonomy_health": {"ok": False},
            },
            "ops": {"state": "ok"},
            "restart": {"exists": True, "status": "running", "phase": "launcher", "age_seconds": 12},
        },
        email_status={
            "success": True,
            "authenticated": True,
            "backend": "resend",
        },
        browser_eval_results=[
            {"name": "booking_search", "passed": True},
            {"name": "login_flow", "passed": True},
        ],
    )

    flows = {flow["flow"]: flow for flow in matrix["flows"]}
    assert matrix["summary"]["overall"] == "warn"
    assert flows["telegram_status"]["status"] == "warn"
    assert flows["restart_recovery"]["status"] == "warn"
    assert flows["telegram_status"]["evidence"]["startup_grace"] is True


def test_build_e2e_regression_matrix_warns_on_browser_eval_blindness():
    matrix = build_e2e_regression_matrix(
        snapshot={
            "services": {
                "mcp": {"ok": True, "active": "active", "uptime_seconds": 300},
                "dispatcher": {"ok": True, "active": "active", "uptime_seconds": 300},
            },
            "local": {
                "mcp_health": {"data": {"status": "healthy"}, "latency_ms": 140},
                "agent_status": {"ok": True},
                "autonomy_health": {"ok": True},
            },
            "ops": {"state": "ok"},
            "restart": {"exists": True, "status": "completed", "phase": "done", "age_seconds": 90},
        },
        email_status={
            "success": True,
            "authenticated": True,
            "backend": "resend",
        },
        browser_eval_results=[],
    )

    flows = {flow["flow"]: flow for flow in matrix["flows"]}
    assert matrix["summary"]["overall"] == "warn"
    assert flows["meta_visual_browser"]["status"] == "warn"
    assert flows["meta_visual_browser"]["evidence"]["blind"] is True


def test_build_e2e_regression_matrix_warns_on_stale_restart_status():
    matrix = build_e2e_regression_matrix(
        snapshot={
            "services": {
                "mcp": {"ok": True, "active": "active", "uptime_seconds": 600},
                "dispatcher": {"ok": True, "active": "active", "uptime_seconds": 600},
            },
            "local": {
                "mcp_health": {"data": {"status": "healthy"}, "latency_ms": 120},
                "agent_status": {"ok": True},
                "autonomy_health": {"ok": True},
            },
            "ops": {"state": "ok"},
            "restart": {"exists": True, "status": "running", "phase": "preflight", "age_seconds": 2400},
        },
        email_status={
            "success": True,
            "authenticated": True,
            "backend": "resend",
        },
        browser_eval_results=[
            {"name": "booking_search", "passed": True},
            {"name": "login_flow", "passed": True},
        ],
    )

    flows = {flow["flow"]: flow for flow in matrix["flows"]}
    assert matrix["summary"]["overall"] == "warn"
    assert flows["restart_recovery"]["status"] == "warn"
    assert flows["restart_recovery"]["evidence"]["restart_status"]["status"] == "running"


@pytest.mark.asyncio
async def test_get_e2e_regression_matrix_returns_matrix(monkeypatch):
    async def _fake_snapshot():
        return {
            "services": {
                "mcp": {"ok": True, "active": "active", "uptime_seconds": 120},
                "dispatcher": {"ok": True, "active": "active", "uptime_seconds": 120},
            },
            "local": {
                "mcp_health": {"data": {"status": "healthy"}, "latency_ms": 180},
                "agent_status": {"ok": True},
                "autonomy_health": {"ok": True},
            },
            "ops": {"state": "ok"},
            "restart": {"exists": True, "status": "completed", "phase": "done", "age_seconds": 5},
        }

    monkeypatch.setattr("gateway.status_snapshot.collect_status_snapshot", _fake_snapshot)
    monkeypatch.setattr(
        "tools.email_tool.tool.get_email_status",
        lambda: {"success": True, "authenticated": True, "backend": "resend"},
    )
    monkeypatch.setattr(
        "orchestration.browser_workflow_eval.BROWSER_WORKFLOW_EVAL_CASES",
        [{"name": "case-a"}],
    )
    monkeypatch.setattr(
        "orchestration.browser_workflow_eval.evaluate_browser_workflow_case",
        lambda case: {"name": case["name"], "passed": True},
    )

    result = await get_e2e_regression_matrix()

    assert result["status"] == "ok"
    assert result["summary"]["overall"] == "pass"
    assert len(result["flows"]) == 4
