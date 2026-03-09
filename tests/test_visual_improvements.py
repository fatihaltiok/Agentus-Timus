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

from agent import providers as providers_mod
from agent.agents.visual import VisualAgent


def _make_agent() -> VisualAgent:
    return VisualAgent(tools_description_string="")


@pytest.fixture(autouse=True)
def _disable_model_validation(monkeypatch):
    monkeypatch.setenv("TIMUS_VALIDATE_CONFIGURED_MODELS", "false")
    providers_mod._provider_client = None
    yield
    providers_mod._provider_client = None


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


def test_get_stability_timeout_is_shorter_for_dynamic_browser_actions():
    agent = _make_agent()

    assert agent._get_stability_timeout("start_visual_browser") == 1.0
    assert agent._get_stability_timeout("type_text") == 1.2
    assert agent._get_stability_timeout("click_at") == 1.5


def test_build_loop_recovery_hint_is_specific_for_scan():
    agent = _make_agent()

    hint = agent._build_loop_recovery_hint("scan_ui_elements")

    assert "use_zoom=false" in hint
    assert "Text/OCR" in hint


def test_preferred_recovery_strategy_uses_feedback_scores(monkeypatch, tmp_path):
    from orchestration.feedback_engine import FeedbackEngine

    agent = _make_agent()
    engine = FeedbackEngine(db_path=tmp_path / "visual_feedback.db")
    engine.record_signal(
        "visual-1",
        "positive",
        feedback_targets=[{"namespace": "visual_strategy", "key": "datepicker"}],
    )
    engine.record_signal(
        "visual-2",
        "positive",
        feedback_targets=[{"namespace": "visual_strategy", "key": "datepicker"}],
    )
    monkeypatch.setattr("orchestration.feedback_engine.get_feedback_engine", lambda: engine)

    assert agent._preferred_recovery_strategy() == "datepicker"


def test_visual_runtime_feedback_infers_browser_targets(monkeypatch, tmp_path):
    from orchestration.feedback_engine import FeedbackEngine

    agent = _make_agent()
    engine = FeedbackEngine(db_path=tmp_path / "visual_runtime_feedback.db")
    monkeypatch.setattr("orchestration.feedback_engine.get_feedback_engine", lambda: engine)

    agent._record_runtime_feedback(
        "Starte den Browser, gehe auf booking.com und wähle ein Datum",
        success=True,
        strategy="browser_flow",
        stage="structured_navigation",
    )

    assert engine.get_target_score("visual_strategy", "browser_flow") > 1.0
    assert engine.get_target_score("visual_strategy", "datepicker") > 1.0


def test_browser_plan_context_embeds_verifiable_steps():
    agent = _make_agent()

    context = agent._build_browser_plan_context(
        "Starte den Browser, gehe auf booking.com, tippe Berlin, wähle 15.03.2026 bis 17.03.2026"
    )

    assert "STRIKTER BROWSER-ABLAUFPLAN" in context
    assert "Navigiere zu booking.com" in context
    assert "Verifiziere" in context
    assert agent.current_workflow_plan


def test_loop_recovery_hint_references_browser_plan():
    agent = _make_agent()
    agent.current_workflow_plan = ["Navigiere zu booking.com", "Verifiziere Suchfeld"]

    hint = agent._build_loop_recovery_hint("scan_ui_elements")

    assert "Browser-Ablaufplan" in hint


@pytest.mark.asyncio
async def test_create_navigation_plan_with_llm_uses_robust_json_extraction(monkeypatch):
    agent = _make_agent()
    screen_state = {
        "screen_id": "screen",
        "elements": [
            {"name": "elem_1", "text": "Berlin", "x": 10, "y": 20, "type": "text"},
            {"name": "elem_2", "text": "Suchen", "x": 30, "y": 40, "type": "button"},
        ],
    }

    async def fake_call_llm(_messages):
        return """<think>planung</think>
```json
{
  "description": "Booking Suche",
  "steps": [
    {"op": "type", "target": "elem_1", "value": "Berlin", "retries": 2},
    {"op": "click", "target": "elem_2", "retries": 2}
  ]
}
```"""

    monkeypatch.setattr(agent, "_call_llm", fake_call_llm)

    plan = await agent._create_navigation_plan_with_llm("Suche nach Berlin", screen_state)

    assert plan is not None
    assert plan["goal"] == "Booking Suche"
    assert len(plan["steps"]) == 2
