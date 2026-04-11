from __future__ import annotations

from types import SimpleNamespace

import pytest

from tools.self_improvement_tool.tool import (
    get_improvement_suggestions,
    get_ops_observability,
)


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
            get_conversation_recall_stats=lambda days=7: {
                "analysis_days": days,
                "total_queries": 4,
                "semantic_hits": 1,
                "recent_hits": 1,
                "summary_hits": 1,
                "none_hits": 1,
                "semantic_rate": 0.25,
                "recent_reply_rate": 0.25,
                "summary_fallback_rate": 0.25,
                "none_rate": 0.25,
                "avg_semantic_candidates": 1.5,
                "avg_recent_reply_candidates": 1.0,
                "avg_top_distance": 0.18,
                "top_sources": [{"source": "semantic", "total": 1}],
            },
        ),
    )

    result = await get_ops_observability(days=7, limit=4)

    assert result["status"] == "ok"
    assert result["days"] == 7
    assert result["state"] == "critical"
    assert result["failing_services"] == 1
    assert result["unhealthy_providers"] == 1
    assert result["recall"]["total_queries"] == 4
    assert result["top_recall_risks"]
    assert result["error_classes"]["availability"] >= 1
    assert result["slo"]["breached"] >= 1
    messages = [item["message"] for item in result["alerts"]]
    assert any("Service dispatcher" in message for message in messages)
    assert any("Provider openai" in message for message in messages)


@pytest.mark.asyncio
async def test_get_improvement_suggestions_exposes_normalized_candidates(monkeypatch):
    async def _fake_combined_candidates(self):
        return [
            {
                "candidate_id": "m12:1",
                "source": "self_improvement_engine",
                "category": "routing",
                "problem": "Routing schwach",
                "proposed_action": "Routing haerten",
                "status": "open",
                "priority_score": 1.1,
            }
        ]

    monkeypatch.setattr(
        "orchestration.self_improvement_engine.get_improvement_engine",
        lambda: SimpleNamespace(
            get_suggestions=lambda applied=False: [
                {"id": 1, "finding": "Routing schwach", "suggestion": "Routing haerten"}
            ],
            get_normalized_suggestions=lambda applied=False: [
                {
                    "candidate_id": "m12:1",
                    "source": "self_improvement_engine",
                    "category": "routing",
                    "problem": "Routing schwach",
                    "proposed_action": "Routing haerten",
                    "status": "open",
                }
            ],
        ),
    )
    monkeypatch.setattr(
        "orchestration.session_reflection.SessionReflectionLoop.get_improvement_suggestions",
        _fake_combined_candidates,
    )

    result = await get_improvement_suggestions(include_applied=False)

    assert result["status"] == "ok"
    assert result["count"] == 1
    assert result["candidate_count"] == 1
    assert result["normalized_candidates"][0]["candidate_id"] == "m12:1"
    assert result["normalized_candidates"][0]["problem"] == "Routing schwach"
    assert result["top_candidate_insights"][0]["candidate_id"] == "m12:1"
    assert "prio=" in result["top_candidate_insights"][0]["summary"]
