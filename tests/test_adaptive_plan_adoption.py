from __future__ import annotations

from orchestration.meta_orchestration import (
    resolve_adaptive_plan_adoption,
    resolve_orchestration_alternative_recipes,
    resolve_orchestration_recipe,
)


def test_resolve_adaptive_plan_adoption_prefers_safe_alternative_recipe():
    current = resolve_orchestration_recipe("simple_live_lookup")
    alternative = resolve_orchestration_recipe("simple_live_lookup_document")

    resolution = resolve_adaptive_plan_adoption(
        {
            "task_type": "simple_live_lookup",
            "site_kind": "web",
            "recommended_recipe_id": current["recipe_id"],
            "recommended_agent_chain": current["recommended_agent_chain"],
            "alternative_recipes": [alternative],
            "adaptive_plan": {
                "planner_mode": "advisory",
                "confidence": 0.91,
                "recommended_chain": ["meta", "executor", "document"],
                "recommended_recipe_hint": "simple_live_lookup_document",
            },
        }
    )

    assert resolution["state"] == "adopted"
    assert resolution["adopted_recipe_id"] == "simple_live_lookup_document"
    assert resolution["recipe_payload"]["recipe_id"] == "simple_live_lookup_document"


def test_resolve_adaptive_plan_adoption_rejects_low_confidence_switch():
    current = resolve_orchestration_recipe("simple_live_lookup")
    alternative = resolve_orchestration_recipe("simple_live_lookup_document")

    resolution = resolve_adaptive_plan_adoption(
        {
            "task_type": "simple_live_lookup",
            "site_kind": "web",
            "recommended_recipe_id": current["recipe_id"],
            "recommended_agent_chain": current["recommended_agent_chain"],
            "alternative_recipes": [alternative],
            "adaptive_plan": {
                "planner_mode": "advisory",
                "confidence": 0.61,
                "recommended_chain": ["meta", "executor", "document"],
                "recommended_recipe_hint": "simple_live_lookup_document",
            },
        }
    )

    assert resolution["state"] == "rejected"
    assert resolution["reason"] == "low_confidence"


def test_resolve_adaptive_plan_adoption_keeps_current_when_plan_already_matches():
    current = resolve_orchestration_recipe("location_route")

    resolution = resolve_adaptive_plan_adoption(
        {
            "task_type": "location_route",
            "site_kind": "maps",
            "recommended_recipe_id": current["recipe_id"],
            "recommended_agent_chain": current["recommended_agent_chain"],
            "alternative_recipes": resolve_orchestration_alternative_recipes("location_route", "maps"),
            "adaptive_plan": {
                "planner_mode": "advisory",
                "confidence": 0.88,
                "recommended_chain": ["meta", "executor"],
                "recommended_recipe_hint": "location_route",
            },
        }
    )

    assert resolution["state"] == "fallback_current"
    assert resolution["reason"] == "current_recipe_already_matches_plan"
