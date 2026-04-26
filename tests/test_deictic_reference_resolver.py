"""CCF3: Tests fuer den Deictic Reference Resolver."""

from __future__ import annotations

import sys
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from orchestration.deictic_reference_resolver import (
    parse_deictic_reference_resolution,
    resolve_deictic_reference,
)


# --- Empty / No-Reference Cases ---------------------------------------


def test_no_reference_returns_empty_resolution():
    result = resolve_deictic_reference(query="wie ist das wetter morgen")
    assert result.has_reference is False
    assert result.reference_kind == ""
    assert result.confidence == 0.0


def test_empty_query_returns_empty_resolution():
    result = resolve_deictic_reference(query="")
    assert result.has_reference is False


def test_neutral_question_no_anchor_returns_empty():
    result = resolve_deictic_reference(
        query="was ist die hauptstadt von frankreich",
        active_topic="ki beratung",
    )
    assert result.has_reference is False


# --- Self-Problem Pattern --------------------------------------------


def test_self_problem_pattern_resolves_to_last_assistant():
    """`kannst du dieses Problem beheben` nach Beschwerde ueber Timus
    soll auf den letzten Assistant-Turn binden.
    """
    result = resolve_deictic_reference(
        query="kannst du dieses Problem beheben",
        last_assistant=(
            "Ich kann die vorherige Anfrage im aktuellen Kontext nicht "
            "sehen - der Conversation-State ist hier abgeschnitten."
        ),
        active_topic="Unternehmensgruendung",
    )
    assert result.has_reference is True
    assert result.reference_kind == "self_problem"
    assert result.confidence >= 0.7
    assert "Conversation-State" in result.resolved_reference
    assert result.source_anchor == "last_assistant"
    # Bei hoher Confidence: KEIN Fallback erlaubt
    assert result.fallback_question == ""


def test_self_problem_without_anchor_offers_fallback():
    result = resolve_deictic_reference(
        query="kannst du dieses Problem beheben",
    )
    assert result.has_reference is True
    assert result.reference_kind == "self_problem"
    assert result.confidence < 0.5
    # Niedrige Confidence: Fallback-Frage erlaubt, aber spezifischer als
    # "Welches Problem?" alleine.
    assert "Problem" in result.fallback_question


# --- Explicit Recall Pattern -----------------------------------------


def test_explicit_recall_resolves_to_last_user_turn():
    """`worueber hatte ich dich eben gebeten` bindet an last_user."""
    result = resolve_deictic_reference(
        query="worueber hatte ich dich eben gebeten",
        last_user=(
            "ich will ein unternehmen gruenden und ki soll eine rolle spielen"
        ),
        active_topic="Unternehmensgruendung mit KI",
    )
    assert result.has_reference is True
    assert result.reference_kind == "recall"
    assert result.confidence >= 0.7
    assert "unternehmen" in result.resolved_reference.lower()
    # Bei hoher Confidence: KEIN Fallback
    assert result.fallback_question == ""


def test_explicit_recall_without_anchor_offers_fallback():
    result = resolve_deictic_reference(
        query="worueber hatte ich dich eben gebeten",
    )
    assert result.has_reference is True
    assert result.reference_kind == "recall"
    assert result.confidence < 0.5
    assert result.fallback_question != ""


# --- Generic Deictic Pattern -----------------------------------------


def test_generic_dafuer_with_open_loop_resolves():
    result = resolve_deictic_reference(
        query="du weisst doch wofuer",
        open_loop="Vorschlaege fuer den Frankfurt-Ausflug",
        active_topic="Frankfurt Wochenende",
    )
    assert result.has_reference is True
    assert result.reference_kind == "thread_carry"
    assert result.confidence >= 0.7
    assert "Frankfurt" in result.resolved_reference
    assert result.source_anchor == "open_loop"


def test_generic_dieses_thema_resolves_to_active_topic():
    result = resolve_deictic_reference(
        query="erzaehl mir mehr ueber dieses Thema",
        active_topic="KI-Startups in Deutschland",
    )
    assert result.has_reference is True
    assert result.reference_kind == "thread_carry"
    assert result.confidence >= 0.7
    assert "KI-Startups" in result.resolved_reference


def test_generic_without_anchor_offers_fallback():
    result = resolve_deictic_reference(query="erzaehl mir mehr ueber dieses Thema")
    assert result.has_reference is True
    assert result.confidence < 0.5
    assert result.fallback_question != ""


# --- Anchor Priority --------------------------------------------------


def test_anchor_priority_open_loop_beats_active_topic():
    """Generic deictic mit beiden Ankern: open_loop gewinnt."""
    result = resolve_deictic_reference(
        query="dafuer brauche ich noch mehr Info",
        open_loop="Skills und Ressourcen klaeren",
        active_topic="Unternehmensgruendung",
    )
    assert result.source_anchor == "open_loop"
    assert "Skills" in result.resolved_reference


def test_recall_priority_last_user_beats_open_loop():
    """Recall: last_user ist wichtiger als open_loop."""
    result = resolve_deictic_reference(
        query="worueber hatte ich dich gerade gefragt",
        open_loop="Was sind deine Skills?",
        last_user="erstelle mir bitte einen Plan fuer die Hochzeit",
    )
    assert result.source_anchor == "last_user"
    assert "Hochzeit" in result.resolved_reference


# --- Confidence Threshold --------------------------------------------


def test_high_confidence_blocks_clarification_question():
    """Wenn Confidence hoch und Anker da: kein Fallback erlaubt.
    Das ist die Bedingung dafuer, dass Meta nicht 'Welches Problem?'
    erneut fragen darf.
    """
    result = resolve_deictic_reference(
        query="kannst du dieses Problem beheben",
        last_assistant="Ich habe vergessen worum es ging.",
    )
    assert result.confidence >= 0.7
    assert result.fallback_question == ""


# --- parse_deictic_reference_resolution -----------------------------


def test_parse_dict_roundtrip():
    result = resolve_deictic_reference(
        query="dieses thema",
        active_topic="KI-Startups",
    )
    parsed = parse_deictic_reference_resolution(result.to_dict())
    assert parsed["has_reference"] == result.has_reference
    assert parsed["reference_kind"] == result.reference_kind
    assert parsed["resolved_reference"] == result.resolved_reference
    assert parsed["confidence"] == result.confidence


def test_parse_handles_none():
    parsed = parse_deictic_reference_resolution(None)
    assert parsed["has_reference"] is False
    assert parsed["confidence"] == 0.0


def test_parse_handles_empty():
    parsed = parse_deictic_reference_resolution({})
    assert parsed["has_reference"] is False


# --- Normalization (umlauts) -----------------------------------------


def test_umlauts_normalize_correctly():
    """`worüber` (mit Umlaut) muss genauso funktionieren wie `worueber`."""
    result_with_umlaut = resolve_deictic_reference(
        query="worüber hatte ich dich eben gebeten",
        last_user="meine Hauptfrage",
    )
    result_ascii = resolve_deictic_reference(
        query="worueber hatte ich dich eben gebeten",
        last_user="meine Hauptfrage",
    )
    assert result_with_umlaut.has_reference is True
    assert result_ascii.has_reference is True
    assert result_with_umlaut.reference_kind == result_ascii.reference_kind
