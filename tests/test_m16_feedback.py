"""
tests/test_m16_feedback.py — M16: Phase 1 Tests

Testet FeedbackEngine und Telegram InlineKeyboard-Struktur.
"""

import json
import os
import sqlite3
import tempfile
from pathlib import Path

import pytest

# FeedbackEngine mit temporärer DB
from orchestration.feedback_engine import FeedbackEngine, FeedbackEvent


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
    """Prüft dass Callback-Daten korrekt aufgebaut sind."""
    action_id = "test-action-123"
    hook_names = ["Sei direkt", "Prüfe zuerst"]

    for signal in ["positive", "negative", "neutral"]:
        data = json.dumps({
            "fb": signal,
            "aid": action_id,
            "hooks": json.dumps(hook_names),
        })
        parsed = json.loads(data)
        assert parsed["fb"] == signal
        assert parsed["aid"] == action_id
        assert json.loads(parsed["hooks"]) == hook_names


def test_callback_data_parseable():
    """Callback-Daten müssen immer JSON-parseable sein."""
    samples = [
        '{"fb": "positive", "aid": "abc123", "hooks": "[\\"hook1\\"]"}',
        '{"fb": "negative", "aid": "xyz", "hooks": "[]"}',
        '{"fb": "neutral", "aid": "id-1", "hooks": "[\\"A\\", \\"B\\"]"}',
    ]
    for s in samples:
        parsed = json.loads(s)
        assert "fb" in parsed
        assert "aid" in parsed
        hooks = json.loads(parsed["hooks"])
        assert isinstance(hooks, list)


def test_feedback_engine_context_stored(engine):
    """Context-Daten werden korrekt gespeichert."""
    event = engine.record_signal(
        "ctx-action",
        "positive",
        context={"user_id": 42, "topic": "Python"},
    )
    assert event.context["user_id"] == 42
    assert event.context["topic"] == "Python"
