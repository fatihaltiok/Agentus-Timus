from __future__ import annotations

from orchestration.ops_observability import build_ops_observability_summary, classify_ops_state
from orchestration.ops_release_gate import evaluate_ops_release_gate


def test_classify_ops_state_prefers_critical():
    assert classify_ops_state(
        failing_services=1,
        unhealthy_providers=0,
        critical_alerts=0,
        warnings=3,
    ) == "critical"


def test_build_ops_observability_summary_collects_alerts():
    summary = build_ops_observability_summary(
        services={
            "mcp": {"ok": False, "active": "failed"},
            "dispatcher": {"ok": True, "active": "active"},
        },
        providers={
            "openrouter": {"state": "error"},
            "zai": {"state": "ok", "latency_ms": 2900},
            "openai": {"state": "ok"},
        },
        tool_stats=[
            {"tool_name": "scan_ui_elements", "agent": "visual", "total": 8, "success_rate": 0.4, "avg_duration_ms": 1800},
            {"tool_name": "restart_timus", "agent": "shell", "total": 4, "success_rate": 1.0, "avg_duration_ms": 3500},
        ],
        routing_stats={
            "by_agent": {
                "meta": {"total": 5, "avg_confidence": 0.52, "success_rate": 0.6},
            }
        },
        llm_usage={"total_requests": 10, "success_rate": 0.83, "avg_latency_ms": 2500},
        budget={"state": "warn", "message": "budget warn"},
        recall_stats={
            "total_queries": 5,
            "none_rate": 0.4,
            "summary_fallback_rate": 0.4,
            "avg_top_distance": 0.24,
        },
        self_healing={
            "open_incidents": 1,
            "degrade_mode": "restricted",
            "circuit_breakers_open": 1,
            "open_breakers": [{"component": "mcp", "signal": "mcp_health"}],
            "incidents": [
                {
                    "recovery_phase": "blocked",
                    "quarantine_state": "active",
                    "notification_state": "cooldown_active",
                    "memory_state": "known_bad_pattern",
                }
            ],
        },
        limit=10,
    )

    assert summary["state"] == "critical"
    assert summary["failing_services"] == 1
    assert summary["unhealthy_providers"] == 1
    assert summary["critical_alerts"] >= 1
    assert summary["error_classes"]["availability"] >= 2
    assert summary["error_classes"]["latency"] >= 1
    assert summary["error_classes"]["budget"] >= 1
    assert summary["error_classes"]["routing"] >= 1
    assert summary["error_classes"]["orchestration"] >= 1
    assert summary["slo"]["breached"] >= 1
    assert summary["self_stabilization_gate"]["state"] == "blocked"
    assert summary["top_recall_risks"]
    assert any(item["name"] == "llm_latency" and item["breached"] for item in summary["slo"]["items"])
    assert summary["top_outliers"]
    messages = [item["message"] for item in summary["alerts"]]
    assert any("Service mcp" in msg for msg in messages)
    assert any("Provider openrouter" in msg for msg in messages)
    assert any("scan_ui_elements" in msg for msg in messages)
    assert any("Routing meta" in msg for msg in messages)
    assert any("budget warn" in msg for msg in messages)
    assert any("Recall none_rate" in msg for msg in messages)
    assert any("Self-Healing gate blocked" in msg for msg in messages)
    assert summary["recall"]["total_queries"] == 5

    gate = evaluate_ops_release_gate(summary, current_canary_percent=30)
    assert gate["state"] == "blocked"
