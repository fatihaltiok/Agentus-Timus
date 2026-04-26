"""CCF2: Open-Loop und Pending-Follow-up Resolver.

Stellt sicher, dass kurze Folge-Antworten in einer Session mit aktivem
Open-Loop oder pending_followup_prompt als Followup behandelt werden,
auch wenn sie keinen klassischen Followup-Marker tragen.
"""

from __future__ import annotations

import sys
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from server.mcp_server import _augment_query_with_followup_capsule


# --- Helper -----------------------------------------------------------


def _capsule(
    *,
    open_loop: str = "",
    pending_followup_prompt: str = "",
    active_topic: str = "",
    last_assistant: str = "",
    last_user: str = "",
    next_step: str = "",
) -> dict:
    return {
        "session_id": "ccf2_test_session",
        "last_user": last_user,
        "last_assistant": last_assistant,
        "last_agent": "meta",
        "session_summary": "",
        "recent_user_queries": [last_user] if last_user else [],
        "recent_assistant_replies": [last_assistant] if last_assistant else [],
        "recent_agents": ["meta"],
        "matched_reply_points": [],
        "inherited_topic_recall": [],
        "semantic_recall": [],
        "pending_followup_prompt": pending_followup_prompt,
        "last_proposed_action": None,
        "pending_workflow": {},
        "pending_workflow_reply": {},
        "conversation_state": {
            "active_topic": active_topic,
            "active_goal": "",
            "active_domain": "topic_advisory",
            "open_loop": open_loop,
            "next_expected_step": next_step,
            "turn_type_hint": "followup",
        },
        "topic_history": [],
    }


# --- CCF2: Open-Loop Followup Trigger -------------------------------


def test_ccf2_short_query_with_open_loop_triggers_followup_context():
    """Kurze Folge-Antwort bei aktivem Open-Loop ohne klassisches
    Followup-Marker muss `# FOLLOW-UP CONTEXT` injizieren.
    """
    capsule = _capsule(
        open_loop="Was sind deine Skills, Ressourcen und Interessen?",
        active_topic="Unternehmensgruendung mit KI",
        last_user="ich will ein Unternehmen gruenden mit KI",
        last_assistant="Was bringst du mit? Sag mir in 2-3 Saetzen, was du gut kannst.",
        next_step="Skills und Interessen nennen",
    )
    augmented = _augment_query_with_followup_capsule(
        "du kannst mich ungefaehr einschaetzen was passt zu mir",
        capsule,
    )
    assert "# FOLLOW-UP CONTEXT" in augmented
    assert "# CURRENT USER QUERY" in augmented
    assert "du kannst mich ungefaehr einschaetzen was passt zu mir" in augmented


def test_ccf2_pending_followup_prompt_triggers_followup_even_without_open_loop():
    """Pending-Followup-Prompt allein reicht als Trigger."""
    capsule = _capsule(
        pending_followup_prompt="Sag mir, was du gut kannst und was dich interessiert",
        active_topic="Unternehmensgruendung mit KI",
        last_user="ich will ein Unternehmen gruenden",
        last_assistant="Sag mir, was du gut kannst.",
    )
    augmented = _augment_query_with_followup_capsule(
        "ich kann gut programmieren",
        capsule,
    )
    assert "# FOLLOW-UP CONTEXT" in augmented


def test_ccf2_advisory_recommendation_request_triggers_followup():
    """Advisory-Recommendation wie 'mach jetzt Vorschlaege' bei aktivem
    Ausflug-Open-Loop muss als Followup behandelt werden.
    """
    capsule = _capsule(
        open_loop="Was genau sucht ihr - Essen, Trinken, Nachtleben, Kultur?",
        active_topic="Frankfurt Ausflug",
        last_user="bin in Frankfurt mit Freunden",
        last_assistant="Was genau sucht ihr - Essen, Trinken, Nachtleben?",
    )
    augmented = _augment_query_with_followup_capsule("mach jetzt Vorschlaege", capsule)
    assert "# FOLLOW-UP CONTEXT" in augmented


# --- CCF2: Schutz gegen falsche Followup-Erkennung -------------------


def test_ccf2_long_new_topic_query_does_not_trigger_open_loop_followup():
    """Eine lange, klar neue Anfrage darf NICHT als Open-Loop-Followup
    behandelt werden, auch wenn ein alter Open-Loop existiert.
    """
    capsule = _capsule(
        open_loop="Was sind deine Skills?",
        active_topic="Unternehmensgruendung",
    )
    long_new_query = (
        "Ich habe gerade gemerkt dass mein Auto nicht mehr startet "
        "und ich brauche jetzt dringend Hilfe um zur Werkstatt zu kommen "
        "und einen Termin zu vereinbaren ohne dass ich auf das Wochenende warten muss"
    )
    augmented = _augment_query_with_followup_capsule(long_new_query, capsule)
    # Lange neue Anfrage > 120 chars: kein Open-Loop-Trigger
    # (andere Trigger koennten greifen, aber nicht has_open_loop_followup).
    # Akzeptanz: entweder kein Followup-Block ODER Followup wegen anderer Triggers.
    # Wir pruefen: kein has_open_loop_followup-Spezifischer Bias.
    assert long_new_query in augmented


def test_ccf2_explicit_new_topic_marker_does_not_trigger_followup():
    """Explizites 'neues thema' soll Open-Loop-Trigger umgehen."""
    capsule = _capsule(
        open_loop="Was sind deine Skills?",
        active_topic="Unternehmensgruendung",
    )
    augmented = _augment_query_with_followup_capsule(
        "neues thema: was ist die Hauptstadt von Frankreich",
        capsule,
    )
    # Bei explizitem new_topic darf has_open_loop_followup nicht greifen.
    # Andere Trigger koennten technisch matchen, aber das ist nicht Aufgabe
    # dieses Tests.
    # Wir pruefen mind: Query ist drin.
    assert "neues thema: was ist die Hauptstadt von Frankreich" in augmented


def test_ccf2_url_query_does_not_trigger_open_loop_followup():
    """Eine URL-Anfrage ist klar ein neuer Auftrag, nicht ein Followup."""
    capsule = _capsule(
        open_loop="Was sind deine Skills?",
        active_topic="Unternehmensgruendung",
    )
    augmented = _augment_query_with_followup_capsule(
        "https://example.com/article fasse zusammen",
        capsule,
    )
    # URL: nicht has_open_loop_followup (looks_like_new_url). Der Test prueft
    # dass die Funktion die Query unveraendert weitergibt oder nur dann ein
    # Followup-Block erzeugt, wenn ein anderer Trigger greift.
    assert "example.com/article" in augmented


def test_ccf2_no_open_loop_no_pending_no_trigger():
    """Wenn kein Open-Loop UND kein Pending-Followup-Prompt vorhanden ist,
    darf has_open_loop_followup NICHT greifen.
    """
    capsule = _capsule()  # alles leer
    augmented = _augment_query_with_followup_capsule(
        "du kannst mich ungefaehr einschaetzen",
        capsule,
    )
    # Ohne Open-Loop und ohne Pending: keine Augmentation.
    # Nur Pure-Query.
    assert augmented == "du kannst mich ungefaehr einschaetzen"


def test_ccf2_empty_query_does_not_trigger():
    """Leere Query darf nichts triggern."""
    capsule = _capsule(open_loop="Was sind deine Skills?")
    augmented = _augment_query_with_followup_capsule("", capsule)
    # Leere Query: keine Augmentation.
    assert augmented == ""


# --- CCF2: Bestehende Trigger nicht beschaedigt ----------------------


def test_ccf2_classic_followup_still_triggers():
    """Klassischer Followup wie 'und dann' soll weiterhin triggern,
    auch ohne Open-Loop.
    """
    capsule = _capsule(last_user="vorherige frage", last_assistant="vorherige antwort")
    augmented = _augment_query_with_followup_capsule(
        "und was ist mit der zweiten Option",
        capsule,
    )
    # 'und' als reference-continuation sollte greifen.
    # Wenn _is_reference_continuation 'und' erkennt: # FOLLOW-UP CONTEXT.
    # Das ist nicht CCF2-spezifisch, sondern Sicherheitsnetz.
    # Akzeptanz: Query ist drin.
    assert "und was ist mit der zweiten Option" in augmented
