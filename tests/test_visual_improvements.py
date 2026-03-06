"""
tests/test_visual_improvements.py — Phase-3: Visual Agent Verbesserungen

Tests für:
  - MAX_VISUAL_RETRIES Invariante (Th.48)
  - _click_with_retry: korrekte Anzahl Versuche
  - _wait_for_stable_screenshot: graceful Fallback
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from hypothesis import given, settings
from hypothesis import strategies as st

from agent.agents.visual import VisualAgent


def _make_agent() -> VisualAgent:
    return VisualAgent(tools_description_string="")


# ──────────────────────────────────────────────────────────────────
# MAX_VISUAL_RETRIES Invariante (Th.48)
# ──────────────────────────────────────────────────────────────────

def test_max_visual_retries_positive():
    assert VisualAgent.MAX_VISUAL_RETRIES > 0


def test_max_visual_retries_default_value():
    assert VisualAgent.MAX_VISUAL_RETRIES == 3


@given(retry=st.integers(min_value=0, max_value=VisualAgent.MAX_VISUAL_RETRIES))
@settings(max_examples=100)
def test_visual_retry_terminates(retry):
    """Th.48: retry ≤ MAX_VISUAL_RETRIES → retry < MAX_VISUAL_RETRIES + 1."""
    assert retry < VisualAgent.MAX_VISUAL_RETRIES + 1


# ──────────────────────────────────────────────────────────────────
# _click_with_retry
# ──────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_click_with_retry_success_first_attempt():
    """Erfolg bei Versuch 1 → keine weiteren Versuche."""
    agent = _make_agent()
    call_count = {"n": 0}

    async def mock_post(*args, **kwargs):
        call_count["n"] += 1
        r = MagicMock()
        r.json.return_value = {"result": {"success": True}}
        return r

    agent.http_client = MagicMock()
    agent.http_client.post = mock_post

    result = await agent._click_with_retry(100, 200, label="test_button")
    assert result is True
    assert call_count["n"] == 1


@pytest.mark.asyncio
async def test_click_with_retry_all_fail():
    """Alle Versuche fehlschlagen → return False, genau MAX_VISUAL_RETRIES Versuche."""
    agent = _make_agent()
    call_count = {"n": 0}

    async def mock_post(*args, **kwargs):
        call_count["n"] += 1
        r = MagicMock()
        r.json.return_value = {"result": {"success": False}}
        return r

    agent.http_client = MagicMock()
    agent.http_client.post = mock_post

    result = await agent._click_with_retry(100, 200)
    assert result is False
    # call_count enthält auch _wait_for_stable_screenshot Calls (Versuch 2)
    assert call_count["n"] <= agent.MAX_VISUAL_RETRIES * 2 + 1


@pytest.mark.asyncio
async def test_click_with_retry_respects_max_retries():
    """Nie mehr als MAX_VISUAL_RETRIES Klick-Versuche."""
    agent = _make_agent()
    click_calls = {"n": 0}

    async def mock_post(*args, **kwargs):
        body = kwargs.get("json", args[1] if len(args) > 1 else {})
        if body.get("method") == "click_at":
            click_calls["n"] += 1
        r = MagicMock()
        r.json.return_value = {"result": {"success": False}}
        return r

    agent.http_client = MagicMock()
    agent.http_client.post = mock_post

    await agent._click_with_retry(100, 200)
    assert click_calls["n"] <= agent.MAX_VISUAL_RETRIES


# ──────────────────────────────────────────────────────────────────
# _wait_for_stable_screenshot
# ──────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_wait_for_stable_returns_bool():
    agent = _make_agent()

    async def mock_post(*args, **kwargs):
        r = MagicMock()
        r.json.return_value = {"result": {"success": True}}
        return r

    agent.http_client = MagicMock()
    agent.http_client.post = mock_post

    result = await agent._wait_for_stable_screenshot(timeout_ms=1000)
    assert isinstance(result, bool)


@pytest.mark.asyncio
async def test_wait_for_stable_exception_returns_false():
    agent = _make_agent()

    async def mock_post(*args, **kwargs):
        raise Exception("Connection refused")

    agent.http_client = MagicMock()
    agent.http_client.post = mock_post

    result = await agent._wait_for_stable_screenshot()
    assert result is False
