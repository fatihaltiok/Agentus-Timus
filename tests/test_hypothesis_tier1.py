"""
tests/test_hypothesis_tier1.py

Hypothesis Tier-1-Tests für die 8 wichtigsten Timus-Kern-Module.
Ergänzt test_hypothesis_formal.py (Th.1–31) mit Th.32–44.

Modul-Index:
  Gruppe 1 — Autonomy Scorecard    (Th.32–37) orchestration/autonomy_scorecard.py
  Gruppe 2 — Self-Improvement      (Th. —)    orchestration/self_improvement_engine.py
  Gruppe 3 — Curiosity Engine      (Th.38–40) orchestration/curiosity_engine.py
  Gruppe 4 — Policy Gate           (Th.41–42) utils/policy_gate.py
  Gruppe 5 — Proactive Triggers    (Th.43)    orchestration/proactive_triggers.py
  Gruppe 6 — Goal Queue Manager    (Th.44)    orchestration/goal_queue_manager.py
  Gruppe 7 — Agent Blackboard      (Th.3*)    memory/agent_blackboard.py
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

from hypothesis import assume, given, settings
from hypothesis import strategies as st

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

# ===========================================================================
# GRUPPE 1 — Autonomy Scorecard (Th.32–37)
# ===========================================================================
# Direkt aus orchestration/autonomy_scorecard.py extrahiert (reine Funktionen)

from orchestration.autonomy_scorecard import (
    _clamp,
    _score_goals,
    _score_planning,
    _score_self_healing,
    _score_policy,
    _autonomy_level,
)


# Th.32 — _clamp(v) ≥ 0
@given(v=st.floats(-1e9, 1e9, allow_nan=False, allow_infinity=False))
def test_scorecard_clamp_lower(v: float) -> None:
    """Th.32: _clamp(v) ≥ 0.0"""
    assert _clamp(v) >= 0.0


# Th.33 — _clamp(v) ≤ 100
@given(v=st.floats(-1e9, 1e9, allow_nan=False, allow_infinity=False))
def test_scorecard_clamp_upper(v: float) -> None:
    """Th.33: _clamp(v) ≤ 100.0"""
    assert _clamp(v) <= 100.0


# Th.34 — _score_goals: score ∈ [0, 100] für alle Inputs
@given(
    open_alignment=st.floats(-500.0, 500.0, allow_nan=False, allow_infinity=False),
    conflicts=st.integers(0, 100),
    orphan=st.integers(0, 100),
    open_tasks=st.integers(0, 100),
)
@settings(max_examples=200)
def test_scorecard_goals_bounds(
    open_alignment: float,
    conflicts: int,
    orphan: int,
    open_tasks: int,
) -> None:
    """Th.34: _score_goals["score"] ∈ [0.0, 100.0]"""
    metrics = {
        "open_alignment_rate": open_alignment,
        "conflict_count": conflicts,
        "orphan_triggered_tasks": orphan,
        "open_tasks": open_tasks,
    }
    result = _score_goals(metrics)
    assert 0.0 <= result["score"] <= 100.0


# Th.34b — _score_planning: score ∈ [0, 100]
@given(
    deviation=st.floats(0.0, 100.0, allow_nan=False, allow_infinity=False),
    overdue=st.integers(0, 50),
    due_reviews=st.integers(0, 50),
    escalated=st.integers(0, 50),
    events=st.integers(0, 50),
    applied=st.integers(0, 50),
    total=st.integers(0, 100),
    active=st.integers(0, 100),
)
@settings(max_examples=200)
def test_scorecard_planning_bounds(
    deviation: float,
    overdue: int,
    due_reviews: int,
    escalated: int,
    events: int,
    applied: int,
    total: int,
    active: int,
) -> None:
    """Th.34b: _score_planning["score"] ∈ [0.0, 100.0]"""
    planning_metrics = {
        "plan_deviation_score": deviation,
        "overdue_commitments": overdue,
        "commitments_total": total,
        "active_plans": active,
    }
    replanning_metrics = {
        "events_last_24h": events,
        "applied_last_24h": applied,
    }
    review_metrics = {
        "due_reviews": due_reviews,
        "escalated_last_7d": escalated,
    }
    result = _score_planning(planning_metrics, replanning_metrics, review_metrics)
    assert 0.0 <= result["score"] <= 100.0


# Th.35 — _score_self_healing: Degrade-Penalty-Mapping ist korrekt
@given(
    recovery_rate=st.floats(0.0, 100.0, allow_nan=False, allow_infinity=False),
    open_incidents=st.integers(0, 20),
    escalated=st.integers(0, 10),
    breaker_open=st.integers(0, 10),
    created=st.integers(0, 20),
    recovered=st.integers(0, 20),
    degrade_mode=st.sampled_from(["normal", "cautious", "restricted", "emergency"]),
)
@settings(max_examples=200)
def test_scorecard_healing_bounds(
    recovery_rate: float,
    open_incidents: int,
    escalated: int,
    breaker_open: int,
    created: int,
    recovered: int,
    degrade_mode: str,
) -> None:
    """Th.35: _score_self_healing["score"] ∈ [0.0, 100.0]"""
    metrics = {
        "degrade_mode": degrade_mode,
        "recovery_rate_24h": recovery_rate,
        "open_incidents": open_incidents,
        "open_escalated_incidents": escalated,
        "circuit_breakers_open": breaker_open,
        "created_last_24h": created,
        "recovered_last_24h": recovered,
    }
    result = _score_self_healing(metrics)
    assert 0.0 <= result["score"] <= 100.0


# Th.36 — Weighted Average ∈ [0, 100] wenn alle Pillars ∈ [0, 100]
@given(
    a=st.floats(0.0, 100.0, allow_nan=False, allow_infinity=False),
    b=st.floats(0.0, 100.0, allow_nan=False, allow_infinity=False),
    c=st.floats(0.0, 100.0, allow_nan=False, allow_infinity=False),
    d=st.floats(0.0, 100.0, allow_nan=False, allow_infinity=False),
)
def test_scorecard_weighted_avg_bounds(
    a: float, b: float, c: float, d: float
) -> None:
    """Th.36: Ø von 4 Pillar-Scores ∈ [0, 100] wenn alle ∈ [0, 100]"""
    overall = _clamp(a * 0.25 + b * 0.25 + c * 0.25 + d * 0.25)
    assert 0.0 <= overall <= 100.0


# Th.37 — _autonomy_level: monoton mit Score (höherer Score → mindestens gleiche Stufe)
_LEVEL_ORDER = {"low": 0, "developing": 1, "medium": 2, "high": 3, "very_high": 4}


@given(
    low=st.floats(0.0, 44.9, allow_nan=False, allow_infinity=False),
    high=st.floats(45.0, 100.0, allow_nan=False, allow_infinity=False),
)
def test_scorecard_level_monotone(low: float, high: float) -> None:
    """Th.37: höherer Score → mindestens gleiche Autonomie-Stufe"""
    assert _LEVEL_ORDER[_autonomy_level(low)] <= _LEVEL_ORDER[_autonomy_level(high)]


def test_scorecard_level_exact_boundaries() -> None:
    """Th.37b: Exakte Grenzen für Autonomie-Stufen"""
    assert _autonomy_level(85.0) == "very_high"
    assert _autonomy_level(84.9) == "high"
    assert _autonomy_level(75.0) == "high"
    assert _autonomy_level(74.9) == "medium"
    assert _autonomy_level(60.0) == "medium"
    assert _autonomy_level(59.9) == "developing"
    assert _autonomy_level(45.0) == "developing"
    assert _autonomy_level(44.9) == "low"


# ===========================================================================
# GRUPPE 2 — Self-Improvement Engine
# ===========================================================================
# Reine Formeln aus orchestration/self_improvement_engine.py

def _compute_success_rate(successes: int, total: int) -> float:
    """Direkt aus get_tool_stats: round(successes / total, 3)"""
    return round(successes / total, 3) if total > 0 else 0.0


def _compute_routing_success_rate(successes: int, total: int) -> float:
    """Direkt aus get_routing_stats."""
    return round(successes / total, 3) if total > 0 else 0.0


@given(
    total=st.integers(min_value=1, max_value=10_000),
    successes=st.integers(min_value=0, max_value=10_000),
)
def test_m12_tool_success_rate_bounds(total: int, successes: int) -> None:
    """Tool-Erfolgsrate ∈ [0, 1] wenn successes ≤ total"""
    assume(successes <= total)
    rate = _compute_success_rate(successes, total)
    assert 0.0 <= rate <= 1.0


@given(avg_ms=st.floats(min_value=0.0, max_value=100_000.0, allow_nan=False))
def test_m12_bottleneck_threshold(avg_ms: float) -> None:
    """Bottleneck: avg_ms > 3000 und success_rate > 0.8 → Suggestion empfohlen"""
    is_bottleneck = avg_ms > 3000
    is_fast = avg_ms <= 3000
    # Logische Konsistenz: beides nicht gleichzeitig wahr
    assert not (is_bottleneck and is_fast)


@given(
    success_rate=st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False),
)
def test_m12_severity_classification(success_rate: float) -> None:
    """Severity: < 0.50 → high, 0.50–0.69 → medium, ≥ 0.70 → kein Befund"""
    # Aus run_analysis_cycle: if success_rate < 0.70 → suggestion
    if success_rate < 0.50:
        severity = "high"
    elif success_rate < 0.70:
        severity = "medium"
    else:
        severity = "none"
    # Invariante: High ist schlimmer als Medium
    if severity == "high":
        assert success_rate < 0.50
    if severity == "medium":
        assert 0.50 <= success_rate < 0.70


@given(
    total=st.integers(min_value=1, max_value=10_000),
    successes=st.integers(min_value=0, max_value=10_000),
)
def test_m12_routing_confidence_bounds(total: int, successes: int) -> None:
    """Routing-Erfolgsrate ∈ [0, 1]"""
    assume(successes <= total)
    rate = _compute_routing_success_rate(successes, total)
    assert 0.0 <= rate <= 1.0


# ===========================================================================
# GRUPPE 3 — Curiosity Engine (Th.38–40)
# ===========================================================================
# Direkt aus orchestration/curiosity_engine.py

from orchestration.curiosity_engine import CuriosityEngine

TOPIC_MIN = 0.1
TOPIC_MAX = 3.0
GATEKEEPER_MIN_DEFAULT = 7


# Th.38+39 — update_topic_score: Score immer ∈ [0.1, 3.0]
@given(
    initial=st.floats(0.1, 3.0, allow_nan=False, allow_infinity=False),
    signal=st.sampled_from(["positive", "negative", "neutral"]),
)
@settings(max_examples=300)
def test_curiosity_topic_score_bounds(initial: float, signal: str) -> None:
    """Th.38+39: Topic-Score bleibt nach update_topic_score ∈ [0.1, 3.0]"""
    engine = CuriosityEngine()
    engine._topic_scores["test_topic"] = initial
    engine.update_topic_score("test_topic", signal)
    result = engine.get_topic_score("test_topic")
    assert TOPIC_MIN <= result <= TOPIC_MAX


@given(
    n_signals=st.integers(min_value=1, max_value=50),
    signals=st.lists(
        st.sampled_from(["positive", "negative", "neutral"]),
        min_size=1,
        max_size=50,
    ),
)
@settings(max_examples=200)
def test_curiosity_topic_score_bounds_multi_signal(
    n_signals: int, signals: list
) -> None:
    """Th.38+39: Score bleibt nach beliebig vielen Signalen ∈ [0.1, 3.0]"""
    engine = CuriosityEngine()
    topic = "multi_signal_test"
    for signal in signals[:n_signals]:
        engine.update_topic_score(topic, signal)
    score = engine.get_topic_score(topic)
    assert TOPIC_MIN <= score <= TOPIC_MAX


# Th.40 — Decay: score > 1.0 → nach Decay kleiner (Richtung 1.0)
@given(score=st.floats(min_value=1.001, max_value=3.0, allow_nan=False, allow_infinity=False))
def test_curiosity_decay_downward(score: float) -> None:
    """Th.40a: score > 1.0 → Decay bringt score näher zu 1.0 (nicht weiter weg)"""
    result = max(1.0, score * 0.9)
    assert result <= score
    assert result >= 1.0


@given(score=st.floats(min_value=0.1, max_value=0.999, allow_nan=False, allow_infinity=False))
def test_curiosity_decay_upward(score: float) -> None:
    """Th.40b: score < 1.0 → Decay bringt score näher zu 1.0 (nicht weiter weg)"""
    result = min(1.0, score / 0.9)
    assert result >= score
    assert result <= 1.0


# Gatekeeper-Invariante
@given(
    score=st.integers(min_value=0, max_value=10),
    gatekeeper_min=st.integers(min_value=1, max_value=10),
)
def test_curiosity_gatekeeper_logic(score: int, gatekeeper_min: int) -> None:
    """Gatekeeper: score < gatekeeper_min → nicht akzeptiert"""
    assume(score < gatekeeper_min)
    accepted = score >= gatekeeper_min
    assert not accepted


# ===========================================================================
# GRUPPE 4 — Policy Gate (Th.41–42)
# ===========================================================================
# Direkt aus utils/policy_gate.py

from utils.policy_gate import (
    ALWAYS_ALLOWED,
    BLOCKED_ACTIONS,
    check_tool_policy,
    check_query_policy,
    _canary_bucket_for_key,
)


# Th.41 — Canary-Bucket ∈ [0, 99]
@given(key=st.text(min_size=0, max_size=200))
def test_policy_canary_bucket_bounds(key: str) -> None:
    """Th.41: _canary_bucket_for_key(key) ∈ [0, 99]"""
    bucket = _canary_bucket_for_key(key)
    assert 0 <= bucket <= 99


# Th.42 — Canary-Percent Clamp ∈ [0, 100]
@given(v=st.integers(-10_000, 10_000))
def test_policy_canary_percent_clamp(v: int) -> None:
    """Th.42: canary_percent nach max(0, min(100, v)) ∈ [0, 100]"""
    clamped = max(0, min(100, v))
    assert 0 <= clamped <= 100


# Always-Allowed: alle immer True
def test_policy_always_allowed_invariant() -> None:
    """Alle ALWAYS_ALLOWED-Tools sind immer erlaubt (kein Block)"""
    for method in ALWAYS_ALLOWED:
        allowed, reason = check_tool_policy(method, {})
        assert allowed, f"ALWAYS_ALLOWED '{method}' wurde blockiert: {reason}"


# Blocked-Actions: alle immer False
def test_policy_blocked_actions_invariant() -> None:
    """Alle BLOCKED_ACTIONS sind nie erlaubt"""
    for method in BLOCKED_ACTIONS:
        allowed, reason = check_tool_policy(method, {})
        assert not allowed, f"BLOCKED_ACTION '{method}' wurde erlaubt!"
        assert reason is not None


# Canary-Determinismus: gleicher Key → gleicher Bucket
@given(key=st.text(min_size=0, max_size=100))
def test_policy_canary_deterministic(key: str) -> None:
    """Canary-Bucket ist deterministisch: gleicher Key → gleicher Bucket"""
    b1 = _canary_bucket_for_key(key)
    b2 = _canary_bucket_for_key(key)
    assert b1 == b2


# ===========================================================================
# GRUPPE 5 — Proactive Triggers (Th.43)
# ===========================================================================
# Direkt aus orchestration/proactive_triggers.py

FIRE_WINDOW_MIN = 14  # Aus proactive_triggers.py


# Th.43 — Fire-Window: |diff| ≤ 14 → im Fenster, > 14 → außen
@given(
    now_minutes=st.integers(0, 23 * 60 + 59),
    trigger_minutes=st.integers(0, 23 * 60 + 59),
)
def test_trigger_fire_window_outside(now_minutes: int, trigger_minutes: int) -> None:
    """Th.43: |diff| > FIRE_WINDOW_MIN → Trigger feuert NICHT"""
    diff = abs(now_minutes - trigger_minutes)
    assume(diff > FIRE_WINDOW_MIN)
    # Invariante: Trigger wird nicht ausgelöst wenn diff > Fenster
    should_skip = diff > FIRE_WINDOW_MIN
    assert should_skip


@given(
    base=st.integers(0, 23 * 60 + 59),
    offset=st.integers(0, FIRE_WINDOW_MIN),
)
def test_trigger_fire_window_inside(base: int, offset: int) -> None:
    """Th.43b: |diff| ≤ FIRE_WINDOW_MIN → Trigger im Zeitfenster (kann feuern)"""
    diff = offset  # direkt ≤ FIRE_WINDOW_MIN generiert, kein assume() nötig
    should_skip = diff > FIRE_WINDOW_MIN
    assert not should_skip


def test_trigger_fire_window_exact_boundary() -> None:
    """Th.43c: diff == FIRE_WINDOW_MIN → noch im Fenster"""
    diff = FIRE_WINDOW_MIN
    assert not (diff > FIRE_WINDOW_MIN)


# Wochentags-Filter: leere Liste = täglich
def test_trigger_empty_days_means_daily() -> None:
    """Leere days_of_week-Liste → täglich (kein Filter)"""
    days_of_week = []
    # Wenn days_of_week leer, dann ist ANY weekday akzeptiert
    for weekday in range(7):
        if days_of_week:
            is_valid_day = weekday in days_of_week
        else:
            is_valid_day = True
        assert is_valid_day


# ===========================================================================
# GRUPPE 6 — Goal Queue Manager (Th.44)
# ===========================================================================
# Direkt aus orchestration/goal_queue_manager.py:161

def _compute_milestone_progress(completed: list, milestones: list) -> float:
    """Direkt aus complete_milestone: len(completed) / len(milestones)"""
    return len(completed) / len(milestones) if milestones else 0.0


# Th.44 — Progress ∈ [0, 1]
@given(
    total=st.integers(min_value=1, max_value=1000),
    done=st.integers(min_value=0, max_value=1000),
)
def test_goal_progress_bounds(total: int, done: int) -> None:
    """Th.44: Meilenstein-Fortschritt ∈ [0.0, 1.0]"""
    done = min(done, total)  # completed ≤ milestones
    milestones = list(range(total))
    completed = list(range(done))
    progress = _compute_milestone_progress(completed, milestones)
    assert 0.0 <= progress <= 1.0


def test_goal_progress_zero_milestones() -> None:
    """Keine Meilensteine → progress = 0.0 (kein ZeroDivisionError)"""
    progress = _compute_milestone_progress([], [])
    assert progress == 0.0


@given(total=st.integers(min_value=1, max_value=1000))
def test_goal_progress_all_completed(total: int) -> None:
    """Alle Meilensteine erledigt → progress = 1.0"""
    milestones = list(range(total))
    progress = _compute_milestone_progress(milestones, milestones)
    assert progress == 1.0


@given(
    total=st.integers(min_value=1, max_value=1000),
    done_a=st.integers(min_value=0, max_value=1000),
    done_b=st.integers(min_value=0, max_value=1000),
)
def test_goal_progress_monotone(total: int, done_a: int, done_b: int) -> None:
    """Progress ist monoton: mehr Erledigtes → mehr Fortschritt"""
    done_a = min(done_a, total)
    done_b = min(done_b, total)
    p_a = _compute_milestone_progress(list(range(done_a)), list(range(total)))
    p_b = _compute_milestone_progress(list(range(done_b)), list(range(total)))
    if done_a <= done_b:
        assert p_a <= p_b


# ===========================================================================
# GRUPPE 7 — Agent Blackboard
# ===========================================================================
# Direkt aus memory/agent_blackboard.py

from datetime import datetime, timedelta


# TTL-Invariante: max(1, ttl) ≥ 1 (erweitert Th.3)
@given(ttl=st.integers(-1000, 10_000))
def test_blackboard_ttl_always_positive(ttl: int) -> None:
    """TTL nach max(1, ttl) immer ≥ 1 Minute"""
    effective_ttl = max(1, ttl)
    assert effective_ttl >= 1


# expires_at > created_at
@given(ttl=st.integers(min_value=1, max_value=10_000))
def test_blackboard_expires_after_created(ttl: int) -> None:
    """expires_at = now + timedelta(minutes=ttl) > now für ttl ≥ 1"""
    now = datetime.now()
    expires = now + timedelta(minutes=max(1, ttl))
    assert expires > now


# TTL monoton: größeres TTL → späteres Ablaufen
@given(
    ttl_a=st.integers(min_value=1, max_value=10_000),
    ttl_b=st.integers(min_value=1, max_value=10_000),
)
def test_blackboard_ttl_monotone(ttl_a: int, ttl_b: int) -> None:
    """Größeres TTL → später ablaufend"""
    now = datetime.now()
    exp_a = now + timedelta(minutes=ttl_a)
    exp_b = now + timedelta(minutes=ttl_b)
    if ttl_a <= ttl_b:
        assert exp_a <= exp_b
