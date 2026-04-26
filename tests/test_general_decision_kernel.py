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


def test_build_general_decision_kernel_for_current_news_lookup() -> None:
    kernel = build_general_decision_kernel(
        effective_query="Zeig mir aktuelle News zu OpenAI.",
        dominant_turn_type="followup",
        response_mode="clarify_before_execute",
        meta_request_frame={
            "frame_kind": "clarify_needed",
            "task_domain": "topic_advisory",
            "execution_mode": "clarify_once",
            "confidence": 0.7,
        },
        meta_interaction_mode=None,
    ).to_dict()

    assert kernel["turn_kind"] == "inspect"
    assert kernel["interaction_mode"] == "inspect"
    assert kernel["evidence_requirement"] == "bounded"
    assert kernel["execution_permission"] == "bounded"
    assert "query:live_lookup" in kernel["evidence"]


def test_build_general_decision_kernel_for_short_resume_update() -> None:
    kernel = build_general_decision_kernel(
        effective_query="Wetter sonnig Zeit ganzen Tag lokale Ecken",
        dominant_turn_type="new_task",
        response_mode="execute",
        active_topic="Frankfurt am Main",
        open_goal="Hey Timus ich bin in Frankfurt sitze am Main was könnte ich heute machen",
        next_step="Wetter? Zeit? Was fuer Ecken?",
        active_domain="topic_advisory",
        recent_user_turns=["Hey Timus ich bin in Frankfurt sitze am Main was könnte ich heute machen"],
        meta_request_frame=None,
        meta_interaction_mode=None,
    ).to_dict()

    assert kernel["turn_kind"] == "constraint_update"
    assert kernel["topic_family"] == "advisory"
    assert kernel["interaction_mode"] == "think_partner"
    assert kernel["evidence_requirement"] == "state_bound"
    assert kernel["execution_permission"] == "forbidden"
    assert kernel["confidence"] >= 0.78
    assert kernel["answer_ready"] is False
    assert "Wetter sonnig Zeit ganzen Tag lokale Ecken" in kernel["constraint_summary"]
    assert "query:constraint_update" in kernel["evidence"]


def test_build_general_decision_kernel_marks_advisory_followup_ready_for_answer() -> None:
    kernel = build_general_decision_kernel(
        effective_query="was kannst du mir für das nächste Wochenende empfehlen",
        dominant_turn_type="followup",
        response_mode="resume_open_loop",
        active_topic="einen Ausflug mit Kultur",
        open_goal="ich hab Lust einen Ausflug zu machen",
        next_step="Was ist dir bei Kultur wichtiger – Museen oder Architektur?",
        active_domain="travel_advisory",
        recent_user_turns=[
            "ich hab Lust einen Ausflug zu machen",
            "am Wochenende in Ruhe Stadt",
            "einen Ausflug mit Kultur",
        ],
        meta_request_frame=None,
        meta_interaction_mode=None,
    ).to_dict()

    assert kernel["turn_kind"] == "inform"
    assert kernel["interaction_mode"] == "think_partner"
    assert kernel["execution_permission"] == "forbidden"
    assert kernel["answer_ready"] is True
    assert "am Wochenende in Ruhe Stadt" in kernel["constraint_summary"]
    assert "einen Ausflug mit Kultur" in kernel["constraint_summary"]
    assert "state:answer_ready" in kernel["evidence"]


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
            "answer_ready": False,
            "constraint_summary": "am Wochenende in Ruhe Stadt | einen Ausflug mit Kultur",
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
    assert parsed["answer_ready"] is False
    assert parsed["constraint_summary"] == "am Wochenende in Ruhe Stadt | einen Ausflug mit Kultur"
