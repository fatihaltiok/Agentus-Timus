from __future__ import annotations

from orchestration.ops_release_gate import (
    build_ops_gate_alert_message,
    evaluate_ops_release_gate,
)


def test_ops_release_gate_blocks_on_critical_ops():
    summary = {
        "state": "critical",
        "critical_alerts": 2,
        "warnings": 1,
        "failing_services": 1,
        "unhealthy_providers": 0,
        "slo": {"breached": 2},
        "alerts": [
            {"severity": "critical", "target": "mcp", "error_class": "availability"},
            {"severity": "warn", "target": "budget", "error_class": "budget"},
        ],
    }

    decision = evaluate_ops_release_gate(summary, current_canary_percent=40)

    assert decision["state"] == "blocked"
    assert decision["release_blocked"] is True
    assert decision["recommended_canary_percent"] == 0
    assert "mcp" in decision["critical_targets"]


def test_ops_release_gate_warns_on_noncritical_drift(monkeypatch):
    monkeypatch.setenv("OPS_WARN_CANARY_CAP_PERCENT", "15")
    summary = {
        "state": "warn",
        "critical_alerts": 0,
        "warnings": 2,
        "failing_services": 0,
        "unhealthy_providers": 0,
        "slo": {"breached": 1},
        "alerts": [
            {"severity": "warn", "target": "llm", "error_class": "latency"},
        ],
    }

    decision = evaluate_ops_release_gate(summary, current_canary_percent=40)

    assert decision["state"] == "warn"
    assert decision["canary_deferred"] is True
    assert decision["recommended_canary_percent"] == 15


def test_ops_gate_alert_message_contains_decision_summary():
    summary = {"state": "warn", "critical_alerts": 0, "warnings": 1, "failing_services": 0, "unhealthy_providers": 0}
    decision = {
        "state": "warn",
        "release_blocked": False,
        "canary_deferred": True,
        "recommended_canary_percent": 10,
        "critical_targets": [],
        "warning_targets": ["llm"],
    }

    message = build_ops_gate_alert_message(summary, decision)

    assert "Ops Release Gate" in message
    assert "RecommendedCanary 10%" in message
    assert "Warning targets: llm" in message
