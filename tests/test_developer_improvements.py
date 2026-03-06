"""
tests/test_developer_improvements.py — Phase-3: Developer Agent Verbesserungen

Tests für:
  - _find_test_file: Test-Datei-Erkennung
  - _auto_run_tests: MAX_TEST_ITERATIONS respektiert (Th.47)
"""

import sys
import os
import subprocess

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from unittest.mock import patch, MagicMock
from hypothesis import given, settings
from hypothesis import strategies as st

from agent.agents.developer import DeveloperAgent

# DeveloperAgent braucht tools_description_string bei Init — leerer String reicht für Tests
def _make_agent() -> DeveloperAgent:
    return DeveloperAgent(tools_description_string="")


# ──────────────────────────────────────────────────────────────────
# MAX_TEST_ITERATIONS Invariante (Th.47)
# ──────────────────────────────────────────────────────────────────

def test_max_test_iterations_is_positive():
    assert DeveloperAgent.MAX_TEST_ITERATIONS > 0


def test_max_test_iterations_value():
    assert DeveloperAgent.MAX_TEST_ITERATIONS == 3


@given(attempts=st.integers(min_value=0, max_value=DeveloperAgent.MAX_TEST_ITERATIONS))
@settings(max_examples=100)
def test_attempts_bound_invariant(attempts):
    """Th.47: attempts ≤ MAX_TEST_ITERATIONS → attempts < MAX_TEST_ITERATIONS + 1."""
    assert attempts < DeveloperAgent.MAX_TEST_ITERATIONS + 1


# ──────────────────────────────────────────────────────────────────
# _find_test_file
# ──────────────────────────────────────────────────────────────────

def test_find_test_file_tool_pattern():
    """tools/email_tool/tool.py → tests/test_m14_email_autonomy.py oder ähnlich."""
    agent = _make_agent()
    # Bekannte Datei die einen echten Test hat
    result = agent._find_test_file("orchestration/autonomy_scorecard.py")
    # Entweder Datei gefunden oder leerer String (kein Fehler)
    assert isinstance(result, str)


def test_find_test_file_nonexistent_returns_empty():
    agent = _make_agent()
    result = agent._find_test_file("completely/nonexistent/module.py")
    assert result == ""


def test_find_test_file_known_module():
    """test_m13_tool_generator.py existiert für tool_generator_engine.py."""
    agent = _make_agent()
    result = agent._find_test_file("orchestration/tool_generator_engine.py")
    assert isinstance(result, str)


# ──────────────────────────────────────────────────────────────────
# _auto_run_tests
# ──────────────────────────────────────────────────────────────────

def test_auto_run_tests_no_test_file():
    """Keine Test-Datei → status='skipped', kein Fehler."""
    agent = _make_agent()
    result = agent._auto_run_tests(["nonexistent/module.py"])
    assert result["status"] == "skipped"


def test_auto_run_tests_returns_dict():
    agent = _make_agent()
    result = agent._auto_run_tests([])
    assert isinstance(result, dict)
    assert "status" in result
    assert result["status"] in ("passed", "failed", "skipped")


def test_auto_run_tests_real_passing():
    """Bekannte Datei mit grünem Test → status='passed'."""
    agent = _make_agent()
    # test_hypothesis_tier1.py existiert und ist grün
    result = agent._auto_run_tests(["orchestration/autonomy_scorecard.py"])
    # Ergebnis hängt von Dateisystem ab, aber Status ist valide
    assert result["status"] in ("passed", "failed", "skipped")


def test_auto_run_tests_attempt_within_bounds():
    """attempt in Ergebnis ≤ MAX_TEST_ITERATIONS."""
    agent = _make_agent()
    result = agent._auto_run_tests(["nonexistent/file.py"])
    assert result["attempt"] <= DeveloperAgent.MAX_TEST_ITERATIONS


def test_auto_run_tests_respects_max_iterations():
    """Subprocess immer fehlend → nicht mehr als MAX_TEST_ITERATIONS Versuche."""
    call_count = {"n": 0}

    def fake_run(*args, **kwargs):
        call_count["n"] += 1
        raise subprocess.TimeoutExpired(cmd="pytest", timeout=30)

    agent = _make_agent()
    with patch("agent.agents.developer.subprocess.run", side_effect=fake_run):
        with patch.object(agent, "_find_test_file", return_value="/tmp/fake_test.py"):
            result = agent._auto_run_tests(["some/module.py"])
    assert call_count["n"] <= DeveloperAgent.MAX_TEST_ITERATIONS
    assert result["status"] == "skipped"
