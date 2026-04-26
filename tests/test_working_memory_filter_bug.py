"""Bug-Fix: filter_working_memory_context normalisiert Section-Header
mit Doppelpunkt korrekt.

Der Memory-Builder schreibt Section-Header als ``KURZZEITKONTEXT:\\n``
(mit Doppelpunkt), aber allowed_sections enthaelt nur ``KURZZEITKONTEXT``
(ohne Doppelpunkt). Der bisherige Filter verglich beide Seiten
ungetrimmt und warf damit ALLE erlaubten Sektionen raus → context_chars=0.

Dieser Test sichert: bei korrekt erlaubten Sektionen bleibt der Inhalt
erhalten.
"""

from __future__ import annotations

import sys
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from orchestration.meta_clarity_contract import filter_working_memory_context


_BUILDER_HEADER = (
    "WORKING_MEMORY_CONTEXT\n"
    "Nutze nur relevante Teile. Bei Konflikt gilt die aktuelle Nutzeranfrage."
)


def _builder_output_with_kurzzeit() -> str:
    """Reproduziert das exakte Format aus memory_system._build_budgeted_section."""
    return (
        f"{_BUILDER_HEADER}\n\n"
        "KURZZEITKONTEXT:\n"
        "- (2026-04-26T22:15:46) User: ich will ein Unternehmen gruenden | Timus: KI-Gruendung ist...\n"
        "- (2026-04-26T22:16:45) User: du kannst mich einschaetzen | Timus: Ich kann dich einschaetzen..."
    )


def _builder_output_with_two_sections() -> str:
    return (
        f"{_BUILDER_HEADER}\n\n"
        "KURZZEITKONTEXT:\n"
        "- (2026-04-26T22:15:46) User: q1 | Timus: a1\n\n"
        "LANGZEITKONTEXT:\n"
        "- [memory/source] earlier insight"
    )


# --- Bug-Reproduktion (rot vor Fix) -----------------------------------


def test_filter_keeps_kurzzeitkontext_with_colon():
    """Der Builder schreibt 'KURZZEITKONTEXT:' mit Doppelpunkt.
    allowed_sections enthaelt 'KURZZEITKONTEXT' ohne Doppelpunkt.
    Der Filter MUSS den Block trotzdem behalten.
    """
    context = _builder_output_with_kurzzeit()
    result = filter_working_memory_context(
        context,
        {"allowed_working_memory_sections": ["KURZZEITKONTEXT"]},
    )
    assert result, "Filter wirft KURZZEITKONTEXT-Block raus trotz allowed_section"
    assert "KURZZEITKONTEXT" in result
    assert "ich will ein Unternehmen gruenden" in result


def test_filter_keeps_both_sections_when_both_allowed():
    context = _builder_output_with_two_sections()
    result = filter_working_memory_context(
        context,
        {
            "allowed_working_memory_sections": [
                "KURZZEITKONTEXT",
                "LANGZEITKONTEXT",
            ]
        },
    )
    assert "KURZZEITKONTEXT" in result
    assert "LANGZEITKONTEXT" in result


def test_filter_drops_disallowed_section():
    context = _builder_output_with_two_sections()
    result = filter_working_memory_context(
        context,
        {"allowed_working_memory_sections": ["KURZZEITKONTEXT"]},
    )
    assert "KURZZEITKONTEXT" in result
    assert "LANGZEITKONTEXT" not in result


def test_filter_returns_empty_when_no_section_matches():
    context = _builder_output_with_kurzzeit()
    result = filter_working_memory_context(
        context,
        {"allowed_working_memory_sections": ["LANGZEITKONTEXT"]},
    )
    # KURZZEITKONTEXT war drin, aber nur LANGZEITKONTEXT erlaubt -> leer
    assert result == ""


def test_filter_no_contract_passes_through():
    context = _builder_output_with_kurzzeit()
    result = filter_working_memory_context(context, None)
    assert result == context.strip()


def test_filter_empty_allowed_sections_passes_through():
    context = _builder_output_with_kurzzeit()
    result = filter_working_memory_context(
        context, {"allowed_working_memory_sections": []}
    )
    # leere allowed-Liste = kein Filter
    assert result == context.strip()


def test_filter_handles_section_name_with_trailing_colon_in_allowed():
    """Auch wenn jemand 'KURZZEITKONTEXT:' (mit Doppelpunkt) als allowed
    angibt, soll der Filter es korrekt matchen.
    """
    context = _builder_output_with_kurzzeit()
    result = filter_working_memory_context(
        context,
        {"allowed_working_memory_sections": ["KURZZEITKONTEXT:"]},
    )
    assert "KURZZEITKONTEXT" in result


def test_filter_case_insensitive_match():
    context = _builder_output_with_kurzzeit()
    result = filter_working_memory_context(
        context,
        {"allowed_working_memory_sections": ["kurzzeitkontext"]},
    )
    assert "KURZZEITKONTEXT" in result


# --- End-to-end Smoke (mit echtem Builder) ---------------------------


def test_real_builder_output_passes_filter_with_kurzzeit_allowed():
    """End-to-end: build_working_memory_context -> filter_working_memory_context
    soll context_chars > 0 liefern, wenn KURZZEITKONTEXT erlaubt ist und
    Events vorhanden sind.

    Dieser Test ist als Smoke gedacht: er nutzt vorhandene DB-Events.
    Wenn die DB leer ist, ist context_chars=0 erwartet (kein Bug).
    """
    from memory.memory_system import memory_manager

    # Suche eine Session mit mind. 1 Event
    import sqlite3
    conn = sqlite3.connect("data/timus_memory.db")
    rows = conn.execute(
        "SELECT session_id, COUNT(*) c FROM interaction_events "
        "GROUP BY session_id HAVING c >= 2 ORDER BY MAX(id) DESC LIMIT 1"
    ).fetchall()
    conn.close()
    if not rows:
        # Nichts in der DB -> Test wird uebersprungen via assert
        return
    session_id = rows[0][0]

    raw_context = memory_manager.build_working_memory_context(
        "irgendeine query",
        4000, 2, 6,
        session_id,
        allowed_sections=("KURZZEITKONTEXT", "LANGZEITKONTEXT"),
        allowed_context_classes=("conversation_state", "topic_state"),
        query_mode="objective_only",
    )
    # Builder muss Inhalt liefern
    if not raw_context:
        return  # kann legitim leer sein

    filtered = filter_working_memory_context(
        raw_context,
        {"allowed_working_memory_sections": ["KURZZEITKONTEXT", "LANGZEITKONTEXT"]},
    )
    # Bug-Reproduktion: filtered war 0 vor dem Fix
    assert filtered, (
        "Filter loescht den gesamten Builder-Output trotz erlaubter Sections "
        "(Section-Header-Doppelpunkt-Bug)"
    )
