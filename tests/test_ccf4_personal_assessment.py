"""CCF4: Tests fuer das Personal Assessment Gate."""

from __future__ import annotations

import sys
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from orchestration.personal_assessment_gate import detect_personal_assessment


# --- Detector ---------------------------------------------------------


def test_personal_assessment_du_kannst_mich_einschaetzen():
    result = detect_personal_assessment("du kannst mich ungefaehr einschaetzen was passt zu mir")
    assert result.is_personal_assessment is True
    assert result.confidence >= 0.7


def test_personal_assessment_was_passt_zu_mir():
    result = detect_personal_assessment("was passt zu mir")
    assert result.is_personal_assessment is True


def test_personal_assessment_mit_meinen_faehigkeiten():
    result = detect_personal_assessment(
        "wie koennte ich mit meinen Faehigkeiten ein KI-Startup aufbauen"
    )
    assert result.is_personal_assessment is True


def test_personal_assessment_umlaut_handling():
    """Umlauts müssen normalisiert werden."""
    a = detect_personal_assessment("du kannst mich einschätzen")
    b = detect_personal_assessment("du kannst mich einschaetzen")
    assert a.is_personal_assessment == b.is_personal_assessment is True


def test_personal_assessment_neutral_query_no_trigger():
    result = detect_personal_assessment("wie ist das wetter morgen")
    assert result.is_personal_assessment is False
    assert result.confidence == 0.0


def test_personal_assessment_empty_query():
    result = detect_personal_assessment("")
    assert result.is_personal_assessment is False


def test_personal_assessment_factual_question_no_trigger():
    """Faktfrage darf nicht als Personalisierung erkannt werden."""
    result = detect_personal_assessment("was ist die hauptstadt von frankreich")
    assert result.is_personal_assessment is False


# --- Authority-Integration --------------------------------------------


def test_authority_unlocks_preference_profile_when_personal_assessment():
    """build_meta_context_authority muss bei is_personal_assessment=True
    preference_profile in allowed_context_classes haben.
    """
    from orchestration.meta_context_authority import build_meta_context_authority

    authority = build_meta_context_authority(
        meta_request_frame={
            "frame_kind": "clarify_needed",
            "task_domain": "topic_advisory",
            "execution_mode": "answer_directly",
            "primary_objective": "Persoenliche Einschaetzung geben",
            "allowed_context_slots": [
                "current_query",
                "conversation_state",
            ],
        },
        meta_interaction_mode={"mode": "think_partner"},
        meta_clarity_contract={
            "allowed_context_slots": [
                "current_query",
                "conversation_state",
                "preference_memory",
            ],
            "forbidden_context_slots": [],
            "max_related_memories": 2,
            "max_recent_events": 6,
        },
        meta_context_bundle={
            "context_slots": [
                {"slot": "conversation_state", "evidence_class": "conversation_state"},
                {"slot": "preference_memory", "evidence_class": "preference_profile"},
            ]
        },
        general_decision_kernel={
            "turn_kind": "think",
            "topic_family": "advisory",
            "interaction_mode": "think_partner",
            "evidence_requirement": "none",
            "execution_permission": "forbidden",
            "confidence": 0.85,
            "answer_ready": False,
        },
        is_personal_assessment=True,
    )
    payload = authority.to_dict()
    assert "preference_profile" in payload["allowed_context_classes"]
    assert "preference_profile" not in payload["forbidden_context_classes"]


def test_authority_locks_preference_profile_without_assessment():
    """Ohne is_personal_assessment bleibt preference_profile bei
    forbidden execution_permission gesperrt.
    """
    from orchestration.meta_context_authority import build_meta_context_authority

    authority = build_meta_context_authority(
        meta_request_frame={
            "frame_kind": "clarify_needed",
            "task_domain": "topic_advisory",
            "execution_mode": "answer_directly",
            "primary_objective": "Allgemeine Frage",
        },
        meta_interaction_mode={"mode": "think_partner"},
        meta_clarity_contract={
            "allowed_context_slots": ["current_query", "conversation_state"],
            "max_related_memories": 0,
            "max_recent_events": 4,
        },
        meta_context_bundle={
            "context_slots": [
                {"slot": "conversation_state", "evidence_class": "conversation_state"},
            ]
        },
        general_decision_kernel={
            "turn_kind": "think",
            "topic_family": "advisory",
            "interaction_mode": "think_partner",
            "evidence_requirement": "none",
            "execution_permission": "forbidden",
            "confidence": 0.85,
            "answer_ready": False,
        },
        is_personal_assessment=False,
    )
    payload = authority.to_dict()
    assert "preference_profile" in payload["forbidden_context_classes"]


# --- classify_meta_task Integration ----------------------------------


def test_classify_meta_task_emits_personal_assessment_gate():
    from orchestration.meta_orchestration import classify_meta_task

    result = classify_meta_task(
        "du kannst mich ungefaehr einschaetzen was passt zu mir",
        action_count=0,
    )
    gate = result.get("personal_assessment_gate") or {}
    assert gate.get("is_personal_assessment") is True


def test_classify_meta_task_no_assessment_for_neutral_query():
    from orchestration.meta_orchestration import classify_meta_task

    result = classify_meta_task("wie ist das wetter morgen in berlin", action_count=0)
    gate = result.get("personal_assessment_gate") or {}
    assert gate.get("is_personal_assessment") is False


def test_classify_meta_task_assessment_unlocks_profile_in_authority():
    """Bei explizitem du-kannst-mich-einschaetzen-Query muss authority
    preference_profile freigeben.
    """
    from orchestration.meta_orchestration import classify_meta_task

    result = classify_meta_task(
        "du kannst mich ungefaehr einschaetzen was passt zu mir",
        action_count=0,
        recent_user_turns=["ich will ein Unternehmen gruenden mit KI"],
        recent_assistant_turns=["Was bringst du mit?"],
        conversation_state={
            "active_topic": "Unternehmensgruendung mit KI",
            "active_goal": "Skills nennen",
            "active_domain": "topic_advisory",
            "open_loop": "Skills nennen",
            "next_expected_step": "Skills nennen",
            "turn_type_hint": "followup",
        },
    )
    authority = result.get("meta_context_authority") or {}
    allowed_classes = authority.get("allowed_context_classes") or []
    assert "preference_profile" in allowed_classes
