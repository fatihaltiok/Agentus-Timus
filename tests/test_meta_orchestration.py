from __future__ import annotations

from orchestration.meta_orchestration import (
    build_meta_feedback_targets,
    classify_meta_task,
    get_agent_capability_map,
)


def test_agent_capability_map_exposes_meta_visual_and_research_profiles():
    capability_map = get_agent_capability_map()

    assert capability_map["meta"]["agent"] == "meta"
    assert "workflow_orchestration" in capability_map["meta"]["capabilities"]
    assert "goal" in capability_map["meta"]["handoff_fields"]
    assert "browser_navigation" in capability_map["visual"]["capabilities"]
    assert "content_extraction" in capability_map["research"]["capabilities"]


def test_classify_meta_task_keeps_simple_booking_navigation_direct():
    result = classify_meta_task("Starte den Browser und gehe auf booking.com", action_count=1)

    assert result["task_type"] == "ui_navigation"
    assert result["site_kind"] == "booking"
    assert result["recommended_entry_agent"] == "visual"
    assert result["recommended_agent_chain"] == ["visual"]
    assert result["needs_structured_handoff"] is False


def test_classify_meta_task_recommends_visual_and_research_for_youtube_extraction():
    result = classify_meta_task(
        "Öffne YouTube, hole maximal viel Inhalt aus dem Video und schreibe einen Bericht",
        action_count=3,
    )

    assert result["task_type"] == "youtube_content_extraction"
    assert result["site_kind"] == "youtube"
    assert result["recommended_entry_agent"] == "meta"
    assert result["recommended_agent_chain"] == ["meta", "visual", "research", "document"]
    assert result["needs_structured_handoff"] is True
    assert result["recommended_recipe_id"] == "youtube_content_extraction"
    assert [stage["stage_id"] for stage in result["recipe_stages"]] == [
        "visual_access",
        "research_synthesis",
        "document_output",
    ]
    assert result["recipe_recoveries"][0]["failed_stage_id"] == "visual_access"
    assert result["recipe_recoveries"][0]["recovery_stage_id"] == "research_context_recovery"


def test_classify_meta_task_exposes_booking_recipe_for_multistage_workflow():
    result = classify_meta_task(
        "Öffne booking.com, gib Berlin ein, wähle Daten und starte die Suche",
        action_count=4,
    )

    assert result["task_type"] == "multi_stage_web_task"
    assert result["site_kind"] == "booking"
    assert result["recommended_recipe_id"] == "booking_search"
    assert [stage["agent"] for stage in result["recipe_stages"]] == ["visual", "visual"]


def test_classify_meta_task_exposes_system_diagnosis_recipe():
    result = classify_meta_task(
        "Prüfe die Logs, analysiere den Systemstatus und starte den Service wenn nötig neu",
        action_count=3,
    )

    assert result["task_type"] == "system_diagnosis"
    assert result["recommended_recipe_id"] == "system_diagnosis"
    assert result["recipe_stages"][0]["agent"] == "system"


def test_build_meta_feedback_targets_emits_task_recipe_and_chain_targets():
    result = classify_meta_task(
        "Öffne YouTube, hole maximal viel Inhalt aus dem Video und schreibe einen Bericht",
        action_count=3,
    )

    targets = build_meta_feedback_targets(result)

    assert {"namespace": "meta_task_type", "key": "youtube_content_extraction"} in targets
    assert {"namespace": "meta_recipe", "key": "youtube_content_extraction"} in targets
    assert {
        "namespace": "meta_agent_chain",
        "key": "meta__visual__research__document",
    } in targets
