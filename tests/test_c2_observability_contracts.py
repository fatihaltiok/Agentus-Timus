"""C2 CrossHair-Contracts für pure Observability-Funktionen.

Contracts auf build_incident_trace und _classify_user_impact_event.
Kein IO, kein Dateiscan — nur reine Logik.
"""
from __future__ import annotations

import sys
from pathlib import Path

import deal

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from orchestration.autonomy_observation import (
    _USER_IMPACT_EVENT_TYPES,
    _classify_user_impact_event,
    build_incident_trace,
)

_KNOWN_CLASSES = _USER_IMPACT_EVENT_TYPES | {"none"}


# ---------------------------------------------------------------------------
# Contracts als deal-dekorierte Funktionen (CrossHair-kompatibel)
# ---------------------------------------------------------------------------

@deal.pre(lambda events, request_id: isinstance(events, list))
@deal.pre(lambda events, request_id: isinstance(request_id, str))
@deal.post(lambda result: isinstance(result, list))
@deal.post(lambda result: all(isinstance(e, dict) for e in result))
def _contract_build_incident_trace_returns_list(events: list, request_id: str) -> list:
    return build_incident_trace(events, request_id)


@deal.post(lambda result: result in _KNOWN_CLASSES)
def _contract_classify_returns_known_class(event_type: str) -> str:
    return _classify_user_impact_event(event_type)


@deal.post(lambda result: result == [])
def _contract_blank_request_id_yields_empty(_: list) -> list:
    return build_incident_trace(_, "")


# ---------------------------------------------------------------------------
# pytest-Tests die die Contracts aufrufen
# ---------------------------------------------------------------------------

def test_contract_build_incident_trace_returns_list():
    events = [
        {"id": "a", "observed_at": "2026-04-05T10:00:00", "event_type": "chat_request_received",
         "payload": {"request_id": "req-1"}},
    ]
    result = _contract_build_incident_trace_returns_list(events, "req-1")
    assert isinstance(result, list)


def test_contract_build_incident_trace_empty_input():
    result = _contract_build_incident_trace_returns_list([], "req-1")
    assert result == []


def test_contract_classify_known_types():
    for event_type in _USER_IMPACT_EVENT_TYPES:
        result = _contract_classify_returns_known_class(event_type)
        assert result in _KNOWN_CLASSES


def test_contract_classify_unknown_returns_none():
    result = _contract_classify_returns_known_class("chat_request_failed")
    assert result == "none"


def test_contract_blank_request_id_yields_empty():
    events = [{"id": "a", "observed_at": "2026-04-05T10:00:00", "event_type": "x", "payload": {"request_id": "req-1"}}]
    result = _contract_blank_request_id_yields_empty(events)
    assert result == []
