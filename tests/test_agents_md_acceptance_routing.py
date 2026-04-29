"""Routing gates derived from AGENTS.md acceptance examples."""

from __future__ import annotations

from orchestration.meta_orchestration import classify_meta_task


def _frame_domain(result: dict) -> str:
    return str((result.get("meta_request_frame") or {}).get("task_domain") or "")


def _mode(result: dict) -> str:
    return str((result.get("meta_interaction_mode") or {}).get("mode") or "")


def test_current_meetups_request_uses_web_lookup() -> None:
    result = classify_meta_task("such mir aktuelle KI-Meetups in Frankfurt")

    assert result["task_type"] == "simple_live_lookup"
    assert result["response_mode"] == "execute"
    assert result["recommended_agent_chain"] == ["meta", "executor"]
    assert _frame_domain(result) == "general_research"


def test_hardware_comparison_uses_lookup_comparison_path() -> None:
    result = classify_meta_task("vergleiche RTX 3090 und RTX 4090 für lokale KI")

    assert result["task_type"] == "simple_live_lookup"
    assert result["recommended_agent_chain"] == ["meta", "executor"]
    assert result["response_mode"] == "execute"


def test_technical_sketch_routes_to_creative_agent() -> None:
    result = classify_meta_task("mach mir eine technische Skizze von einem modularen KI-Server")

    assert result["task_type"] == "image_generation"
    assert result["recommended_agent_chain"] == ["meta", "creative"]
    assert result["recommended_recipe_id"] == "image_generation"
    assert _frame_domain(result) == "creative_generation"
    assert _mode(result) != "think_partner"


def test_claim_verification_routes_to_research() -> None:
    result = classify_meta_task("prüfe ob diese Aussage stimmt")

    assert result["task_type"] == "knowledge_research"
    assert result["recommended_agent_chain"] == ["meta", "research"]
    assert result["recommended_recipe_id"] == "knowledge_research"
    assert _mode(result) == "inspect"


def test_plan_request_uses_planning_domain_without_clarification() -> None:
    result = classify_meta_task("erstelle mir einen Plan für Timus")

    assert result["task_type"] == "single_lane"
    assert result["recommended_agent_chain"] == ["meta"]
    assert result["response_mode"] == "execute"
    assert _frame_domain(result) == "planning_advisory"
    assert _mode(result) == "assist"


def test_creative_prompt_optimization_routes_to_creative_agent() -> None:
    result = classify_meta_task("optimiere diesen Prompt für meinen Kreativ-Agenten")

    assert result["task_type"] == "creative_text_optimization"
    assert result["recommended_agent_chain"] == ["meta", "creative"]
    assert result["recommended_recipe_id"] == "creative_text_optimization"
    assert _frame_domain(result) == "creative_generation"


def test_error_code_change_request_routes_to_developer_agent() -> None:
    result = classify_meta_task("lies diesen Fehler und sag mir, was im Code geändert werden muss")

    assert result["task_type"] == "code_troubleshooting"
    assert result["recommended_agent_chain"] == ["meta", "developer"]
    assert result["recommended_recipe_id"] == "code_troubleshooting"
    assert _frame_domain(result) == "developer_work"
