from __future__ import annotations

import deal
from hypothesis import given, settings
from hypothesis import strategies as st

from orchestration.meta_orchestration import resolve_runtime_goal_gap_stage


@deal.post(lambda r: r is None or set(r.keys()) >= {"stage_id", "agent", "goal", "expected_output", "adaptive_reason"})
@deal.post(lambda r: r is None or r["agent"] == "document")
def _contract_resolve_runtime_goal_gap_stage(
    output_mode: str,
    artifact_format: str,
    stage_has_document: bool,
    previous_status: str,
    previous_agent: str,
    has_result_material: bool,
):
    stage_ids = ["live_lookup_scan"]
    stage_agents = ["executor"]
    if stage_has_document:
        stage_ids.append("document_output")
        stage_agents.append("document")
    return resolve_runtime_goal_gap_stage(
        {"output_mode": output_mode, "artifact_format": artifact_format},
        current_stage_ids=stage_ids,
        current_stage_agents=stage_agents,
        previous_stage_status=previous_status,
        previous_stage_agent=previous_agent,
        has_result_material=has_result_material,
    )


@given(
    st.sampled_from(["artifact", "table", "answer"]),
    st.sampled_from(["", "txt", "xlsx"]),
    st.booleans(),
    st.sampled_from(["success", "error", "skipped"]),
    st.sampled_from(["executor", "research", "visual"]),
    st.booleans(),
)
@settings(max_examples=80)
def test_hypothesis_runtime_goal_gap_replan_shape(
    output_mode: str,
    artifact_format: str,
    stage_has_document: bool,
    previous_status: str,
    previous_agent: str,
    has_result_material: bool,
):
    result = _contract_resolve_runtime_goal_gap_stage(
        output_mode,
        artifact_format,
        stage_has_document,
        previous_status,
        previous_agent,
        has_result_material,
    )
    if result is not None:
        assert result["stage_id"] == "document_output"
