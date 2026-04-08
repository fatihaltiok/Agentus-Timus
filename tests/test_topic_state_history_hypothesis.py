from __future__ import annotations

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from orchestration.conversation_state import decay_conversation_state
from orchestration.topic_state_history import (
    normalize_topic_history,
    parse_historical_topic_recall_hint,
    select_historical_topic_memory,
)


_TIMESTAMPS = st.sampled_from(
    [
        "2026-04-08T10:00:00Z",
        "2026-04-07T10:00:00Z",
        "2026-04-01T10:00:00Z",
        "2026-02-01T10:00:00Z",
        "2025-10-01T10:00:00Z",
        "2025-04-01T10:00:00Z",
    ]
)

_TOPIC_TEXT = st.text(
    alphabet=st.characters(
        whitelist_categories=("L", "N", "Zs"),
        blacklist_characters=("\n", "\r", "\t"),
    ),
    min_size=1,
    max_size=60,
).map(str.strip).filter(bool)

_STATUS = st.sampled_from(["active", "historical", "stale", "closed", "weird-status"])


def _history_entry_strategy():
    return st.fixed_dictionaries(
        {
            "topic": _TOPIC_TEXT,
            "goal": st.text(min_size=0, max_size=80),
            "open_loop": st.text(min_size=0, max_size=80),
            "next_expected_step": st.text(min_size=0, max_size=80),
            "status": _STATUS,
            "first_seen_at": _TIMESTAMPS,
            "last_seen_at": _TIMESTAMPS,
            "closed_at": st.one_of(st.just(""), _TIMESTAMPS),
            "topic_confidence": st.floats(min_value=0.0, max_value=1.0, allow_nan=False),
            "turn_type_hint": st.sampled_from(["", "new_task", "followup", "behavior_instruction"]),
        }
    )


_HISTORICAL_QUERY = st.sampled_from(
    [
        "kannst du dich an unser gespraech von eben erinnern",
        "greif das thema von gestern nochmal auf",
        "weisst du noch was wir letzte woche dazu besprochen hatten",
        "was hatten wir vor 6 monaten dazu besprochen",
        "weisst du noch was wir vor 18 monaten ueber timus besprochen hatten",
        "weisst du noch was wir vor einem jahr ueber timus besprochen hatten",
        "weisst du noch was wir vor 3 jahren ueber timus besprochen hatten",
    ]
)


@given(
    entries=st.lists(_history_entry_strategy(), min_size=0, max_size=20),
    limit=st.integers(min_value=1, max_value=8),
)
@settings(max_examples=160, suppress_health_check=[HealthCheck.too_slow])
def test_hypothesis_normalize_topic_history_keeps_unique_topics_and_limit(entries, limit):
    normalized = normalize_topic_history(
        entries,
        session_id="canvas_d08_hyp",
        limit=limit,
        now="2026-04-08T12:00:00Z",
    )

    assert len(normalized) <= limit
    topics = [entry.topic for entry in normalized]
    assert all(topic.strip() for topic in topics)
    assert len(topics) == len(set(topics))
    assert all(entry.status in {"active", "historical", "stale", "closed"} for entry in normalized)


@given(
    entries=st.lists(_history_entry_strategy(), min_size=0, max_size=20),
    query=_HISTORICAL_QUERY,
    limit=st.integers(min_value=1, max_value=4),
)
@settings(max_examples=120, suppress_health_check=[HealthCheck.too_slow])
def test_hypothesis_select_historical_topic_memory_is_bounded(entries, query, limit):
    selected, summary = select_historical_topic_memory(
        entries,
        session_id="canvas_d08_hyp",
        query=query,
        now="2026-04-08T12:00:00Z",
        limit=limit,
    )

    assert len(selected) <= limit
    assert len(summary["selected_details"]) == len(selected)
    assert summary["history_size"] >= 0
    assert isinstance(summary["requested"], bool)
    if selected:
        assert summary["requested"] is True


@given(query=_HISTORICAL_QUERY)
@settings(max_examples=50)
def test_hypothesis_parse_historical_topic_recall_hint_produces_valid_ranges(query):
    hint = parse_historical_topic_recall_hint(query)

    assert isinstance(hint.requested, bool)
    assert hint.min_age_days >= 0.0
    assert hint.max_age_days >= hint.min_age_days
    assert isinstance(hint.time_label, str) and bool(hint.time_label)


@given(
    confidence=st.floats(min_value=0.0, max_value=1.0, allow_nan=False),
    include_open_loop=st.booleans(),
    include_questions=st.booleans(),
)
@settings(max_examples=120, suppress_health_check=[HealthCheck.too_slow])
def test_hypothesis_decay_conversation_state_never_increases_confidence(
    confidence: float,
    include_open_loop: bool,
    include_questions: bool,
):
    original = {
        "active_topic": "Timus und Agentenarchitektur",
        "active_goal": "naechsten Ausbau planen",
        "open_loop": "naechsten Schritt definieren" if include_open_loop else "",
        "next_expected_step": "naechsten Schritt definieren" if include_open_loop else "",
        "open_questions": ["was ist der naechste schritt?"] if include_questions else [],
        "topic_confidence": confidence,
        "updated_at": "2026-04-01T10:00:00Z",
    }

    decayed, summary = decay_conversation_state(
        original,
        session_id="canvas_d08_hyp",
        now="2026-04-08T12:00:00Z",
    )

    assert decayed.topic_confidence <= confidence
    assert summary["age_hours"] >= 0.0
    if summary["applied"]:
        assert summary["reasons"]
