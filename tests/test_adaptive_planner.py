from __future__ import annotations

from orchestration.adaptive_planner import build_adaptive_plan
from orchestration.capability_graph import build_capability_graph
from orchestration.goal_spec import derive_goal_spec
from orchestration.meta_orchestration import classify_meta_task, get_agent_capability_map


def test_adaptive_planner_keeps_lookup_document_chain_when_goal_is_table():
    classification = classify_meta_task(
        "Erstelle mir eine Liste mit den aktuellen Preisen der besten LLMs und zeige mir dann die Tabelle",
        action_count=0,
    )

    goal_spec = classification["goal_spec"]
    capability_graph = classification["capability_graph"]
    adaptive_plan = classification["adaptive_plan"]

    assert goal_spec["output_mode"] == "table"
    assert goal_spec["domain"] == "pricing"
    assert any(node["actor"] == "executor" for node in capability_graph["matching_nodes"])
    assert any(node["actor"] == "document" for node in capability_graph["matching_nodes"])
    assert adaptive_plan["planner_mode"] == "advisory"
    assert adaptive_plan["recommended_chain"] == ["meta", "executor", "document"]
    assert adaptive_plan["recommended_recipe_hint"] == "simple_live_lookup_document"


def test_adaptive_planner_extends_live_lookup_with_document_when_goal_changes_to_artifact():
    classification = {
        "task_type": "simple_live_lookup",
        "site_kind": None,
        "required_capabilities": ["live_lookup", "light_search"],
        "recommended_entry_agent": "meta",
        "recommended_agent_chain": ["meta", "executor"],
        "needs_structured_handoff": True,
        "reason": "simple_live_lookup",
        "recommended_recipe_id": "simple_live_lookup",
        "recipe_stages": [],
        "recipe_recoveries": [],
        "alternative_recipes": [],
    }
    goal_spec = derive_goal_spec(
        "Hole aktuelle LLM-Preise und speichere sie als txt Datei",
        classification,
    )
    capability_graph = build_capability_graph(
        goal_spec,
        get_agent_capability_map(),
        current_chain=classification["recommended_agent_chain"],
        required_capabilities=classification["required_capabilities"],
    )

    adaptive_plan = build_adaptive_plan(goal_spec, capability_graph, classification)

    assert "artifact_output_stage_missing" in capability_graph["goal_gaps"]
    assert adaptive_plan["recommended_chain"] == ["meta", "executor", "document"]
    assert adaptive_plan["reason"] == "goal_gap_extension"
