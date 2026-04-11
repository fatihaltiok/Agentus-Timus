from __future__ import annotations

import pytest

from datetime import datetime, timedelta
import sqlite3

from orchestration.self_improvement_engine import (
    ConversationRecallRecord,
    LLMUsageRecord,
    RoutingRecord,
    SelfImprovementEngine,
    ToolUsageRecord,
)


def test_routing_stats_separate_outcome_and_router_confidence(tmp_path):
    engine = SelfImprovementEngine(db_path=tmp_path / "task_queue.db")
    engine.record_routing(
        RoutingRecord(
            task_hash="a1",
            chosen_agent="research",
            outcome="success",
            router_confidence=0.91,
            outcome_score=0.8,
        )
    )
    engine.record_routing(
        RoutingRecord(
            task_hash="a2",
            chosen_agent="research",
            outcome="partial",
            router_confidence=None,
            outcome_score=0.4,
        )
    )

    stats = engine.get_routing_stats(days=7)
    research = stats["by_agent"]["research"]

    assert stats["total_decisions"] == 2
    assert research["avg_router_confidence"] == pytest.approx(0.91, abs=0.001)
    assert research["avg_outcome_score"] == pytest.approx(0.6, abs=0.001)
    assert research["avg_confidence"] == pytest.approx(0.91, abs=0.001)
    assert research["router_confidence_samples"] == 1
    assert research["success_rate"] == pytest.approx(0.5, abs=0.001)


def test_routing_stats_ignore_unregistered_test_agents(tmp_path):
    engine = SelfImprovementEngine(db_path=tmp_path / "task_queue.db")
    engine.record_routing(
        RoutingRecord(
            task_hash="t1",
            chosen_agent="research",
            outcome="success",
            outcome_score=0.8,
        )
    )
    engine.record_routing(
        RoutingRecord(
            task_hash="t2",
            chosen_agent="broken",
            outcome="error",
            outcome_score=0.0,
        )
    )

    stats = engine.get_routing_stats(days=7)

    assert stats["raw_total_decisions"] == 2
    assert stats["total_decisions"] == 1
    assert stats["ignored_test_decisions"] == 1
    assert "research" in stats["by_agent"]
    assert "broken" not in stats["by_agent"]
    assert stats["unknown_agents"][0]["agent"] == "broken"


@pytest.mark.asyncio
async def test_run_analysis_cycle_flags_low_routing_success_not_fake_confidence(tmp_path, monkeypatch):
    monkeypatch.setattr("orchestration.self_improvement_engine.MIN_SAMPLES", 2)
    engine = SelfImprovementEngine(db_path=tmp_path / "task_queue.db")
    engine.record_routing(
        RoutingRecord(
            task_hash="b1",
            chosen_agent="research",
            outcome="error",
            outcome_score=0.8,
        )
    )
    engine.record_routing(
        RoutingRecord(
            task_hash="b2",
            chosen_agent="research",
            outcome="success",
            outcome_score=0.8,
        )
    )

    report = await engine.run_analysis_cycle()

    findings = [item["finding"] for item in report.suggestions if item.get("type") == "routing"]
    assert findings
    assert any("Erfolgsrate" in finding for finding in findings)


def test_get_suggestions_include_measured_evidence_fields(tmp_path):
    engine = SelfImprovementEngine(db_path=tmp_path / "task_queue.db")
    engine._save_suggestion(
        {
            "type": "routing",
            "target": "research",
            "finding": "Gemessene Routing-Qualitaet zu Agent 'research' ist schwach.",
            "suggestion": "Routing schaerfen.",
            "confidence": 0.7,
            "severity": "medium",
        }
    )

    suggestions = engine.get_suggestions(applied=False)

    assert suggestions
    assert suggestions[0]["evidence_level"] == "measured"
    assert suggestions[0]["evidence_basis"] == "runtime_analytics"


def test_get_suggestions_include_normalized_candidate_fields(tmp_path):
    engine = SelfImprovementEngine(db_path=tmp_path / "task_queue.db")
    engine._save_suggestion(
        {
            "type": "routing",
            "target": "research",
            "finding": "Gemessene Routing-Qualitaet zu Agent 'research' ist schwach.",
            "suggestion": "Routing schaerfen.",
            "confidence": 0.7,
            "severity": "medium",
        }
    )

    suggestion = engine.get_suggestions(applied=False)[0]

    assert suggestion["candidate_id"] == "m12:1"
    assert suggestion["source"] == "self_improvement_engine"
    assert suggestion["category"] == "routing"
    assert suggestion["problem"] == "Gemessene Routing-Qualitaet zu Agent 'research' ist schwach."
    assert suggestion["proposed_action"] == "Routing schaerfen."
    assert suggestion["occurrence_count"] == 1
    assert suggestion["status"] == "open"


def test_get_normalized_suggestions_returns_phase_e_shape_only(tmp_path):
    engine = SelfImprovementEngine(db_path=tmp_path / "task_queue.db")
    engine._save_suggestion(
        {
            "type": "routing",
            "target": "research",
            "finding": "Gemessene Routing-Qualitaet zu Agent 'research' ist schwach.",
            "suggestion": "Routing schaerfen.",
            "confidence": 0.7,
            "severity": "medium",
        }
    )

    suggestion = engine.get_normalized_suggestions(applied=False)[0]

    assert suggestion["candidate_id"] == "m12:1"
    assert suggestion["source"] == "self_improvement_engine"
    assert suggestion["status"] == "open"
    assert suggestion["problem"] == "Gemessene Routing-Qualitaet zu Agent 'research' ist schwach."
    assert suggestion["proposed_action"] == "Routing schaerfen."
    assert "finding" not in suggestion
    assert "suggestion" not in suggestion


def test_housekeeping_prunes_old_analytics_rows(tmp_path, monkeypatch):
    monkeypatch.setattr("orchestration.self_improvement_engine._ANALYTICS_RETENTION_DAYS", 30)
    monkeypatch.setattr("orchestration.self_improvement_engine._SUGGESTION_RETENTION_DAYS", 30)
    monkeypatch.setattr("orchestration.self_improvement_engine._HOUSEKEEPING_INTERVAL_SECONDS", 1)

    engine = SelfImprovementEngine(db_path=tmp_path / "task_queue.db")
    recent_ts = datetime.now().isoformat()
    old_ts = (datetime.now() - timedelta(days=45)).isoformat()

    engine.record_tool_usage(
        ToolUsageRecord(tool_name="recent_tool", agent="executor", timestamp=recent_ts)
    )
    engine.record_tool_usage(
        ToolUsageRecord(tool_name="old_tool", agent="executor", timestamp=old_ts)
    )
    engine.record_routing(
        RoutingRecord(task_hash="new", chosen_agent="research", outcome_score=0.8, timestamp=recent_ts)
    )
    engine.record_routing(
        RoutingRecord(task_hash="old", chosen_agent="research", outcome_score=0.8, timestamp=old_ts)
    )
    engine.record_llm_usage(
        LLMUsageRecord(trace_id="recent", agent="meta", provider="openai", model="gpt", timestamp=recent_ts)
    )
    engine.record_llm_usage(
        LLMUsageRecord(trace_id="old", agent="meta", provider="openai", model="gpt", timestamp=old_ts)
    )
    engine.record_conversation_recall(
        ConversationRecallRecord(query="recent", source="topic_recall", timestamp=recent_ts)
    )
    engine.record_conversation_recall(
        ConversationRecallRecord(query="old", source="none", timestamp=old_ts)
    )
    engine._save_suggestion(
        {
            "type": "routing",
            "target": "research",
            "finding": "Old suggestion",
            "suggestion": "cleanup",
            "confidence": 0.7,
            "severity": "medium",
        }
    )
    engine.mark_suggestion_applied("1", applied=True)
    with sqlite3.connect(str(engine.db_path)) as conn:
        conn.execute(
            "UPDATE improvement_suggestions_m12 SET created_at = ? WHERE id = 1",
            (old_ts,),
        )
        conn.commit()

    result = engine.run_housekeeping(force=True)

    assert result["deleted"]["tool_analytics"] == 1
    assert result["deleted"]["routing_analytics"] == 1
    assert result["deleted"]["llm_usage_analytics"] == 1
    assert result["deleted"]["conversation_recall_analytics"] == 1
    assert result["deleted"]["applied_suggestions"] == 1
    assert engine.get_tool_stats(days=90)[0]["tool_name"] == "recent_tool"
    assert engine.get_routing_stats(days=90)["total_decisions"] == 1
