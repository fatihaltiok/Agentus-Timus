from __future__ import annotations

import deal
from hypothesis import given, settings
from hypothesis import strategies as st

from orchestration.meta_orchestration import resolve_runtime_goal_gap_stage


@deal.post(lambda r: r is None or set(r.keys()) >= {"stage_id", "agent", "goal", "expected_output", "adaptive_reason"})
@deal.post(lambda r: r is None or r["agent"] in {"document", "research", "communication"})
def _contract_resolve_runtime_goal_gap_stage(
    output_mode: str,
    artifact_format: str,
    stage_has_document: bool,
    stage_has_research: bool,
    stage_has_communication: bool,
    previous_status: str,
    previous_agent: str,
    has_result_material: bool,
    evidence_level: str,
    delivery_required: bool,
):
    stage_ids = ["live_lookup_scan"]
    stage_agents = ["executor"]
    if stage_has_document:
        stage_ids.append("document_output")
        stage_agents.append("document")
    if stage_has_research:
        stage_ids.append("research_discovery")
        stage_agents.append("research")
    if stage_has_communication:
        stage_ids.append("communication_output")
        stage_agents.append("communication")
    return resolve_runtime_goal_gap_stage(
        {
            "output_mode": output_mode,
            "artifact_format": artifact_format,
            "evidence_level": evidence_level,
            "delivery_required": delivery_required,
        },
        current_stage_ids=stage_ids,
        current_stage_agents=stage_agents,
        previous_stage_status=previous_status,
        previous_stage_agent=previous_agent,
        has_result_material=has_result_material,
    )


@given(
    st.sampled_from(["artifact", "table", "answer", "message"]),
    st.sampled_from(["", "txt", "xlsx"]),
    st.booleans(),
    st.booleans(),
    st.booleans(),
    st.sampled_from(["success", "error", "skipped"]),
    st.sampled_from(["executor", "research", "visual", "document"]),
    st.booleans(),
    st.sampled_from(["light", "verified", "deep"]),
    st.booleans(),
)
@settings(max_examples=80)
def test_hypothesis_runtime_goal_gap_replan_shape(
    output_mode: str,
    artifact_format: str,
    stage_has_document: bool,
    stage_has_research: bool,
    stage_has_communication: bool,
    previous_status: str,
    previous_agent: str,
    has_result_material: bool,
    evidence_level: str,
    delivery_required: bool,
):
    result = _contract_resolve_runtime_goal_gap_stage(
        output_mode,
        artifact_format,
        stage_has_document,
        stage_has_research,
        stage_has_communication,
        previous_status,
        previous_agent,
        has_result_material,
        evidence_level,
        delivery_required,
    )
    if result is not None:
        assert result["stage_id"] in {"document_output", "verification_output", "communication_output"}
