from __future__ import annotations

from orchestration.meta_orchestration_eval import (
    META_ORCHESTRATION_EVAL_CASES,
    META_REPLAN_EVAL_CASES,
    evaluate_meta_orchestration_case,
    evaluate_meta_replan_case,
)


def test_meta_orchestration_eval_cases_all_pass():
    results = [evaluate_meta_orchestration_case(case) for case in META_ORCHESTRATION_EVAL_CASES]

    assert all(result["passed"] for result in results)


def test_meta_orchestration_eval_youtube_case_tracks_recipe_and_chain():
    case = next(case for case in META_ORCHESTRATION_EVAL_CASES if case["name"] == "youtube_content_extraction")

    result = evaluate_meta_orchestration_case(case)

    assert result["decision"]["recommended_recipe_id"] == "youtube_content_extraction"
    assert result["decision"]["recommended_agent_chain"] == ["meta", "visual", "research", "document"]
    assert result["benchmark"]["recipe_match"] is True
    assert result["benchmark"]["chain_match"] is True
    assert result["actual_alternative_recipe_ids"] == ["youtube_search_then_visual", "youtube_research_only"]
    assert result["actual_recovery_stage_ids"] == ["research_context_recovery"]


def test_meta_orchestration_eval_simple_browser_guard_stays_direct():
    case = next(case for case in META_ORCHESTRATION_EVAL_CASES if case["name"] == "simple_booking_navigation_guard")

    result = evaluate_meta_orchestration_case(case)

    assert result["decision"]["route_to_meta"] is False
    assert result["decision"]["recommended_entry_agent"] == "visual"
    assert result["decision"]["recommended_agent_chain"] == ["visual"]
    assert result["decision"]["needs_structured_handoff"] is False


def test_meta_replan_eval_cases_all_pass():
    results = [evaluate_meta_replan_case(case) for case in META_REPLAN_EVAL_CASES]

    assert all(result["passed"] for result in results)


def test_meta_replan_eval_x_failure_prefers_research_only():
    case = next(case for case in META_REPLAN_EVAL_CASES if case["name"] == "x_visual_failure_replans_to_research_only")

    result = evaluate_meta_replan_case(case)

    assert result["initial_recipe_id"] == "web_visual_research_summary"
    assert result["replanned_recipe_id"] == "web_research_only"
