"""CrossHair + Hypothesis Contracts fuer Dispatcher-Semantik in Phase A."""

from __future__ import annotations

import deal
from hypothesis import given, settings
from hypothesis import strategies as st

import main_dispatcher


@deal.post(lambda r: isinstance(r, str))
def dispatcher_focus_query_contract(text: str) -> str:
    """Der Dispatcher-Fokus bleibt immer ein String."""
    return main_dispatcher._extract_dispatcher_focus_query(text)


@deal.post(lambda r: isinstance(r, bool))
def dispatcher_reference_followup_contract(text: str) -> bool:
    """Referenz-Follow-up-Erkennung bleibt total und boolesch."""
    return main_dispatcher._looks_like_dispatcher_reference_followup(text)


@deal.post(lambda r: isinstance(r, str))
def dispatcher_core_query_contract(text: str) -> str:
    """Die reduzierte Kernfrage bleibt immer ein String."""
    return main_dispatcher._extract_dispatcher_core_query(text)


def test_contract_dispatcher_focus_query_prefers_current_user_query():
    text = """# FOLLOW-UP CONTEXT
last_agent: research
# CURRENT USER QUERY
mach weiter damit
"""

    assert dispatcher_focus_query_contract(text) == "mach weiter damit"


def test_contract_dispatcher_reference_followup_detects_short_reference():
    assert dispatcher_reference_followup_contract("dann uebernimm die empfehlung 2") is True


def test_contract_dispatcher_core_query_strips_colloquial_shell():
    assert dispatcher_core_query_contract("was denkst du wird es morgen regnen") == "wird es morgen regnen"


@given(st.text(min_size=0, max_size=200))
@settings(max_examples=150)
def test_hypothesis_dispatcher_focus_query_always_returns_string(text: str):
    assert isinstance(dispatcher_focus_query_contract(text), str)


@given(st.text(min_size=0, max_size=200))
@settings(max_examples=150)
def test_hypothesis_dispatcher_core_query_always_returns_string(text: str):
    assert isinstance(dispatcher_core_query_contract(text), str)


@given(st.text(min_size=0, max_size=60))
@settings(max_examples=150)
def test_hypothesis_dispatcher_reference_followup_always_returns_bool(text: str):
    assert isinstance(dispatcher_reference_followup_contract(text), bool)


@given(st.text(min_size=0, max_size=80))
@settings(max_examples=100)
def test_hypothesis_current_user_marker_not_preserved_when_suffix_exists(suffix: str):
    text = f"# FOLLOW-UP CONTEXT\nlast_agent: meta\n# CURRENT USER QUERY\n{suffix}"
    result = dispatcher_focus_query_contract(text)
    if suffix.strip():
        assert "# CURRENT USER QUERY" not in result
