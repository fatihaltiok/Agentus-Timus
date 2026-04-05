"""C2 Observability: Hypothesis-Tests für pure Funktionen.

Getestet wird ausschliesslich auf pure Funktionen (build_incident_trace,
_classify_user_impact_event) — kein IO, kein Store, kein Dateiscan.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from orchestration.autonomy_observation import (
    _USER_IMPACT_EVENT_TYPES,
    _classify_user_impact_event,
    build_incident_trace,
    summarize_autonomy_events,
)


# ---------------------------------------------------------------------------
# Hilfsfunktionen
# ---------------------------------------------------------------------------

def _make_event(event_type: str, request_id: str = "", observed_at: str = "2026-04-05T10:00:00") -> dict:
    return {
        "id": "test",
        "observed_at": observed_at,
        "event_type": event_type,
        "payload": {"request_id": request_id},
    }


# ---------------------------------------------------------------------------
# build_incident_trace — Filterinvarianten
# ---------------------------------------------------------------------------

def test_blank_request_id_returns_empty():
    """Leere request_id → leere Liste, keine Exception."""
    events = [_make_event("chat_request_received", "req-1")]
    assert build_incident_trace(events, "") == []
    assert build_incident_trace(events, "  ") == []


def test_no_matching_events_returns_empty():
    """Keine passenden Events → leere Liste."""
    events = [_make_event("chat_request_received", "req-other")]
    assert build_incident_trace(events, "req-1") == []


def test_non_dict_events_are_ignored():
    """Heterogene Listen duerfen den Trace-Builder nicht crashen."""
    events = [
        _make_event("chat_request_received", "req-1"),
        "\x00",
        123,
        None,
    ]
    trace = build_incident_trace(events, "req-1")
    assert len(trace) == 1
    assert trace[0]["event_type"] == "chat_request_received"


def test_matching_event_appears_in_trace():
    """Event mit matching request_id taucht im Trace auf."""
    events = [
        _make_event("chat_request_received", "req-1"),
        _make_event("dispatcher_route_selected", "req-1"),
        _make_event("chat_request_completed", "req-2"),
    ]
    trace = build_incident_trace(events, "req-1")
    assert len(trace) == 2
    assert all(e["payload"]["request_id"] == "req-1" for e in trace)


def test_trace_contains_only_matching_events():
    """Trace enthält ausschliesslich Events mit der angegebenen request_id."""
    events = [
        _make_event("chat_request_received", "req-A"),
        _make_event("chat_request_failed", "req-B"),
        _make_event("dispatcher_route_selected", "req-A"),
    ]
    trace = build_incident_trace(events, "req-A")
    for e in trace:
        assert e["payload"]["request_id"] == "req-A"


def test_trace_length_bounded_by_input():
    """Trace-Länge ≤ Eingabelänge (strukturelle Filterinvariante)."""
    events = [_make_event("chat_request_received", f"req-{i}") for i in range(10)]
    trace = build_incident_trace(events, "req-3")
    assert len(trace) <= len(events)


def test_trace_sorted_chronologically():
    """Trace ist chronologisch sortiert nach observed_at."""
    events = [
        _make_event("chat_request_completed", "req-1", "2026-04-05T10:02:00"),
        _make_event("dispatcher_route_selected", "req-1", "2026-04-05T10:01:00"),
        _make_event("chat_request_received", "req-1", "2026-04-05T10:00:00"),
    ]
    trace = build_incident_trace(events, "req-1")
    timestamps = [e["observed_at"] for e in trace]
    assert timestamps == sorted(timestamps)


def test_empty_events_list_returns_empty():
    """Leere Event-Liste → leere Trace, unabhängig von request_id."""
    assert build_incident_trace([], "req-1") == []


@given(
    n=st.integers(min_value=0, max_value=50),
    target=st.text(min_size=1, max_size=20, alphabet=st.characters(whitelist_categories=("Ll", "Lu", "Nd"), whitelist_characters="-_")),
)
@settings(max_examples=200)
def test_trace_length_le_input_property(n: int, target: str):
    """Property: len(trace) <= len(events) für beliebige Inputs."""
    events = [_make_event("chat_request_received", target if i % 2 == 0 else "other") for i in range(n)]
    trace = build_incident_trace(events, target)
    assert len(trace) <= len(events)


@given(
    request_id=st.text(min_size=1, max_size=40),
    n_matching=st.integers(min_value=0, max_value=20),
    n_other=st.integers(min_value=0, max_value=20),
)
@settings(max_examples=200)
def test_trace_only_contains_target_request_id(request_id: str, n_matching: int, n_other: int):
    """Property: Alle Events im Trace haben exakt die gesuchte request_id."""
    matching = [_make_event("chat_request_received", request_id) for _ in range(n_matching)]
    others = [_make_event("chat_request_received", request_id + "_other") for _ in range(n_other)]
    events = matching + others
    trace = build_incident_trace(events, request_id)
    # build_incident_trace stripped beim Vergleich, gibt aber Originalwerte zurück.
    # Deshalb .strip() auf beiden Seiten.
    for e in trace:
        assert e["payload"]["request_id"].strip() == request_id.strip()


# ---------------------------------------------------------------------------
# _classify_user_impact_event — abgeschlossene Wertemenge
# ---------------------------------------------------------------------------

KNOWN_CLASSES = _USER_IMPACT_EVENT_TYPES | {"none"}


def test_known_impact_types_classified_correctly():
    """Bekannte Klassen werden korrekt erkannt."""
    for event_type in _USER_IMPACT_EVENT_TYPES:
        assert _classify_user_impact_event(event_type) == event_type


def test_unknown_event_type_returns_none():
    """Unbekannte Event-Typen → 'none'."""
    for unknown in ("chat_request_failed", "meta_recipe_outcome", "", "anything"):
        assert _classify_user_impact_event(unknown) == "none"


@given(event_type=st.text(max_size=80))
@settings(max_examples=500)
def test_classify_always_returns_known_class(event_type: str):
    """Property: Rückgabe ist immer aus der bekannten Menge."""
    result = _classify_user_impact_event(event_type)
    assert result in KNOWN_CLASSES


# ---------------------------------------------------------------------------
# summarize_autonomy_events — user_impact Block
# ---------------------------------------------------------------------------

def test_user_impact_block_present_in_summary():
    """user_impact-Block ist im Summary vorhanden."""
    summary = summarize_autonomy_events([])
    assert "user_impact" in summary
    ui = summary["user_impact"]
    assert "response_never_delivered_total" in ui
    assert "silent_failure_total" in ui
    assert "user_visible_timeout_total" in ui
    assert "misroute_recovered_total" in ui
    assert "recent_impacts" in ui


def test_user_impact_does_not_affect_user_visible_failures_total():
    """user_impact-Events erhöhen user_visible_failures_total NICHT."""
    events = [
        {
            "id": "x",
            "observed_at": "2026-04-05T10:00:00",
            "event_type": "user_visible_timeout",
            "payload": {"request_id": "req-1", "session_id": "s1"},
        },
        {
            "id": "y",
            "observed_at": "2026-04-05T10:01:00",
            "event_type": "silent_failure",
            "payload": {"request_id": "req-2", "session_id": "s1"},
        },
    ]
    summary = summarize_autonomy_events(events)
    # user_impact-Events dürfen user_visible_failures_total nicht hochzählen
    assert summary["request_correlation"]["user_visible_failures_total"] == 0
    # aber den eigenen Block schon
    assert summary["user_impact"]["user_visible_timeout_total"] == 1
    assert summary["user_impact"]["silent_failure_total"] == 1


def test_user_impact_counts_correct_per_type():
    """Jeder Impact-Typ wird separat gezählt."""
    events = []
    for event_type in _USER_IMPACT_EVENT_TYPES:
        for _ in range(3):
            events.append({
                "id": "x",
                "observed_at": "2026-04-05T10:00:00",
                "event_type": event_type,
                "payload": {},
            })
    summary = summarize_autonomy_events(events)
    ui = summary["user_impact"]
    for event_type in _USER_IMPACT_EVENT_TYPES:
        assert ui[f"{event_type}_total"] == 3


def test_recent_impacts_capped_at_limit():
    """recent_impacts wird auf _RECENT_CORRELATION_LIMIT begrenzt."""
    events = [
        {
            "id": f"e{i}",
            "observed_at": f"2026-04-05T10:{i:02d}:00",
            "event_type": "silent_failure",
            "payload": {},
        }
        for i in range(20)
    ]
    summary = summarize_autonomy_events(events)
    assert len(summary["user_impact"]["recent_impacts"]) <= 8


def test_unknown_event_type_not_counted_in_user_impact():
    """chat_request_failed ist kein user_impact-Event."""
    events = [{
        "id": "x",
        "observed_at": "2026-04-05T10:00:00",
        "event_type": "chat_request_failed",
        "payload": {"error_class": "test"},
    }]
    summary = summarize_autonomy_events(events)
    ui = summary["user_impact"]
    assert ui["response_never_delivered_total"] == 0
    assert ui["silent_failure_total"] == 0
    assert ui["user_visible_timeout_total"] == 0
    assert ui["misroute_recovered_total"] == 0
