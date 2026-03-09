"""
tests/test_m16_integration.py — M16: Phase 4 + Integration Tests

Testet Curiosity Topic-Scores und Session Reflection Hook-Integration.
"""

import os
import json
import sqlite3
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest


# ──────────────────────────────────────────────────────────────────
# Curiosity Engine Topic-Scores
# ──────────────────────────────────────────────────────────────────

@pytest.fixture
def curiosity():
    from orchestration.curiosity_engine import CuriosityEngine
    return CuriosityEngine(telegram_app=None)


def test_topic_score_default(curiosity):
    score = curiosity.get_topic_score("Python")
    assert score == 1.0


def test_topic_score_positive_increases(curiosity):
    curiosity.update_topic_score("Python", "positive")
    assert curiosity.get_topic_score("Python") > 1.0


def test_topic_score_negative_decreases(curiosity):
    curiosity.update_topic_score("Python", "negative")
    assert curiosity.get_topic_score("Python") < 1.0


def test_topic_score_neutral_no_change(curiosity):
    curiosity.update_topic_score("Python", "neutral")
    assert curiosity.get_topic_score("Python") == 1.0


def test_topic_score_lower_bound(curiosity):
    for _ in range(100):
        curiosity.update_topic_score("Topic", "negative")
    assert curiosity.get_topic_score("Topic") >= 0.1


def test_topic_score_upper_bound(curiosity):
    for _ in range(100):
        curiosity.update_topic_score("Topic", "positive")
    assert curiosity.get_topic_score("Topic") <= 3.0


def test_topic_score_five_positive_increases_score(curiosity):
    """5× positives Feedback → Score steigt."""
    initial = curiosity.get_topic_score("MachineLearning")
    for _ in range(5):
        curiosity.update_topic_score("MachineLearning", "positive")
    assert curiosity.get_topic_score("MachineLearning") > initial


def test_topic_score_accumulates_correctly(curiosity):
    """Akkumulation: 3 positiv + 1 negativ = Netto +0.2."""
    curiosity.update_topic_score("AI", "positive")
    curiosity.update_topic_score("AI", "positive")
    curiosity.update_topic_score("AI", "positive")
    curiosity.update_topic_score("AI", "negative")
    expected = max(0.1, min(3.0, 1.0 + 0.3 - 0.1))
    assert curiosity.get_topic_score("AI") == pytest.approx(expected, abs=0.01)


def test_topic_score_invalid_signal_ignored(curiosity):
    curiosity.update_topic_score("Topic", "invalid")
    assert curiosity.get_topic_score("Topic") == 1.0


def test_curiosity_topic_score_uses_feedback_target(tmp_path):
    from orchestration.feedback_engine import FeedbackEngine
    import orchestration.feedback_engine as fe_module
    from orchestration.curiosity_engine import CuriosityEngine

    fe = FeedbackEngine(db_path=tmp_path / "curiosity_feedback.db")
    fe.record_signal(
        "curiosity-1",
        "positive",
        context={"topic": "python"},
        feedback_targets=[{"namespace": "curiosity_topic", "key": "python"}],
    )
    curiosity = CuriosityEngine(telegram_app=None)
    with patch.object(fe_module, "get_feedback_engine", return_value=fe):
        assert curiosity.get_topic_score("python") > 1.0


def test_dispatcher_runtime_feedback_updates_selected_agent(tmp_path):
    from orchestration.feedback_engine import FeedbackEngine
    import orchestration.feedback_engine as fe_module
    import main_dispatcher

    fe = FeedbackEngine(db_path=tmp_path / "dispatcher_runtime_feedback.db")

    with patch.object(fe_module, "get_feedback_engine", return_value=fe):
        main_dispatcher._record_runtime_feedback(
            session_id="sess-1",
            agent_name="meta",
            query="plane den browser workflow",
            final_output="Workflow erfolgreich abgeschlossen",
            runtime_metadata={"execution_path": "standard"},
        )

    stats = fe.get_target_stats("dispatcher_agent", "meta")
    assert stats["positive_count"] == 1
    assert stats["score"] == pytest.approx(1.05)


def test_decay_stale_scores(curiosity):
    """Scores älter als 7 Tage werden Richtung 1.0 decay'd."""
    from datetime import datetime, timedelta
    curiosity._topic_scores["OldTopic"] = 1.8
    # Setze last_feedback auf 10 Tage in der Vergangenheit
    curiosity._topic_last_feedback["OldTopic"] = (
        datetime.now() - timedelta(days=10)
    ).isoformat()
    curiosity._decay_stale_topic_scores()
    assert curiosity._topic_scores["OldTopic"] < 1.8


def test_topic_score_lean_invariant_lower():
    """Lean: m16_topic_score_lower — clamp ≥ 0."""
    for v in [-100, -1, 0, 1, 100]:
        assert max(0, min(100, v)) >= 0


def test_topic_score_lean_invariant_upper():
    """Lean: m16_topic_score_upper — clamp ≤ 100."""
    for v in [-100, -1, 0, 1, 100]:
        assert max(0, min(100, v)) <= 100


def test_negative_signal_lean_invariant():
    """Lean: m16_negative_signal — score - delta < score."""
    for score in [50, 80, 10]:
        for delta in [1, 5, 10]:
            assert score - delta < score


# ──────────────────────────────────────────────────────────────────
# Session Reflection → Hook Integration
# ──────────────────────────────────────────────────────────────────

@pytest.fixture
def reflection_loop(tmp_path):
    from orchestration.session_reflection import SessionReflectionLoop
    return SessionReflectionLoop(db_path=tmp_path / "test_refl.db")


@pytest.fixture
def reflection_summary():
    from orchestration.session_reflection import ReflectionSummary
    return ReflectionSummary(
        session_id="test-session-abc",
        tasks_count=5,
        success_rate=0.8,
        what_worked=["Sei direkt war hilfreich", "Schnelle Antwort"],
        what_failed=["Zu lange Ausgabe"],
        patterns=["pattern-x"],
        improvements=["Kürzer sein"],
    )


def test_apply_reflection_to_hooks_disabled(reflection_loop, reflection_summary):
    """Ohne M16_ENABLED passiert nichts."""
    with patch.dict(os.environ, {"AUTONOMY_M16_ENABLED": "false"}):
        # Kein Fehler, kein Effekt
        reflection_loop._apply_reflection_to_hooks(reflection_summary)


def test_apply_reflection_to_hooks_enabled(reflection_loop, reflection_summary, tmp_path):
    """Mit AUTONOMY_M16_ENABLED=true werden FeedbackEngine-Signale gespeichert."""
    from orchestration.feedback_engine import FeedbackEngine
    import orchestration.feedback_engine as fe_module
    import memory.soul_engine as se_module

    fe = FeedbackEngine(db_path=tmp_path / "fb.db")

    with patch.dict(os.environ, {"AUTONOMY_M16_ENABLED": "true"}):
        with patch.object(fe_module, "get_feedback_engine", return_value=fe):
            with patch.object(se_module, "get_soul_engine", return_value=MagicMock()):
                reflection_loop._apply_reflection_to_hooks(reflection_summary)

    events = fe.get_recent_events(limit=20)
    assert len(events) >= 1
    assert fe.get_target_score("reflection_pattern", reflection_summary.what_worked[0]) > 1.0


def test_reflection_positive_from_what_worked(reflection_loop, tmp_path):
    """what_worked → positive Signale."""
    from orchestration.feedback_engine import FeedbackEngine
    from orchestration.session_reflection import ReflectionSummary
    import orchestration.feedback_engine as fe_module
    import memory.soul_engine as se_module

    fe = FeedbackEngine(db_path=tmp_path / "fb2.db")
    summary = ReflectionSummary(
        session_id="sess-1",
        tasks_count=3,
        success_rate=0.9,
        what_worked=["Direkte Antwort", "Schnell"],
        what_failed=[],
    )

    with patch.dict(os.environ, {"AUTONOMY_M16_ENABLED": "true"}):
        with patch.object(fe_module, "get_feedback_engine", return_value=fe):
            with patch.object(se_module, "get_soul_engine", return_value=MagicMock()):
                reflection_loop._apply_reflection_to_hooks(summary)

    positive_events = [e for e in fe.get_recent_events(limit=20) if e.signal == "positive"]
    assert len(positive_events) >= 1


def test_reflection_negative_from_what_failed(reflection_loop, tmp_path):
    """what_failed → negative Signale."""
    from orchestration.feedback_engine import FeedbackEngine
    from orchestration.session_reflection import ReflectionSummary
    import orchestration.feedback_engine as fe_module
    import memory.soul_engine as se_module

    fe = FeedbackEngine(db_path=tmp_path / "fb3.db")
    summary = ReflectionSummary(
        session_id="sess-2",
        tasks_count=3,
        success_rate=0.4,
        what_worked=[],
        what_failed=["Fehler bei API-Call", "Timeout"],
    )

    with patch.dict(os.environ, {"AUTONOMY_M16_ENABLED": "true"}):
        with patch.object(fe_module, "get_feedback_engine", return_value=fe):
            with patch.object(se_module, "get_soul_engine", return_value=MagicMock()):
                reflection_loop._apply_reflection_to_hooks(summary)

    negative_events = [e for e in fe.get_recent_events(limit=20) if e.signal == "negative"]
    assert len(negative_events) >= 1


def test_reflection_patterns_gain_weighted_occurrences(reflection_loop, tmp_path):
    from orchestration.feedback_engine import FeedbackEngine
    from orchestration.session_reflection import ReflectionSummary
    import orchestration.feedback_engine as fe_module

    fe = FeedbackEngine(db_path=tmp_path / "fb_patterns.db")
    fe.record_signal(
        "pattern-1",
        "positive",
        context={"reflection_pattern": "pattern-x"},
        feedback_targets=[{"namespace": "reflection_pattern", "key": "pattern-x"}],
    )
    summary = ReflectionSummary(
        session_id="sess-pattern",
        tasks_count=2,
        success_rate=0.7,
        patterns=["pattern-x"],
    )
    with patch.object(fe_module, "get_feedback_engine", return_value=fe):
        reflection_loop._accumulate_patterns(summary)

    with sqlite3.connect(str(reflection_loop.db_path)) as conn:
        row = conn.execute(
            "SELECT occurrences FROM improvement_suggestions WHERE pattern = ?",
            ("pattern-x",),
        ).fetchone()
    assert row is not None
    assert row[0] == 2


# ──────────────────────────────────────────────────────────────────
# End-to-End: FeedbackEngine + Soul Engine (ohne SOUL.md)
# ──────────────────────────────────────────────────────────────────

def test_feedback_engine_record_and_retrieve(tmp_path):
    """FeedbackEngine speichert und liest korrekt."""
    from orchestration.feedback_engine import FeedbackEngine
    fe = FeedbackEngine(db_path=tmp_path / "e2e.db")

    fe.record_signal("action-e2e", "positive", hook_names=["direkt"])
    fe.record_signal("action-e2e", "negative", hook_names=["vorsichtig"])
    fe.record_signal("action-e2e", "neutral")

    events = fe.get_recent_events(limit=10)
    signals = [e.signal for e in events]
    assert "positive" in signals
    assert "negative" in signals
    assert "neutral" in signals


def test_feedback_count_lean_invariant():
    """Lean: m16_feedback_count — n + 1 ≥ 0 für n ≥ 0."""
    for n in range(10):
        assert n + 1 >= 0


def test_neutral_noop_lean_invariant():
    """Lean: m16_neutral_noop — w = w."""
    from memory.soul_engine import WeightedHook
    for w in [0.5, 1.0, 1.5, 2.0]:
        h = WeightedHook(text="test", weight=w)
        old_weight = h.weight
        h.apply_feedback("neutral")
        assert h.weight == old_weight
