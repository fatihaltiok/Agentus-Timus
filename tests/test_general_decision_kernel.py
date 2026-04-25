from __future__ import annotations

from orchestration.general_decision_kernel import (
    build_general_decision_kernel,
    parse_general_decision_kernel,
)


def test_build_general_decision_kernel_for_docs_status() -> None:
    kernel = build_general_decision_kernel(
        effective_query="lies docs/PHASE_F_PLAN.md und sag was als naechstes ansteht",
        meta_request_frame={
            "frame_kind": "direct_answer",
            "task_domain": "docs_status",
            "execution_mode": "answer_directly",
            "confidence": 0.82,
        },
        meta_interaction_mode={
            "mode": "inspect",
            "mode_reason": "task_domain:docs_status",
            "explicit_override": False,
        },
    ).to_dict()

    assert kernel["turn_kind"] == "inspect"
    assert kernel["topic_family"] == "document"
    assert kernel["evidence_requirement"] == "bounded"
    assert kernel["execution_permission"] == "bounded"
    assert kernel["clarify_if_below_threshold"] is False


def test_build_general_decision_kernel_for_travel_think_partner() -> None:
    kernel = build_general_decision_kernel(
        effective_query="wo kann ich am Wochenende hin in Deutschland",
        meta_request_frame={
            "frame_kind": "new_task",
            "task_domain": "travel_advisory",
            "execution_mode": "plan_and_delegate",
            "confidence": 0.71,
        },
        meta_interaction_mode={
            "mode": "think_partner",
            "mode_reason": "task_domain:travel_advisory",
            "explicit_override": False,
        },
    ).to_dict()

    assert kernel["turn_kind"] == "think"
    assert kernel["topic_family"] == "travel"
    assert kernel["evidence_requirement"] == "none"
    assert kernel["execution_permission"] == "forbidden"


def test_build_general_decision_kernel_for_research_advisory() -> None:
    kernel = build_general_decision_kernel(
        effective_query="mach dich schlau ueber Kreislaufwirtschaft im Bau und hilf mir dann",
        meta_request_frame={
            "frame_kind": "new_task",
            "task_domain": "research_advisory",
            "execution_mode": "plan_and_delegate",
            "confidence": 0.69,
        },
        meta_interaction_mode={
            "mode": "inspect",
            "mode_reason": "task_domain:research_advisory",
            "explicit_override": False,
        },
    ).to_dict()

    assert kernel["turn_kind"] == "research"
    assert kernel["topic_family"] == "general_knowledge"
    assert kernel["evidence_requirement"] == "research"
    assert kernel["execution_permission"] == "bounded"


def test_parse_general_decision_kernel_roundtrip() -> None:
    parsed = parse_general_decision_kernel(
        {
            "schema_version": 1,
            "turn_kind": "inspect",
            "topic_family": "document",
            "interaction_mode": "inspect",
            "evidence_requirement": "bounded",
            "execution_permission": "bounded",
            "confidence": 0.78,
            "clarify_if_below_threshold": False,
            "rationale": "turn_kind:inspect | topic_family:document",
            "evidence": ["frame:direct_answer", "mode:inspect", "domain:docs_status"],
        }
    )

    assert parsed["turn_kind"] == "inspect"
    assert parsed["topic_family"] == "document"
    assert parsed["interaction_mode"] == "inspect"
    assert parsed["evidence_requirement"] == "bounded"
    assert parsed["execution_permission"] == "bounded"
    assert parsed["confidence"] == 0.78
