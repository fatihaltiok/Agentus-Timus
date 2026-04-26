"""CCF6: Live-Gate-Snapshot-Tests.

Sichern den end-to-end-Pfad gegen Regressionen, ohne dass die Tests
einen laufenden Stack brauchen. Sie pruefen die Klassifikations- und
Authority-Outputs fuer die 6 Pflichtfaelle.

Hintergrund: bei den echten Live-Tests am 2026-04-26 wurden alle 6
Faelle korrekt geroutet, ohne Drift auf skill-creator, generic_help
oder Setup. Diese Snapshot-Tests sichern dass sich das Verhalten
nicht still aendert.
"""

from __future__ import annotations

import sys
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from orchestration.meta_orchestration import classify_meta_task


_ADVISORY_STATE = {
    "active_topic": "Unternehmensgruendung mit KI",
    "active_goal": "Startansatz mit vorhandenen Faehigkeiten finden",
    "active_domain": "topic_advisory",
    "open_loop": "Was sind deine Skills, Ressourcen und Interessen?",
    "next_expected_step": "Skills nennen",
    "turn_type_hint": "followup",
    "topic_confidence": 0.7,
}


_RECENT_USERS = [
    "ich will ein unternehmen gruenden mit ki und brauche einen startansatz",
]
_RECENT_ASSISTANTS = [
    "Was bringst du mit? Sag mir in 2-3 Saetzen, was du gut kannst.",
]


def _drift_free(result: dict) -> bool:
    """Prueft, dass die Klassifikation nicht in falsche Domain driftet."""
    forbidden_domains = {"skill_creation", "setup_build", "location_route"}
    frame = result.get("meta_request_frame") or {}
    return frame.get("task_domain") not in forbidden_domains


# --- 6 Pflichtfaelle als Snapshot --------------------------------------


def test_g1_initial_advisory_no_drift():
    result = classify_meta_task(
        _RECENT_USERS[0],
        action_count=0,
    )
    assert _drift_free(result)
    chain = result.get("recommended_agent_chain") or []
    assert chain[:1] == ["meta"]


def test_g2_personal_assessment_unlocks_profile():
    """G2: 'du kannst mich einschaetzen' soll preference_profile freigeben."""
    result = classify_meta_task(
        "du kannst mich ungefaehr einschaetzen was passt zu mir",
        action_count=0,
        recent_user_turns=_RECENT_USERS,
        recent_assistant_turns=_RECENT_ASSISTANTS,
        conversation_state=_ADVISORY_STATE,
    )
    assert _drift_free(result)
    gate = result.get("personal_assessment_gate") or {}
    assert gate.get("is_personal_assessment") is True
    authority = result.get("meta_context_authority") or {}
    assert "preference_profile" in (authority.get("allowed_context_classes") or [])


def test_g3_recall_question_finds_anchor():
    """G3: 'worueber hatte ich dich eben gebeten' bekommt Deictic-Hit."""
    result = classify_meta_task(
        "worueber hatte ich dich eben gebeten",
        action_count=0,
        recent_user_turns=_RECENT_USERS,
        recent_assistant_turns=_RECENT_ASSISTANTS,
        conversation_state=_ADVISORY_STATE,
    )
    assert _drift_free(result)
    deictic = result.get("deictic_reference") or {}
    assert deictic.get("has_reference") is True
    assert deictic.get("reference_kind") == "recall"


def test_g4_self_problem_resolves_to_anchor():
    """G4: 'kannst du dieses problem beheben' wird als self_problem
    erkannt, mit Anker auf last_assistant.
    """
    result = classify_meta_task(
        "kannst du dieses problem beheben",
        action_count=0,
        recent_user_turns=_RECENT_USERS,
        recent_assistant_turns=_RECENT_ASSISTANTS,
        conversation_state=_ADVISORY_STATE,
    )
    assert _drift_free(result)
    deictic = result.get("deictic_reference") or {}
    assert deictic.get("has_reference") is True
    assert deictic.get("reference_kind") == "self_problem"


def test_g5_constraint_update_stays_in_advisory_thread():
    """G5: kurzer Constraint 'ich kann gut programmieren' soll im
    Beratungsthread bleiben, nicht auf neue Domain driften.
    """
    result = classify_meta_task(
        "ich kann gut programmieren und mag b2b saas",
        action_count=0,
        recent_user_turns=_RECENT_USERS,
        recent_assistant_turns=_RECENT_ASSISTANTS,
        conversation_state=_ADVISORY_STATE,
    )
    assert _drift_free(result)
    chain = result.get("recommended_agent_chain") or []
    assert chain[:1] == ["meta"]


def test_g6_neutral_topic_does_not_session_followup():
    """G6: brandneue Session, neutraler Topic ('wetter') darf keinen
    session:followup-Tag tragen und nicht im Advisory-Frame landen.
    """
    result = classify_meta_task(
        "wie ist das wetter morgen in muenchen",
        action_count=0,
    )
    authority = result.get("meta_context_authority") or {}
    rationale = authority.get("rationale") or ""
    # Keine session:followup-Markierung in einer frischen, unrelated Anfrage.
    assert "session:followup" not in rationale
    # Personal-Assessment darf nicht ausloesen.
    gate = result.get("personal_assessment_gate") or {}
    assert gate.get("is_personal_assessment") is False


# --- Sammelassertion ueber alle 6 -----------------------------------


def test_all_gates_no_drift_to_skill_or_setup():
    queries = [
        _RECENT_USERS[0],
        "du kannst mich ungefaehr einschaetzen was passt zu mir",
        "worueber hatte ich dich eben gebeten",
        "kannst du dieses problem beheben",
        "ich kann gut programmieren und mag b2b saas",
        "wie ist das wetter morgen in muenchen",
    ]
    for q in queries:
        result = classify_meta_task(
            q,
            action_count=0,
            recent_user_turns=_RECENT_USERS,
            recent_assistant_turns=_RECENT_ASSISTANTS,
            conversation_state=_ADVISORY_STATE,
        )
        assert _drift_free(result), f"Drift bei query: {q[:60]}"
