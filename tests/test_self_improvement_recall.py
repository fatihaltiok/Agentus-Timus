from __future__ import annotations

import pytest

from orchestration.self_improvement_engine import (
    ConversationRecallRecord,
    SelfImprovementEngine,
)


def test_conversation_recall_stats_aggregate_sources(tmp_path):
    engine = SelfImprovementEngine(db_path=tmp_path / "task_queue.db")
    engine.record_conversation_recall(
        ConversationRecallRecord(query="wie war nochmal dein plan", source="semantic", semantic_candidates=3)
    )
    engine.record_conversation_recall(
        ConversationRecallRecord(query="woran lag das nochmal", source="summary", used_summary=True)
    )
    engine.record_conversation_recall(
        ConversationRecallRecord(query="erinner mich", source="none")
    )

    stats = engine.get_conversation_recall_stats(days=7)

    assert stats["total_queries"] == 3
    assert stats["semantic_hits"] == 1
    assert stats["summary_hits"] == 1
    assert stats["none_hits"] == 1
    assert stats["semantic_rate"] == pytest.approx(0.333, abs=0.001)
    assert stats["summary_fallback_rate"] == pytest.approx(0.333, abs=0.001)
    assert stats["none_rate"] == pytest.approx(0.333, abs=0.001)


@pytest.mark.asyncio
async def test_run_analysis_cycle_emits_recall_suggestion(tmp_path, monkeypatch):
    monkeypatch.setattr("orchestration.self_improvement_engine.MIN_SAMPLES", 2)
    engine = SelfImprovementEngine(db_path=tmp_path / "task_queue.db")
    engine.record_conversation_recall(
        ConversationRecallRecord(query="wie war nochmal dein plan", source="none")
    )
    engine.record_conversation_recall(
        ConversationRecallRecord(query="erinner mich", source="summary", used_summary=True)
    )

    report = await engine.run_analysis_cycle()

    findings = [item["finding"] for item in report.suggestions]
    assert any("Konversationeller Recall" in finding or "Conversation recall" in finding for finding in findings)
    assert report.recall_stats["total_queries"] == 2
