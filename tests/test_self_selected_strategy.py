from __future__ import annotations

from orchestration.self_selected_strategy import (
    build_task_profile,
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
