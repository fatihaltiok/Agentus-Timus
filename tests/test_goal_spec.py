from __future__ import annotations

from orchestration.goal_spec import derive_goal_spec


def test_derive_goal_spec_detects_live_pricing_artifact_goal():
    goal = derive_goal_spec(
        "Speichere mir aktuelle LLM-Preise als txt Datei",
        {
            "task_type": "simple_live_lookup_document",
            "site_kind": None,
            "required_capabilities": ["live_lookup", "document_creation"],
        },
    )

    assert goal["domain"] == "pricing"
    assert goal["freshness"] == "live"
    assert goal["evidence_level"] == "light"
    assert goal["output_mode"] == "artifact"
    assert goal["artifact_format"] == "txt"
    assert goal["delivery_required"] is False
    assert goal["goal_signature"].startswith("pricing|live|light|artifact|txt|")


def test_derive_goal_spec_detects_location_goal_without_explicit_route_recipe():
    goal = derive_goal_spec(
        "Wo bekomme ich gerade Kaffee?",
        {
            "task_type": "location_local_search",
            "site_kind": "maps",
            "required_capabilities": ["location_context", "local_maps_search"],
        },
    )

    assert goal["domain"] == "local_search"
    assert goal["freshness"] == "live"
    assert goal["uses_location"] is True
    assert goal["output_mode"] == "answer"
