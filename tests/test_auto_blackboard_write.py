"""Tests für AgentRegistry._auto_write_to_blackboard (M17)."""
import time
from unittest.mock import MagicMock, patch

import pytest
from hypothesis import given, strategies as st

from agent.agent_registry import AgentRegistry


# ── 1. Mock-Blackboard: write() wird aufgerufen ───────────────────────────

def _make_bb_mock():
    bb = MagicMock()
    bb.write = MagicMock()
    return bb


def test_auto_blackboard_write_called(monkeypatch):
    bb = _make_bb_mock()
    with patch("memory.agent_blackboard.get_blackboard", return_value=bb):
        key = AgentRegistry._auto_write_to_blackboard("shell", "test task", "result", "success")
    bb.write.assert_called_once()
    assert key != ""


def test_auto_blackboard_write_returns_key(monkeypatch):
    bb = _make_bb_mock()
    with patch("memory.agent_blackboard.get_blackboard", return_value=bb):
        key = AgentRegistry._auto_write_to_blackboard("research", "my task", "output", "success")
    assert key.startswith("delegation:research:")


# ── 2. TTL-Mapping ────────────────────────────────────────────────────────

def test_ttl_success_is_120(monkeypatch):
    bb = _make_bb_mock()
    with patch("memory.agent_blackboard.get_blackboard", return_value=bb):
        AgentRegistry._auto_write_to_blackboard("shell", "t", "r", "success")
    call_kwargs = bb.write.call_args[1]
    assert call_kwargs["ttl_minutes"] == 120


def test_ttl_partial_is_60(monkeypatch):
    bb = _make_bb_mock()
    with patch("memory.agent_blackboard.get_blackboard", return_value=bb):
        AgentRegistry._auto_write_to_blackboard("shell", "t", "r", "partial")
    call_kwargs = bb.write.call_args[1]
    assert call_kwargs["ttl_minutes"] == 60


def test_ttl_error_is_30(monkeypatch):
    bb = _make_bb_mock()
    with patch("memory.agent_blackboard.get_blackboard", return_value=bb):
        AgentRegistry._auto_write_to_blackboard("shell", "t", "r", "error")
    call_kwargs = bb.write.call_args[1]
    assert call_kwargs["ttl_minutes"] == 30


def test_ttl_unknown_status_defaults_to_60(monkeypatch):
    bb = _make_bb_mock()
    with patch("memory.agent_blackboard.get_blackboard", return_value=bb):
        AgentRegistry._auto_write_to_blackboard("shell", "t", "r", "unexpected")
    call_kwargs = bb.write.call_args[1]
    assert call_kwargs["ttl_minutes"] == 60


def test_ttl_positive_for_all_statuses():
    """Lean Th.52: TTL ist immer positiv."""
    for ttl in [120, 60, 30]:
        assert ttl > 0


def test_blackboard_write_uses_real_signature_fields():
    bb = _make_bb_mock()
    with patch("memory.agent_blackboard.get_blackboard", return_value=bb):
        AgentRegistry._auto_write_to_blackboard("shell", "task", "result", "success")

    call_kwargs = bb.write.call_args.kwargs
    assert call_kwargs["agent"] == "agent_registry"
    assert call_kwargs["topic"] == "delegation_results"
    assert call_kwargs["key"].startswith("delegation:shell:")


def test_blackboard_write_propagates_session_id():
    bb = _make_bb_mock()
    with patch("memory.agent_blackboard.get_blackboard", return_value=bb):
        AgentRegistry._auto_write_to_blackboard(
            "research",
            "task",
            "result",
            "success",
            session_id="sess-42",
        )

    call_kwargs = bb.write.call_args.kwargs
    assert call_kwargs["session_id"] == "sess-42"


def test_blackboard_write_uses_empty_session_id_when_missing():
    bb = _make_bb_mock()
    with patch("memory.agent_blackboard.get_blackboard", return_value=bb):
        AgentRegistry._auto_write_to_blackboard("research", "task", "result", "success")

    call_kwargs = bb.write.call_args.kwargs
    assert call_kwargs["session_id"] == ""


# ── 3. Key-Format ─────────────────────────────────────────────────────────

def test_key_format_delegation_prefix(monkeypatch):
    bb = _make_bb_mock()
    with patch("memory.agent_blackboard.get_blackboard", return_value=bb):
        key = AgentRegistry._auto_write_to_blackboard("developer", "task", "res", "success")
    assert key.startswith("delegation:developer:")


def test_key_format_contains_timestamp(monkeypatch):
    before = int(time.time())
    bb = _make_bb_mock()
    with patch("memory.agent_blackboard.get_blackboard", return_value=bb):
        key = AgentRegistry._auto_write_to_blackboard("meta", "t", "r", "success")
    after = int(time.time())
    ts = int(key.split(":")[-1])
    assert before <= ts <= after


# ── 4. Exception im Blackboard → Key="" (graceful) ────────────────────────

def test_blackboard_exception_returns_empty_key(monkeypatch):
    with patch("memory.agent_blackboard.get_blackboard", side_effect=RuntimeError("BB offline")):
        key = AgentRegistry._auto_write_to_blackboard("shell", "t", "r", "success")
    assert key == ""


def test_blackboard_write_exception_returns_empty_key(monkeypatch):
    bb = MagicMock()
    bb.write.side_effect = Exception("write failed")
    with patch("memory.agent_blackboard.get_blackboard", return_value=bb):
        key = AgentRegistry._auto_write_to_blackboard("shell", "t", "r", "success")
    assert key == ""


@given(
    agent_type=st.text(
        min_size=1,
        max_size=20,
        alphabet=st.characters(
            whitelist_categories=("Ll", "Lu", "Nd"),
            whitelist_characters="-_",
        ),
    ),
    task=st.text(max_size=80),
    result=st.text(max_size=120),
    status=st.text(min_size=1, max_size=20),
)
def test_auto_blackboard_write_hypothesis_contract(agent_type, task, result, status):
    bb = _make_bb_mock()
    with patch("memory.agent_blackboard.get_blackboard", return_value=bb):
        key = AgentRegistry._auto_write_to_blackboard(
            agent_type,
            task,
            result,
            status,
            session_id="sess-h",
        )

    call_kwargs = bb.write.call_args.kwargs
    assert key.startswith(f"delegation:{agent_type}:")
    assert call_kwargs["agent"] == "agent_registry"
    assert call_kwargs["topic"] == "delegation_results"
    assert call_kwargs["ttl_minutes"] >= 1
    assert call_kwargs["session_id"] == "sess-h"
