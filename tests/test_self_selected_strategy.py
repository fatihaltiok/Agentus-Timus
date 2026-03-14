from __future__ import annotations

from orchestration.self_selected_strategy import (
    build_task_profile,
    classify_strategy_error,
    select_strategy,
    select_tool_affordances,
)


def test_self_selected_strategy_prefers_lightweight_youtube_lookup():
    classification = {
        "task_type": "youtube_light_research",
        "recommended_recipe_id": "youtube_light_research",
        "recommended_agent_chain": ["meta", "executor"],
    }

    task_profile = build_task_profile(
        "Schau mal was es auf YouTube so gibt zu KI-Agenten",
        classification,
    )
    affordances = select_tool_affordances(classification, task_profile)
    strategy = select_strategy(
        "Schau mal was es auf YouTube so gibt zu KI-Agenten",
        classification,
        task_profile,
        affordances,
    )

    assert task_profile["intent"] == "casual_lookup"
    assert task_profile["desired_depth"] == "light"
    assert any(item["name"] == "search_youtube" for item in affordances)
    assert strategy["strategy_id"] == "youtube_lightweight_scan"
    assert strategy["strategy_mode"] == "lightweight_first"
    assert strategy["primary_recipe_id"] == "youtube_light_research"
    assert "search_youtube" in strategy["preferred_tools"]
    assert "start_deep_research" in strategy["avoid_tools"]
    assert strategy["error_strategy"] == "switch_tool_then_degrade"


def test_self_selected_strategy_prefers_layered_youtube_extraction():
    classification = {
        "task_type": "youtube_content_extraction",
        "recommended_recipe_id": "youtube_content_extraction",
        "recommended_agent_chain": ["meta", "visual", "research", "document"],
    }

    task_profile = build_task_profile(
        "Öffne YouTube, hole maximal viel Inhalt aus dem Video und schreibe einen Bericht",
        classification,
    )
    affordances = select_tool_affordances(classification, task_profile)
    strategy = select_strategy(
        "Öffne YouTube, hole maximal viel Inhalt aus dem Video und schreibe einen Bericht",
        classification,
        task_profile,
        affordances,
    )

    assert task_profile["intent"] == "content_extraction"
    assert task_profile["output_mode"] == "artifact"
    assert any(item["name"] == "get_youtube_subtitles" for item in affordances)
    assert strategy["strategy_id"] == "layered_youtube_extraction"
    assert strategy["primary_recipe_id"] == "youtube_content_extraction"
    assert strategy["fallback_recipe_id"] == "youtube_research_only"
    assert "get_youtube_video_info" in strategy["preferred_tools"]
    assert "start_deep_research" in strategy["fallback_tools"]


def test_self_selected_strategy_classifies_browser_failure_as_non_browser_fallback():
    handoff = {
        "task_type": "youtube_content_extraction",
        "site_kind": "youtube",
        "selected_strategy": {
            "fallback_recipe_id": "youtube_research_only",
            "error_strategy": "recover_then_continue",
        },
    }
    failed_stage = {
        "stage_id": "visual_access",
        "agent": "visual",
        "error": "Videoseite konnte nicht verifiziert werden",
    }

    signal = classify_strategy_error(handoff=handoff, failed_stage=failed_stage)

    assert signal["error_class"] == "browser_runtime_failure"
    assert signal["prefer_non_browser_fallback"] is True
    assert signal["prefer_recipe_id"] == "youtube_research_only"
    assert signal["suggested_reaction"] == "switch_to_non_browser_fallback"


def test_self_selected_strategy_prefers_location_context_then_maps():
    classification = {
        "task_type": "location_local_search",
        "recommended_recipe_id": "location_local_search",
        "recommended_agent_chain": ["meta", "executor"],
    }

    task_profile = build_task_profile(
        "Was ist hier in meiner Nähe gerade offen?",
        classification,
    )
    affordances = select_tool_affordances(classification, task_profile)
    strategy = select_strategy(
        "Was ist hier in meiner Nähe gerade offen?",
        classification,
        task_profile,
        affordances,
    )

    assert task_profile["intent"] == "local_lookup"
    assert task_profile["desired_depth"] == "light"
    assert any(item["name"] == "search_google_maps_places" for item in affordances)
    assert strategy["strategy_id"] == "location_context_then_maps"
    assert "get_current_location_context" in strategy["preferred_tools"]
    assert "search_google_maps_places" in strategy["preferred_tools"]


def test_self_selected_strategy_classifies_missing_device_location():
    handoff = {
        "task_type": "location_local_search",
        "site_kind": "maps",
        "selected_strategy": {
            "fallback_recipe_id": "",
            "error_strategy": "switch_tool_then_degrade",
        },
    }
    failed_stage = {
        "stage_id": "location_context_scan",
        "agent": "executor",
        "error": "Kein aktueller Mobil-Standort verfuegbar.",
    }

    signal = classify_strategy_error(handoff=handoff, failed_stage=failed_stage)

    assert signal["error_class"] == "missing_device_location"
    assert signal["suggested_reaction"] == "degrade_or_request_location_refresh"
    assert signal["degrade_ok"] is True
