from __future__ import annotations

from orchestration.meta_context_authority import (
    build_meta_context_authority,
    parse_meta_context_authority,
)


def test_build_meta_context_authority_for_docs_direct_answer() -> None:
    authority = build_meta_context_authority(
        meta_request_frame={
            "frame_kind": "direct_answer",
            "task_domain": "docs_status",
            "execution_mode": "answer_directly",
            "primary_objective": "lies docs/PHASE_F_PLAN.md und sag was als naechstes ansteht",
        },
        meta_interaction_mode={
            "mode": "inspect",
            "mode_reason": "task_domain:docs_status",
        },
        meta_clarity_contract={
            "primary_objective": "lies docs/PHASE_F_PLAN.md und sag was als naechstes ansteht",
            "request_kind": "direct_recommendation",
            "direct_answer_required": True,
            "allowed_context_slots": [
                "current_query",
                "conversation_state",
                "open_loop",
                "recent_user_turn",
                "historical_topic_memory",
            ],
            "forbidden_context_slots": [
                "topic_memory",
                "preference_memory",
                "semantic_recall",
                "assistant_fallback_context",
            ],
            "allowed_working_memory_sections": ["KURZZEITKONTEXT"],
            "max_related_memories": 0,
            "max_recent_events": 4,
        },
        meta_context_bundle={
            "context_slots": [
                {
                    "slot": "conversation_state",
                    "priority": 1,
                    "content": "active_topic: Phase F",
                    "source": "conversation_state",
                    "evidence_class": "conversation_state",
                },
                {
                    "slot": "historical_topic_memory",
                    "priority": 2,
                    "content": "Frueherer Planstand zu Phase F",
                    "source": "topic_history",
                    "evidence_class": "topic_state",
                },
            ]
        },
    )

    payload = authority.to_dict()
    assert payload["task_domain"] == "docs_status"
    assert payload["interaction_mode"] == "inspect"
    assert payload["request_kind"] == "direct_recommendation"
    assert payload["direct_answer_required"] is True
    assert payload["allowed_context_classes"] == ["conversation_state", "topic_state"]
    assert payload["forbidden_context_classes"] == [
        "topic_state",
        "preference_profile",
        "semantic_recall",
        "assistant_fallback",
    ]
    assert payload["observed_context_classes"] == ["conversation_state", "topic_state"]
    assert payload["context_class_counts"] == {"conversation_state": 1, "topic_state": 1}
    assert payload["primary_evidence_class"] == "conversation_state"
    assert payload["working_memory_query_mode"] == "evidence_bound"
    assert payload["working_memory_allowed_sections"] == ["KURZZEITKONTEXT"]
    assert payload["working_memory_max_related"] == 0
    assert payload["working_memory_max_recent"] == 4
    assert payload["strict_working_memory_gating"] is True


def test_parse_meta_context_authority_normalizes_payload() -> None:
    parsed = parse_meta_context_authority(
        {
            "schema_version": 1,
            "authority_chain": ["meta_request_frame", "meta_interaction_mode", "working_memory"],
            "primary_objective": "Plane meinen Tag",
            "frame_kind": "new_task",
            "task_domain": "planning_advisory",
            "execution_mode": "plan_and_delegate",
            "interaction_mode": "assist",
            "interaction_reason": "task_domain:planning_advisory",
            "request_kind": "execute_task",
            "direct_answer_required": False,
            "allowed_context_classes": ["conversation_state", "preference_profile"],
            "forbidden_context_classes": ["semantic_recall"],
            "observed_context_classes": ["conversation_state", "document_knowledge"],
            "context_class_counts": {"conversation_state": 1, "document_knowledge": 2},
            "primary_evidence_class": "document_knowledge",
            "allowed_context_slots": ["current_query", "conversation_state"],
            "working_memory_query_mode": "authority_bound",
            "working_memory_allowed_sections": ["KURZZEITKONTEXT"],
            "working_memory_max_related": 2,
            "working_memory_max_recent": 6,
            "strict_working_memory_gating": True,
            "rationale": "frame:new_task | domain:planning_advisory",
        }
    )

    assert parsed["interaction_mode"] == "assist"
    assert parsed["task_domain"] == "planning_advisory"
    assert parsed["allowed_context_classes"] == ["conversation_state", "preference_profile"]
    assert parsed["observed_context_classes"] == ["conversation_state", "document_knowledge"]
    assert parsed["context_class_counts"] == {"conversation_state": 1, "document_knowledge": 2}
    assert parsed["primary_evidence_class"] == "document_knowledge"
    assert parsed["working_memory_max_related"] == 2
    assert parsed["working_memory_max_recent"] == 6
