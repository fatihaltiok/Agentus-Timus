from __future__ import annotations

import pytest

from orchestration.self_improvement_engine import RoutingRecord, SelfImprovementEngine


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
