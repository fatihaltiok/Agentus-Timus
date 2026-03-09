"""
tests/test_m16_feedback.py — M16: Phase 1 Tests

Testet FeedbackEngine und Telegram InlineKeyboard-Struktur.
"""

import json
import sqlite3

import pytest

# FeedbackEngine mit temporärer DB
from orchestration.feedback_engine import (
    FeedbackEngine,
    clamp_feedback_target_score,
    feedback_evidence_confidence,
    next_feedback_target_score,
)
from utils.telegram_notify import build_feedback_callback_data, decode_feedback_signal


@pytest.fixture
def tmp_db(tmp_path):
    return tmp_path / "test_feedback.db"


@pytest.fixture
def engine(tmp_db):
    return FeedbackEngine(db_path=tmp_db)


# ──────────────────────────────────────────────────────────────────
# Grundlegende Operationen
# ──────────────────────────────────────────────────────────────────

def test_record_positive_signal(engine):
    event = engine.record_signal("action-1", "positive", hook_names=["Sei direkt"])
    assert event.signal == "positive"
    assert event.action_id == "action-1"
    assert "Sei direkt" in event.hook_names
    assert len(event.id) > 0


def test_record_negative_signal(engine):
    event = engine.record_signal("action-2", "negative", hook_names=["Sei vorsichtig"])
    assert event.signal == "negative"


def test_record_neutral_signal(engine):
    event = engine.record_signal("action-3", "neutral")
    assert event.signal == "neutral"
    assert event.hook_names == []


def test_invalid_signal_raises(engine):
    with pytest.raises(ValueError, match="Ungültiges Signal"):
        engine.record_signal("action-x", "unknown")


def test_event_persisted_in_db(engine, tmp_db):
    engine.record_signal("action-persist", "positive", hook_names=["Hook-A"])
    with sqlite3.connect(str(tmp_db)) as conn:
        rows = conn.execute("SELECT signal, hook_names FROM feedback_events").fetchall()
    assert len(rows) == 1
    assert rows[0][0] == "positive"
    hooks = json.loads(rows[0][1])
    assert "Hook-A" in hooks


def test_multiple_signals_persisted(engine):
    for i in range(5):
        engine.record_signal(f"action-{i}", "positive" if i % 2 == 0 else "negative")
    events = engine.get_recent_events(limit=10)
    assert len(events) == 5


# ──────────────────────────────────────────────────────────────────
# Hook-Statistiken
# ──────────────────────────────────────────────────────────────────

def test_hook_stats_empty(engine):
    stats = engine.get_hook_stats("NonExistentHook")
    assert stats["pos"] == 0
    assert stats["neg"] == 0
    assert stats["neutral"] == 0
    assert stats["weight"] == 1.0


def test_hook_stats_after_positive(engine):
    engine.record_signal("a1", "positive", hook_names=["hook-x"])
    engine.record_signal("a2", "positive", hook_names=["hook-x"])
    stats = engine.get_hook_stats("hook-x")
    assert stats["pos"] == 2
    assert stats["neg"] == 0
    assert stats["weight"] > 1.0


def test_hook_stats_after_negative(engine):
    engine.record_signal("a1", "negative", hook_names=["hook-y"])
    engine.record_signal("a2", "negative", hook_names=["hook-y"])
    stats = engine.get_hook_stats("hook-y")
    assert stats["neg"] == 2
    assert stats["weight"] < 1.0


def test_hook_stats_neutral_no_weight_change(engine):
    engine.record_signal("a1", "neutral", hook_names=["hook-z"])
    stats = engine.get_hook_stats("hook-z")
    # neutral zählt nicht für weight
    assert stats["neutral"] == 1
    assert stats["weight"] == 1.0


def test_weight_clamped_at_minimum(engine):
    # Sehr viele negative Signale
    for i in range(50):
        engine.record_signal(f"neg-{i}", "negative", hook_names=["hook-min"])
    stats = engine.get_hook_stats("hook-min")
    assert stats["weight"] >= 0.05


def test_weight_clamped_at_maximum(engine):
    # Sehr viele positive Signale
    for i in range(50):
        engine.record_signal(f"pos-{i}", "positive", hook_names=["hook-max"])
    stats = engine.get_hook_stats("hook-max")
    assert stats["weight"] <= 2.0


# ──────────────────────────────────────────────────────────────────
# process_pending / get_recent_events
# ──────────────────────────────────────────────────────────────────

def test_process_pending_returns_int(engine):
    count = engine.process_pending()
    assert isinstance(count, int)
    assert count >= 0


def test_get_recent_events_order(engine):
    engine.record_signal("first", "positive")
    engine.record_signal("second", "negative")
    events = engine.get_recent_events(limit=2)
    # Neuestes zuerst
    assert events[0].action_id == "second"
    assert events[1].action_id == "first"


def test_get_recent_events_limit(engine):
    for i in range(10):
        engine.record_signal(f"ev-{i}", "neutral")
    events = engine.get_recent_events(limit=3)
    assert len(events) == 3


# ──────────────────────────────────────────────────────────────────
# Telegram InlineKeyboard Struktur (Unit-Test ohne Bot)
# ──────────────────────────────────────────────────────────────────

def test_feedback_callback_data_structure():
    """Prüft dass Callback-Daten kompakt und korrekt aufgebaut sind."""
    token = "abc123token"

    for signal in ["positive", "negative", "neutral"]:
        data = build_feedback_callback_data(signal, token)
        parsed = json.loads(data)
        assert parsed["type"] == "feedback"
        assert decode_feedback_signal(parsed["s"]) == signal
        assert parsed["t"] == token
        assert len(data) <= 64


def test_callback_data_parseable():
    """Callback-Daten müssen immer JSON-parseable sein."""
    samples = [
        build_feedback_callback_data("positive", "abc123"),
        build_feedback_callback_data("negative", "xyz"),
        build_feedback_callback_data("neutral", "id1"),
    ]
    for s in samples:
        parsed = json.loads(s)
        assert parsed["type"] == "feedback"
        assert decode_feedback_signal(parsed["s"]) in {"positive", "negative", "neutral"}
        assert parsed["t"]


def test_feedback_engine_context_stored(engine):
    """Context-Daten werden korrekt gespeichert."""
    event = engine.record_signal(
        "ctx-action",
        "positive",
        context={"user_id": 42, "topic": "Python"},
    )
    assert event.context["user_id"] == 42
    assert event.context["topic"] == "Python"


def test_register_and_resolve_feedback_request(engine):
    token = engine.register_feedback_request(
        action_id="reply-1",
        hook_names=["ambient_trigger"],
        context={"source": "telegram_reply"},
        feedback_targets=[{"namespace": "dispatcher_agent", "key": "meta"}],
    )
    payload = engine.resolve_feedback_request(token)
    assert payload is not None
    assert payload.action_id == "reply-1"
    assert payload.context["source"] == "telegram_reply"
    assert payload.feedback_targets == [{"namespace": "dispatcher_agent", "key": "meta"}]


def test_feedback_target_scores_are_updated(engine):
    engine.record_signal(
        "reply-2",
        "positive",
        context={"dispatcher_agent": "meta"},
        feedback_targets=[
            {"namespace": "curiosity_topic", "key": "python"},
            {"namespace": "visual_strategy", "key": "ocr_text"},
            {"namespace": "reflection_pattern", "key": "direkt"},
        ],
    )
    assert engine.get_target_score("dispatcher_agent", "meta") > 1.0
    assert engine.get_target_score("curiosity_topic", "python") > 1.0
    assert engine.get_target_score("visual_strategy", "ocr_text") > 1.0
    assert engine.get_target_score("reflection_pattern", "direkt") > 1.0


def test_feedback_target_stats_track_evidence_counts(engine):
    for signal in ("positive", "negative", "neutral"):
        engine.record_signal(
            f"stats-{signal}",
            signal,
            feedback_targets=[{"namespace": "dispatcher_agent", "key": "meta"}],
        )

    stats = engine.get_target_stats("dispatcher_agent", "meta")

    assert stats["positive_count"] == 1
    assert stats["negative_count"] == 1
    assert stats["neutral_count"] == 1
    assert stats["evidence_count"] == 3


def test_effective_target_score_is_damped_until_enough_evidence(engine):
    engine.record_signal(
        "evidence-1",
        "positive",
        feedback_targets=[{"namespace": "dispatcher_agent", "key": "meta"}],
    )

    raw_score = engine.get_target_score("dispatcher_agent", "meta")
    effective_score = engine.get_effective_target_score("dispatcher_agent", "meta")

    assert raw_score == pytest.approx(1.1)
    assert effective_score == pytest.approx(1.02)

    for index in range(2, 6):
        engine.record_signal(
            f"evidence-{index}",
            "positive",
            feedback_targets=[{"namespace": "dispatcher_agent", "key": "meta"}],
        )

    assert engine.get_effective_target_score("dispatcher_agent", "meta") == pytest.approx(
        engine.get_target_score("dispatcher_agent", "meta")
    )


def test_feedback_target_score_clamps():
    assert clamp_feedback_target_score(-10) == 0.1
    assert clamp_feedback_target_score(99) == 3.0
    assert next_feedback_target_score(3.0, "positive") == 3.0
    assert next_feedback_target_score(0.1, "negative") == 0.1


def test_feedback_evidence_confidence_is_bounded():
    assert feedback_evidence_confidence(-5) == 0.0
    assert feedback_evidence_confidence(0) == 0.0
    assert feedback_evidence_confidence(2) == pytest.approx(0.4)
    assert feedback_evidence_confidence(5) == 1.0
    assert feedback_evidence_confidence(50) == 1.0


def test_record_runtime_outcome_uses_damped_weight(engine):
    event = engine.record_runtime_outcome(
        "runtime-1",
        success=True,
        context={"dispatcher_agent": "meta"},
        feedback_targets=[{"namespace": "dispatcher_agent", "key": "meta"}],
    )

    assert event.signal == "positive"
    assert event.context["feedback_source"] == "runtime_outcome"
    assert event.context["feedback_weight"] == pytest.approx(0.05)
    assert engine.get_target_score("dispatcher_agent", "meta") == pytest.approx(1.05)


def test_record_runtime_outcome_negative_updates_visual_strategy(engine):
    engine.record_runtime_outcome(
        "runtime-visual-1",
        success=False,
        context={"visual_strategy": "browser_flow"},
        feedback_targets=[{"namespace": "visual_strategy", "key": "browser_flow"}],
    )

    stats = engine.get_target_stats("visual_strategy", "browser_flow")
    assert stats["negative_count"] == 1
    assert stats["score"] == pytest.approx(0.95)
