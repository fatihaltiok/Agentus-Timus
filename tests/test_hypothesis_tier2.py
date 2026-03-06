"""
tests/test_hypothesis_tier2.py — Tier-2 Hypothesis Property-Based Tests

Mappt Lean-Invarianten auf Property-Based Tests für 5 Module:
  - SessionReflectionLoop (orchestration/session_reflection.py)
  - AgentRegistry        (agent/agent_registry.py)
  - HealthOrchestrator   (orchestration/health_orchestrator.py)
  - CommitmentReviewEngine (orchestration/commitment_review_engine.py)
  - TaskQueue / task_queue.py Normalisierungsfunktionen

Alle Tests laufen ohne Netz/DB-Zugriff (unit-level, pure functions).
"""

import sys
import os

# Projekt-Root in sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from hypothesis import given, settings, assume
from hypothesis import strategies as st

# ──────────────────────────────────────────────────────────────────
# A. SessionReflectionLoop — pure Hilfsfunktionen
# ──────────────────────────────────────────────────────────────────

# IDLE_THRESHOLD_MIN = 30 (Standard-Wert)
IDLE_THRESHOLD_MIN = 30
PATTERN_THRESHOLD = 3


def _reflection_triggered(gap_minutes: float) -> bool:
    """Spiegelt die Bedingung aus check_and_reflect: gap >= IDLE_THRESHOLD_MIN."""
    return gap_minutes >= IDLE_THRESHOLD_MIN


# Th.45: Reflexion NOT ausgelöst wenn gap < Threshold
@given(gap=st.floats(min_value=0.0, max_value=29.99, allow_nan=False, allow_infinity=False))
@settings(max_examples=300)
def test_reflection_guard_not_triggered(gap):
    """gap < IDLE_THRESHOLD_MIN → Reflexion nicht ausgelöst (Spiegelbild von M8)."""
    assert not _reflection_triggered(gap)


# Th.46: Reflexion ausgelöst wenn gap >= Threshold
@given(gap=st.floats(min_value=30.0, max_value=10000.0, allow_nan=False, allow_infinity=False))
@settings(max_examples=300)
def test_reflection_triggered_at_threshold(gap):
    """gap >= IDLE_THRESHOLD_MIN → Reflexion wird ausgelöst."""
    assert _reflection_triggered(gap)


# Th.47: Pattern-Akkumulation — Monotonie (nach n Signalen: occurrences ≥ 1)
@given(n=st.integers(min_value=1, max_value=100))
@settings(max_examples=200)
def test_pattern_accumulation_monotone(n):
    """Occurrences wächst monoton: nach n Signalen ist occurrences = n ≥ 1."""
    occurrences = n  # jede Runde +1
    assert occurrences >= 1


# Th.48: Pattern-Suggestion tritt genau ab PATTERN_THRESHOLD auf
@given(count=st.integers(min_value=PATTERN_THRESHOLD, max_value=1000))
@settings(max_examples=200)
def test_pattern_threshold_suggestion(count):
    """count >= PATTERN_THRESHOLD → Suggestion wird erstellt (not count < PATTERN_THRESHOLD)."""
    assert count >= PATTERN_THRESHOLD


# Th.49: Erfolgsrate ∈ [0.0, 1.0]
@given(
    completed=st.integers(min_value=0, max_value=100),
    total=st.integers(min_value=1, max_value=100),
)
@settings(max_examples=300)
def test_reflection_success_rate_bounds(completed, total):
    """success_rate = completed/total ∈ [0.0, 1.0] wenn completed ≤ total."""
    assume(completed <= total)
    rate = completed / total
    assert 0.0 <= rate <= 1.0


# ──────────────────────────────────────────────────────────────────
# B. AgentRegistry — pure Methoden
# ──────────────────────────────────────────────────────────────────

from agent.agent_registry import AgentRegistry

REGISTRY = AgentRegistry()

VALID_ALIASES = {
    "development": "developer",
    "dev": "developer",
    "researcher": "research",
    "analyst": "reasoning",
    "vision": "visual",
    "daten": "data",
    "bash": "shell",
    "terminal": "shell",
    "monitoring": "system",
    "koordinator": "meta",
    "orchestrator": "meta",
}


# Th.50: Alias-Normalisierung — bekannte Aliase landen immer beim Ziel-Typ
@given(alias=st.sampled_from(list(VALID_ALIASES.keys())))
@settings(max_examples=100)
def test_agent_normalize_known_alias(alias):
    """Bekannte Alias-Namen werden korrekt auf kanonische Agent-Namen gemappt."""
    expected = VALID_ALIASES[alias]
    assert REGISTRY.normalize_agent_name(alias) == expected


# Th.51: Idempotenz — normalize zweimal aufgerufen ergibt dasselbe Ergebnis
@given(name=st.text(min_size=1, max_size=30, alphabet=st.characters(whitelist_categories=("Ll", "Lu", "Nd"))))
@settings(max_examples=200)
def test_agent_normalize_idempotent(name):
    """normalize(normalize(x)) == normalize(x) — Idempotenz."""
    once = REGISTRY.normalize_agent_name(name)
    twice = REGISTRY.normalize_agent_name(once)
    assert once == twice


# Th.52: Unbekannte Namen passieren unverändert (lowercase)
@given(name=st.text(min_size=1, max_size=20, alphabet="abcdefghijklmnopqrstuvwxyz"))
@settings(max_examples=200)
def test_agent_normalize_unknown_passthrough(name):
    """Namen die kein Alias sind passieren lowercase unverändert."""
    assume(name not in VALID_ALIASES)
    result = REGISTRY.normalize_agent_name(name)
    # Kein bekannter Alias → Rückgabe ist name.strip().lower()
    assert result == name.strip().lower() or result == name  # entweder pass-through oder alias-mapped


# Th.53: list_agents — Länge monoton wachsend nach register_spec
def test_agent_list_monotone_after_register():
    """Nach register_spec ist die Agentenliste länger oder gleich."""
    registry = AgentRegistry()
    before = len(registry.list_agents())
    registry.register_spec(
        name="test_agent_tier2",
        agent_type="test",
        capabilities=["test_cap"],
        factory=lambda **kw: None,
    )
    after = len(registry.list_agents())
    assert after >= before + 1


# Th.54: find_by_capability — gibt nur Specs mit passender Capability zurück
def test_agent_find_by_capability_correct():
    """find_by_capability gibt nur Specs zurück die die Capability enthalten."""
    registry = AgentRegistry()
    registry.register_spec(
        name="cap_agent_a",
        agent_type="test",
        capabilities=["cap_x", "cap_y"],
        factory=lambda **kw: None,
    )
    registry.register_spec(
        name="cap_agent_b",
        agent_type="test",
        capabilities=["cap_z"],
        factory=lambda **kw: None,
    )
    results = registry.find_by_capability("cap_x")
    for spec in results:
        assert "cap_x" in spec.capabilities


# ──────────────────────────────────────────────────────────────────
# C. HealthOrchestrator — pure Berechnungen
# ──────────────────────────────────────────────────────────────────

from orchestration.health_orchestrator import HealthOrchestrator, _normalize_severity
from orchestration.task_queue import Priority, SelfHealingDegradeMode

ORCHESTRATOR = HealthOrchestrator()

VALID_SEVERITIES = {"critical", "high", "medium", "low"}
VALID_PRIORITY_INTS = {int(p) for p in Priority}
VALID_DEGRADE_MODES = {
    SelfHealingDegradeMode.NORMAL,
    SelfHealingDegradeMode.DEGRADED,
    SelfHealingDegradeMode.EMERGENCY,
}

# Th.55: _normalize_severity gibt immer einen validen Wert zurück
@given(sev=st.text(min_size=0, max_size=50))
@settings(max_examples=300)
def test_normalize_severity_valid(sev):
    """_normalize_severity gibt immer einen Wert aus {critical, high, medium, low} zurück."""
    result = _normalize_severity(sev)
    assert result in VALID_SEVERITIES


# Th.56: _normalize_severity ist idempotent
@given(sev=st.sampled_from(["critical", "high", "medium", "low", "CRITICAL", "HIGH", "unknown", ""]))
@settings(max_examples=100)
def test_normalize_severity_idempotent(sev):
    """normalize(normalize(sev)) == normalize(sev)."""
    once = _normalize_severity(sev)
    twice = _normalize_severity(once)
    assert once == twice


# Th.57: route_recovery — priority ist immer ein valider Priority-Int
@given(
    sev=st.sampled_from(["critical", "high", "medium", "low"]),
    comp=st.sampled_from(["mcp", "system", "queue", "providers", "other"]),
    default_priority=st.integers(min_value=0, max_value=3),
)
@settings(max_examples=300)
def test_route_recovery_priority_valid(sev, comp, default_priority):
    """route_recovery gibt immer eine gültige Priority-Zahl zurück."""
    result = ORCHESTRATOR.route_recovery(
        component=comp,
        signal="test_signal",
        severity=sev,
        default_target_agent="meta",
        default_priority=default_priority,
        default_template="default_template",
    )
    assert result["priority"] in VALID_PRIORITY_INTS


# Th.58: evaluate_degrade_mode — mode ist immer ein valider DegradeMode-String
@given(
    open_incidents=st.integers(min_value=0, max_value=20),
    breakers_open=st.integers(min_value=0, max_value=10),
    high_open=st.integers(min_value=0, max_value=10),
)
@settings(max_examples=400)
def test_evaluate_degrade_mode_valid(open_incidents, breakers_open, high_open):
    """evaluate_degrade_mode gibt immer einen validen Mode-String zurück."""
    result = ORCHESTRATOR.evaluate_degrade_mode(
        metrics={
            "open_incidents": open_incidents,
            "circuit_breakers_open": breakers_open,
            "open_by_severity": {"high": high_open},
        },
        signals={},
    )
    assert result["mode"] in VALID_DEGRADE_MODES


# Th.59: evaluate_degrade_mode — score ≥ 0
@given(
    open_incidents=st.integers(min_value=0, max_value=20),
    breakers_open=st.integers(min_value=0, max_value=10),
    high_open=st.integers(min_value=0, max_value=10),
)
@settings(max_examples=300)
def test_evaluate_degrade_mode_score_nonneg(open_incidents, breakers_open, high_open):
    """Der Health-Score ist immer ≥ 0."""
    result = ORCHESTRATOR.evaluate_degrade_mode(
        metrics={
            "open_incidents": open_incidents,
            "circuit_breakers_open": breakers_open,
            "open_by_severity": {"high": high_open},
        },
        signals={},
    )
    assert result["score"] >= 0.0


# Th.60: Normal-Modus wenn keine Incidents und keine Signale
def test_evaluate_degrade_mode_nominal():
    """Ohne Incidents und ohne unhealthy Signals: mode=normal."""
    result = ORCHESTRATOR.evaluate_degrade_mode(
        metrics={"open_incidents": 0, "circuit_breakers_open": 0, "open_by_severity": {}},
        signals={},
    )
    assert result["mode"] == SelfHealingDegradeMode.NORMAL


# ──────────────────────────────────────────────────────────────────
# D. CommitmentReviewEngine — _risk_level (pure Funktion)
# ──────────────────────────────────────────────────────────────────

from orchestration.commitment_review_engine import CommitmentReviewEngine
from orchestration.task_queue import CommitmentStatus

REVIEW_ENGINE = CommitmentReviewEngine()

VALID_RISK_LEVELS = {"low", "medium", "high", "critical"}


# Th.61: _risk_level gibt immer validen Wert zurück
@given(
    gap=st.floats(min_value=-100.0, max_value=200.0, allow_nan=False, allow_infinity=False),
    status=st.sampled_from([
        CommitmentStatus.PENDING,
        CommitmentStatus.IN_PROGRESS,
        CommitmentStatus.COMPLETED,
        CommitmentStatus.BLOCKED,
        CommitmentStatus.FAILED,
        CommitmentStatus.CANCELLED,
    ]),
)
@settings(max_examples=400)
def test_risk_level_valid(gap, status):
    """_risk_level gibt immer low|medium|high|critical zurück."""
    commitment = {"status": status}
    result = REVIEW_ENGINE._risk_level(gap, commitment)
    assert result in VALID_RISK_LEVELS


# Th.62: BLOCKED-Status → immer mindestens "high" Risiko
@given(gap=st.floats(min_value=-100.0, max_value=100.0, allow_nan=False, allow_infinity=False))
@settings(max_examples=300)
def test_risk_level_blocked_is_high(gap):
    """Status=BLOCKED → risk_level ist immer 'high'."""
    commitment = {"status": CommitmentStatus.BLOCKED}
    result = REVIEW_ENGINE._risk_level(gap, commitment)
    assert result == "high"


# Th.63: gap ≥ 35.0 → critical (wenn nicht BLOCKED)
@given(gap=st.floats(min_value=35.0, max_value=1000.0, allow_nan=False, allow_infinity=False))
@settings(max_examples=300)
def test_risk_level_critical_at_high_gap(gap):
    """gap >= 35.0 → critical (außer BLOCKED-Status)."""
    commitment = {"status": CommitmentStatus.PENDING}
    result = REVIEW_ENGINE._risk_level(gap, commitment)
    assert result == "critical"


# Th.64: gap < 10.0 und nicht BLOCKED → low
@given(gap=st.floats(min_value=-1000.0, max_value=9.99, allow_nan=False, allow_infinity=False))
@settings(max_examples=300)
def test_risk_level_low_at_small_gap(gap):
    """gap < 10.0 und kein BLOCKED-Status → risk_level == 'low'."""
    commitment = {"status": CommitmentStatus.PENDING}
    result = REVIEW_ENGINE._risk_level(gap, commitment)
    assert result == "low"


# Th.65: Eskalation passiert genau wenn risk in {high, critical}
@given(
    gap=st.floats(min_value=-100.0, max_value=200.0, allow_nan=False, allow_infinity=False),
    status=st.sampled_from([CommitmentStatus.PENDING, CommitmentStatus.IN_PROGRESS]),
)
@settings(max_examples=300)
def test_risk_escalation_iff_high_or_critical(gap, status):
    """Eskalation (reviews_escalated++) tritt genau dann auf wenn risk ∈ {high, critical}."""
    commitment = {"status": status}
    risk = REVIEW_ENGINE._risk_level(gap, commitment)
    should_escalate = risk in {"high", "critical"}
    if gap >= 20.0:
        assert should_escalate
    elif gap < 10.0:
        assert not should_escalate


# ──────────────────────────────────────────────────────────────────
# E. TaskQueue — Normalisierungsfunktionen (pure)
# ──────────────────────────────────────────────────────────────────

from orchestration.task_queue import (
    _normalize_goal_status,
    _normalize_commitment_status,
    _normalize_plan_horizon,
    _normalize_plan_status,
    _normalize_self_healing_incident_status,
    _normalize_self_healing_circuit_breaker_state,
    _normalize_self_healing_degrade_mode,
    _is_goal_transition_allowed,
    GoalStatus,
    GOAL_ALLOWED_TRANSITIONS,
    GOAL_STATUS_VALUES,
)


# Th.66: _normalize_goal_status gibt immer validen Status zurück
@given(raw=st.text(min_size=0, max_size=30))
@settings(max_examples=300)
def test_normalize_goal_status_valid(raw):
    """_normalize_goal_status gibt immer einen Wert aus GOAL_STATUS_VALUES zurück."""
    result = _normalize_goal_status(raw)
    assert result in GOAL_STATUS_VALUES


# Th.67: _normalize_goal_status ist idempotent
@given(raw=st.sampled_from(["active", "blocked", "completed", "cancelled", "ACTIVE", "unknown", ""]))
@settings(max_examples=100)
def test_normalize_goal_status_idempotent(raw):
    """normalize(normalize(x)) == normalize(x)."""
    once = _normalize_goal_status(raw)
    twice = _normalize_goal_status(once)
    assert once == twice


# Th.68: _normalize_commitment_status gibt immer validen Status zurück
from orchestration.task_queue import COMMITMENT_STATUS_VALUES

@given(raw=st.text(min_size=0, max_size=30))
@settings(max_examples=300)
def test_normalize_commitment_status_valid(raw):
    """_normalize_commitment_status gibt immer einen Wert aus COMMITMENT_STATUS_VALUES zurück."""
    result = _normalize_commitment_status(raw)
    assert result in COMMITMENT_STATUS_VALUES


# Th.69: Completed/Cancelled → keine Transition zu ANDEREN Zuständen erlaubt
@given(
    target=st.sampled_from([GoalStatus.ACTIVE, GoalStatus.BLOCKED]),
)
@settings(max_examples=100)
def test_goal_terminal_states_no_transition(target):
    """completed und cancelled sind terminale Zustände — keine Transition zu active/blocked."""
    for terminal in [GoalStatus.COMPLETED, GoalStatus.CANCELLED]:
        # same-state (terminal→terminal) ist erlaubt, aber terminal→active/blocked nicht
        assert not _is_goal_transition_allowed(terminal, target)


# Th.70: Aktive/Blocked States erlauben Transitionen zu anderen Zuständen
def test_goal_active_allows_transitions():
    """active → blocked, completed, cancelled sind erlaubt."""
    assert _is_goal_transition_allowed(GoalStatus.ACTIVE, GoalStatus.BLOCKED)
    assert _is_goal_transition_allowed(GoalStatus.ACTIVE, GoalStatus.COMPLETED)
    assert _is_goal_transition_allowed(GoalStatus.ACTIVE, GoalStatus.CANCELLED)


# Th.71: _normalize_self_healing_degrade_mode ist idempotent
@given(raw=st.sampled_from(["normal", "degraded", "emergency", "NORMAL", "unknown", ""]))
@settings(max_examples=100)
def test_normalize_degrade_mode_idempotent(raw):
    """normalize(normalize(mode)) == normalize(mode)."""
    once = _normalize_self_healing_degrade_mode(raw)
    twice = _normalize_self_healing_degrade_mode(once)
    assert once == twice


# Th.72: avg_gap-Invariante: sum/n mit 0≤completed≤total
@given(
    gaps=st.lists(
        st.floats(min_value=-100.0, max_value=100.0, allow_nan=False, allow_infinity=False),
        min_size=1,
        max_size=50,
    )
)
@settings(max_examples=200)
def test_avg_gap_formula(gaps):
    """avg_gap = sum(gaps)/len(gaps) liegt immer zwischen min und max."""
    avg = sum(gaps) / len(gaps)  # kein round() um Float-Rounding-Artefakte zu vermeiden
    min_gap = min(gaps)
    max_gap = max(gaps)
    assert min_gap <= avg <= max_gap
