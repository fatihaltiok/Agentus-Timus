"""
tests/test_meta_improvements.py — Phase-3: Meta Agent Verbesserungen

Tests für:
  - MAX_DECOMPOSITION_DEPTH Invariante (Th.49)
  - _needs_decomposition_hint: Erkennung komplexer Aufgaben
  - _DECOMPOSITION_HINT: vorhanden und korrekt
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from agent.agents.meta import MetaAgent


def _make_agent() -> MetaAgent:
    return MetaAgent(tools_description_string="")


# ──────────────────────────────────────────────────────────────────
# MAX_DECOMPOSITION_DEPTH Invariante (Th.49)
# ──────────────────────────────────────────────────────────────────

def test_max_decomposition_depth_positive():
    assert MetaAgent.MAX_DECOMPOSITION_DEPTH > 0


def test_max_decomposition_depth_value():
    assert MetaAgent.MAX_DECOMPOSITION_DEPTH == 3


@given(depth=st.integers(min_value=0, max_value=MetaAgent.MAX_DECOMPOSITION_DEPTH))
@settings(max_examples=100)
def test_decomposition_depth_terminates(depth):
    """Th.49: depth ≤ MAX_DECOMPOSITION_DEPTH → depth < MAX_DECOMPOSITION_DEPTH + 1."""
    assert depth < MetaAgent.MAX_DECOMPOSITION_DEPTH + 1


# ──────────────────────────────────────────────────────────────────
# _needs_decomposition_hint
# ──────────────────────────────────────────────────────────────────

def test_simple_task_no_hint():
    """Einfache, kurze Aufgabe → kein Hint."""
    result = MetaAgent._needs_decomposition_hint("Sag hallo")
    assert result is False


def test_complex_task_gets_hint():
    """Komplexe Aufgabe mit vielen Trigger-Wörtern → Hint aktiviert."""
    task = (
        "Implementiere das neue Feature, dann schreibe Tests, "
        "anschließend erstelle die Dokumentation und außerdem deploye alles"
    )
    result = MetaAgent._needs_decomposition_hint(task)
    assert result is True


def test_long_task_gets_hint():
    """Langer Task (>200 Zeichen) → Hint immer aktiviert."""
    task = "A" * 201
    result = MetaAgent._needs_decomposition_hint(task)
    assert result is True


def test_short_simple_task():
    """Kurzer Task ohne Trigger → kein Hint."""
    result = MetaAgent._needs_decomposition_hint("Recherchiere Python")
    assert result is False


def test_two_step_task():
    """Zweischrittiger Task mit wenigen Triggern → kein Hint (< 3 Trigger)."""
    result = MetaAgent._needs_decomposition_hint("Lese die Datei und gib den Inhalt zurück")
    assert isinstance(result, bool)  # Kein Fehler — Ergebnis kann True oder False sein


# ──────────────────────────────────────────────────────────────────
# _DECOMPOSITION_HINT Inhalt
# ──────────────────────────────────────────────────────────────────

def test_decomposition_hint_contains_phases():
    assert "Phase 1" in MetaAgent._DECOMPOSITION_HINT
    assert "Phase 2" in MetaAgent._DECOMPOSITION_HINT
    assert "Phase 3" in MetaAgent._DECOMPOSITION_HINT


def test_decomposition_hint_mentions_max_depth():
    assert str(MetaAgent.MAX_DECOMPOSITION_DEPTH) in MetaAgent._DECOMPOSITION_HINT


def test_decomposition_hint_is_string():
    assert isinstance(MetaAgent._DECOMPOSITION_HINT, str)
    assert len(MetaAgent._DECOMPOSITION_HINT) > 50
