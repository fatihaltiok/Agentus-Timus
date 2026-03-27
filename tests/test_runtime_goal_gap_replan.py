from __future__ import annotations

from orchestration.meta_orchestration import resolve_runtime_goal_gap_stage


def test_runtime_goal_gap_replan_requests_document_stage_for_artifact_goal():
    stage = resolve_runtime_goal_gap_stage(
        {"output_mode": "artifact", "artifact_format": "txt"},
        current_stage_ids=["research_discovery"],
        current_stage_agents=["research"],
        previous_stage_status="success",
        previous_stage_agent="research",
        has_result_material=True,
    )

    assert stage is not None
    assert stage["stage_id"] == "document_output"
    assert stage["agent"] == "document"
    assert stage["adaptive_reason"] == "runtime_goal_gap_document"


def test_runtime_goal_gap_replan_skips_when_document_stage_already_present():
    stage = resolve_runtime_goal_gap_stage(
        {"output_mode": "artifact", "artifact_format": "txt"},
        current_stage_ids=["research_discovery", "document_output"],
        current_stage_agents=["research", "document"],
        previous_stage_status="success",
        previous_stage_agent="research",
        has_result_material=True,
    )

    assert stage is None
