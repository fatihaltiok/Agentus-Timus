from __future__ import annotations

from types import SimpleNamespace

import pytest

from tools.self_improvement_tool.tool import get_ops_observability


@pytest.mark.asyncio
async def test_get_ops_observability_returns_central_summary(monkeypatch):
    async def _fake_collect_status_snapshot():
        return {
            "services": {
                "mcp": {"ok": True, "active": "active"},
                "dispatcher": {"ok": False, "active": "failed"},
            },
            "providers": {
                "openrouter": {"state": "ok"},
                "openai": {"state": "error"},
            },
            "budget": {"state": "warn", "message": "budget warn"},
        }

    monkeypatch.setattr(
        "gateway.status_snapshot.collect_status_snapshot",
        _fake_collect_status_snapshot,
    )
    monkeypatch.setattr(
        "orchestration.self_improvement_engine.get_improvement_engine",
        lambda: SimpleNamespace(
            get_tool_stats=lambda days=7: [
                {
                    "tool_name": "scan_ui_elements",
                    "agent": "visual",
                    "total": 5,
                    "success_rate": 0.4,
                    "avg_duration_ms": 1800,
                }
            ],
            get_routing_stats=lambda days=7: {
                "by_agent": {"meta": {"total": 4, "avg_confidence": 0.51}},
            },
            get_llm_usage_summary=lambda days=7, limit=5: {
                "analysis_days": days,
                "session_id": "",
                "total_requests": 8,
                "successful_requests": 6,
                "failed_requests": 2,
                "success_rate": 0.75,
                "input_tokens": 1000,
                "output_tokens": 200,
                "cached_tokens": 0,
                "total_cost_usd": 0.04,
                "avg_latency_ms": 120.0,
                "top_agents": [],
                "top_models": [],
            },
        ),
    )

    result = await get_ops_observability(days=7, limit=4)

    assert result["status"] == "ok"
    assert result["days"] == 7
    assert result["state"] == "critical"
    assert result["failing_services"] == 1
    assert result["unhealthy_providers"] == 1
    assert result["error_classes"]["availability"] >= 1
    assert result["slo"]["breached"] >= 1
    messages = [item["message"] for item in result["alerts"]]
    assert any("Service dispatcher" in message for message in messages)
    assert any("Provider openai" in message for message in messages)
