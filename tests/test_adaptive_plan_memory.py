from __future__ import annotations

from orchestration.adaptive_plan_memory import AdaptivePlanMemory
from orchestration.adaptive_planner import build_adaptive_plan
from orchestration.capability_graph import build_capability_graph
from orchestration.goal_spec import derive_goal_spec
from orchestration.meta_orchestration import get_agent_capability_map


def test_adaptive_plan_memory_aggregates_successful_and_failed_chains(tmp_path):
    memory = AdaptivePlanMemory(tmp_path / "adaptive_plan_memory.db")
    goal_signature = "pricing|live|light|table|none|loc=0|deliver=0"

    memory.record_outcome(
        goal_signature=goal_signature,
        final_chain=["meta", "executor", "document"],
        recommended_chain=["meta", "executor", "document"],
        success=True,
        runtime_gap_insertions=["runtime_goal_gap_document"],
        duration_ms=1200,
    )
    memory.record_outcome(
        goal_signature=goal_signature,
        final_chain=["meta", "executor", "document"],
        recommended_chain=["meta", "executor", "document"],
        success=True,
        duration_ms=900,
    )
    memory.record_outcome(
        goal_signature=goal_signature,
        final_chain=["meta", "executor"],
        recommended_chain=["meta", "executor"],
        success=False,
        duration_ms=800,
    )

    stats = memory.get_goal_chain_stats(goal_signature)

    assert stats[0]["chain"] == ["meta", "executor", "document"]
    assert stats[0]["evidence_count"] == 2
    assert stats[0]["success_rate"] == 1.0
    assert stats[0]["runtime_gap_rate"] == 0.5
    assert stats[0]["learned_bias"] > 0.0
    assert any(item["chain"] == ["meta", "executor"] and item["learned_bias"] < 0.0 for item in stats)


def test_adaptive_planner_applies_learned_bias_to_candidate_scores():
    classification = {
        "task_type": "simple_live_lookup_document",
        "site_kind": None,
        "required_capabilities": ["live_lookup", "light_search", "structured_export"],
        "recommended_entry_agent": "meta",
        "recommended_agent_chain": ["meta", "executor", "document"],
        "needs_structured_handoff": True,
        "reason": "simple_live_lookup_document",
        "recommended_recipe_id": "simple_live_lookup_document",
        "recipe_stages": [],
        "recipe_recoveries": [],
        "alternative_recipes": [],
    }
    query = "Erstelle mir eine Liste mit den aktuellen Preisen der besten LLMs und zeige mir dann die Tabelle"
    goal_spec = derive_goal_spec(query, classification)
    capability_graph = build_capability_graph(
        goal_spec,
        get_agent_capability_map(),
        current_chain=classification["recommended_agent_chain"],
        required_capabilities=classification["required_capabilities"],
    )

    baseline = build_adaptive_plan(goal_spec, capability_graph, classification)
    boosted = build_adaptive_plan(
        goal_spec,
        capability_graph,
        classification,
        learned_chain_stats=[
            {
                "chain": ["meta", "executor", "document"],
                "learned_bias": 0.18,
                "evidence_count": 3,
                "learned_confidence": 1.0,
            }
        ],
    )

    assert boosted["recommended_chain"] == ["meta", "executor", "document"]
    assert boosted["confidence"] > baseline["confidence"]
    assert boosted["candidate_chains"][0]["learned_bias"] > 0.0
