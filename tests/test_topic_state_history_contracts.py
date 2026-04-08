from __future__ import annotations

from typing import Any

import deal

from orchestration.conversation_state import decay_conversation_state
from orchestration.topic_state_history import (
    normalize_topic_history,
    parse_historical_topic_recall_hint,
    select_historical_topic_memory,
)


@deal.post(lambda r: isinstance(r["requested"], bool))
@deal.post(lambda r: isinstance(r["time_label"], str) and bool(r["time_label"]))
@deal.post(lambda r: 0.0 <= float(r["min_age_days"]) <= float(r["max_age_days"]))
@deal.post(lambda r: isinstance(r["focus_terms"], list))
def _contract_parse_historical_topic_recall_hint(query: str) -> dict[str, Any]:
    return parse_historical_topic_recall_hint(query).to_dict()


@deal.pre(lambda entries, limit: limit >= 1)
@deal.post(lambda r: all(bool(str(item["topic"]).strip()) for item in r))
@deal.post(lambda r: len({str(item["topic"]) for item in r}) == len(r))
@deal.post(lambda r: all(str(item["status"]) in {"active", "historical", "stale", "closed"} for item in r))
def _contract_normalize_topic_history(entries: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    return [item.to_dict() for item in normalize_topic_history(entries, session_id="contract_d08", limit=limit, now="2026-04-08T12:00:00Z")]


@deal.pre(lambda entries, query, limit: limit >= 1)
@deal.post(lambda r: len(r["selected"]) == len(r["selected_details"]))
@deal.post(lambda r: int(r["history_size"]) >= 0)
@deal.post(lambda r: isinstance(r["requested"], bool))
def _contract_select_historical_topic_memory(entries: list[dict[str, Any]], query: str, limit: int) -> dict[str, Any]:
    _, summary = select_historical_topic_memory(
        entries,
        session_id="contract_d08",
        query=query,
        now="2026-04-08T12:00:00Z",
        limit=limit,
    )
    return summary


@deal.post(lambda r: isinstance(r["applied"], bool))
@deal.post(lambda r: float(r["age_hours"]) >= 0.0)
@deal.post(lambda r: not r["applied"] or len(r["reasons"]) > 0)
def _contract_decay_conversation_state(payload: dict[str, Any]) -> dict[str, Any]:
    _, summary = decay_conversation_state(
        payload,
        session_id="contract_d08",
        now="2026-04-08T12:00:00Z",
    )
    return summary


def test_contract_parse_historical_topic_recall_hint_accepts_recent_moment() -> None:
    result = _contract_parse_historical_topic_recall_hint("weisst du noch was ich eben gesagt habe")
    assert result["requested"] is True
    assert result["time_label"] == "recent_moment"


def test_contract_parse_historical_topic_recall_hint_accepts_multi_year_range() -> None:
    result = _contract_parse_historical_topic_recall_hint(
        "weisst du noch was wir vor 3 jahren ueber die agentenarchitektur besprochen hatten"
    )
    assert result["requested"] is True
    assert result["time_label"] == "year_scale"
    assert float(result["min_age_days"]) >= 800.0


def test_contract_normalize_topic_history_returns_unique_topics() -> None:
    result = _contract_normalize_topic_history(
        [
            {
                "topic": "Mars und KI",
                "goal": "Einordnung",
                "open_loop": "",
                "next_expected_step": "",
                "status": "active",
                "first_seen_at": "2026-04-08T10:00:00Z",
                "last_seen_at": "2026-04-08T10:00:00Z",
                "closed_at": "",
                "topic_confidence": 0.8,
                "turn_type_hint": "new_task",
            },
            {
                "topic": "Mars und KI",
                "goal": "Spaeterer Stand",
                "open_loop": "",
                "next_expected_step": "",
                "status": "closed",
                "first_seen_at": "2026-04-07T10:00:00Z",
                "last_seen_at": "2026-04-08T11:00:00Z",
                "closed_at": "2026-04-08T11:00:00Z",
                "topic_confidence": 0.9,
                "turn_type_hint": "followup",
            },
        ],
        4,
    )
    assert len(result) == 1


def test_contract_select_historical_topic_memory_has_consistent_lengths() -> None:
    summary = _contract_select_historical_topic_memory(
        [
            {
                "topic": "Agentenarchitektur",
                "goal": "Meta und Spezialisten sauber trennen",
                "open_loop": "",
                "next_expected_step": "",
                "status": "closed",
                "first_seen_at": "2025-09-01T10:00:00Z",
                "last_seen_at": "2025-10-01T10:00:00Z",
                "closed_at": "2025-10-01T10:00:00Z",
                "topic_confidence": 0.9,
                "turn_type_hint": "new_task",
            }
        ],
        "weisst du noch was wir vor 6 monaten ueber die agentenarchitektur besprochen hatten",
        2,
    )
    assert len(summary["selected"]) == len(summary["selected_details"])


def test_contract_decay_conversation_state_produces_non_negative_age() -> None:
    summary = _contract_decay_conversation_state(
        {
            "active_topic": "aktuelle Weltlage",
            "active_goal": "brauchbare Live-News",
            "open_loop": "Reuters zuerst pruefen",
            "next_expected_step": "Reuters zuerst pruefen",
            "updated_at": "2026-04-01T10:00:00Z",
            "topic_confidence": 0.9,
        }
    )
    assert summary["age_hours"] >= 0.0
