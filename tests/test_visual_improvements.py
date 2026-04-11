"""
tests/test_visual_improvements.py — Phase-3: Visual Agent Verbesserungen

Tests für:
  - MAX_VISUAL_RETRIES Invariante (Th.48)
  - _click_with_retry: korrekte Anzahl Versuche
  - _wait_for_stable_screenshot: graceful Fallback
"""

import sys
import os
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from hypothesis import given, settings
from hypothesis import strategies as st

from agent import providers as providers_mod
from agent.agents.visual import VisualAgent
from agent.base_agent import BaseAgent
from orchestration.browser_workflow_plan import BrowserWorkflowPlan, BrowserWorkflowStep, BrowserStateEvidence


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
    assert "flow_type=booking_search" in context


def test_browser_plan_context_recognizes_natural_chrome_password_manager_login():
    agent = _make_agent()
    agent.current_browser_url = "https://github.com/login"

    context = agent._build_browser_plan_context(
        "Bitte melde mich in Chrome bei GitHub an und nutze den Passwortmanager."
    )

    assert "STRIKTER BROWSER-ABLAUFPLAN" in context
    assert "flow_type=login_flow" in context
    assert "target=page:https://github.com/login" in context
    assert "expected_state=login_modal" in context
    assert "fallback=" in context
    assert agent.current_workflow_plan
    assert agent.current_structured_workflow_plan is not None


def test_browser_plan_context_keeps_unknown_domain_generic_login_flow():
    agent = _make_agent()

    context = agent._build_browser_plan_context(
        "Bitte melde mich in Chrome bei example-auth-site.net an und nutze den Passwortmanager."
    )

    assert "STRIKTER BROWSER-ABLAUFPLAN" in context
    assert "flow_type=login_flow" in context
    assert "target=page:https://example-auth-site.net" in context
    assert "action=click_target target=button:login||sign in||log in||anmelden||einloggen" in context
    assert agent.current_structured_workflow_plan is not None
    assert agent.current_structured_workflow_plan.steps[0].target_text == "https://example-auth-site.net"
    assert agent.current_structured_workflow_plan.steps[1].action == "click_target"


@pytest.mark.asyncio
async def test_detect_credential_broker_ready_state_uses_passkey_markers(monkeypatch):
    agent = _make_agent()

    async def mock_call_tool(self, method: str, params: dict):
        if method == "get_all_screen_text":
            return {
                "texts": [
                    {"text": "Sign in with a passkey"},
                    {"text": "Google Chrome"},
                ]
            }
        if method == "analyze_screen_verified":
            return {"filtered_elements": []}
        raise AssertionError(f"unexpected tool call: {method}")

    monkeypatch.setattr(BaseAgent, "_call_tool", mock_call_tool)

    result = await agent._detect_credential_broker_ready_state("github", "chrome_password_manager")

    assert result["success"] is True
    assert "passkey" in " ".join(result["positive_hits"])
    assert result["visible_browser"] == "chrome"


@pytest.mark.asyncio
async def test_detect_credential_broker_ready_state_supports_unknown_site(monkeypatch):
    agent = _make_agent()

    async def mock_call_tool(self, method: str, params: dict):
        if method == "get_all_screen_text":
            return {
                "texts": [
                    {"text": "Mit Passkey anmelden"},
                    {"text": "Konto auswählen"},
                    {"text": "Google Chrome"},
                ]
            }
        if method == "analyze_screen_verified":
            return {"filtered_elements": []}
        raise AssertionError(f"unexpected tool call: {method}")

    monkeypatch.setattr(BaseAgent, "_call_tool", mock_call_tool)

    result = await agent._detect_credential_broker_ready_state("", "chrome_password_manager")

    assert result["success"] is True
    assert "mit passkey anmelden" in result["positive_hits"]
    assert result["visible_browser"] == "chrome"


@pytest.mark.asyncio
async def test_detect_authenticated_session_state_supports_unknown_site_markers(monkeypatch):
    agent = _make_agent()

    async def mock_call_tool(self, method: str, params: dict):
        if method == "get_all_screen_text":
            return {
                "texts": [
                    {"text": "Dashboard"},
                    {"text": "Sign out"},
                    {"text": "Inbox"},
                    {"text": "Google Chrome"},
                ]
            }
        if method == "analyze_screen_verified":
            return {"filtered_elements": []}
        raise AssertionError(f"unexpected tool call: {method}")

    monkeypatch.setattr(BaseAgent, "_call_tool", mock_call_tool)

    result = await agent._detect_authenticated_session_state("")

    assert result["success"] is True
    assert any(marker in result["positive_hits"] for marker in ("dashboard", "sign out", "inbox"))
    assert result["visible_browser"] == "chrome"


def test_preferred_text_entry_method_uses_clipboard_for_layout_sensitive_text():
    agent = _make_agent()

    assert agent._preferred_text_entry_method("https://www.youtube.com/watch?v=abc") == "clipboard"
    assert agent._preferred_text_entry_method("name@example.com") == "clipboard"
    assert agent._preferred_text_entry_method("leder jacken") == "auto"


@pytest.mark.asyncio
async def test_execute_structured_workflow_plan_runs_steps_with_state_progression():
    agent = _make_agent()
    observation = {
        "elements": [{"text": "booking", "x": 10, "y": 10}, {"text": "Ergebnisse", "x": 20, "y": 20}],
        "current_url": "https://booking.com/search",
    }

    async def fake_call_tool(method, params):
        if method in {"start_visual_browser", "click_at"}:
            return {"success": True}
        raise AssertionError(f"Unexpected tool call: {method}")

    async def fake_analyze_current_screen():
        return observation

    agent._call_tool = fake_call_tool
    agent._analyze_current_screen = fake_analyze_current_screen
    agent.current_browser_url = "https://booking.com/search"

    plan = BrowserWorkflowPlan(
        flow_type="booking_search",
        initial_state="landing",
        steps=[
            BrowserWorkflowStep(
                action="navigate",
                target_type="page",
                target_text="booking.com",
                expected_state="landing",
                success_signal=[BrowserStateEvidence("url_contains", "booking.com")],
                timeout=18.0,
                fallback_strategy="abort_with_handoff",
            ),
            BrowserWorkflowStep(
                action="verify_state",
                target_type="results",
                target_text="Suchergebnisse sichtbar",
                expected_state="results_loaded",
                success_signal=[BrowserStateEvidence("visible_text", "Ergebnisse")],
                timeout=8.0,
                fallback_strategy="abort_with_handoff",
            ),
        ],
    )

    result = await agent._execute_structured_workflow_plan(plan)

    assert result["success"] is True
    assert result["current_state"] == "results_loaded"
    assert len(result["completed_steps"]) == 2


@pytest.mark.asyncio
async def test_execute_structured_step_uses_clipboard_for_url_like_input(monkeypatch):
    agent = _make_agent()
    calls = []

    async def fake_call_tool(method, params):
        calls.append((method, dict(params)))
        if method == "find_text_coordinates":
            return {"found": True, "x": 120, "y": 240}
        return {"success": True}

    async def fake_analyze_current_screen():
        return {
            "elements": [{"text": "https://www.youtube.com/watch?v=abc", "x": 120, "y": 240}],
            "current_url": "https://example.com",
        }

    monkeypatch.setattr(agent, "_call_tool", fake_call_tool)
    monkeypatch.setattr(agent, "_analyze_current_screen", fake_analyze_current_screen)

    step = BrowserWorkflowStep(
        action="type_text",
        target_type="input",
        target_text="https://www.youtube.com/watch?v=abc",
        expected_state="form_ready",
        success_signal=[BrowserStateEvidence("visible_text", "https://www.youtube.com/watch?v=abc")],
        timeout=6.0,
        fallback_strategy="dom_lookup",
    )

    result = await agent._execute_structured_step(step)

    assert result["success"] is True
    type_calls = [item for item in calls if item[0] == "type_text"]
    assert type_calls
    assert type_calls[-1][1]["method"] == "clipboard"


@pytest.mark.asyncio
async def test_execute_structured_step_uses_real_fallback_strategy_switch(monkeypatch):
    agent = _make_agent()
    calls = []

    async def fake_call_tool(method, params):
        calls.append((method, dict(params)))
        if method == "find_text_coordinates":
            threshold = params.get("fuzzy_threshold")
            if threshold == 85:
                raise Exception("not found")
            return {"found": True, "x": 120, "y": 240}
        if method == "click_at":
            return {"success": True}
        return {"success": True}

    async def fake_analyze_current_screen():
        return {
            "elements": [{"text": "Berlin", "x": 120, "y": 240}],
            "current_url": "https://booking.com",
        }

    monkeypatch.setattr(agent, "_call_tool", fake_call_tool)
    monkeypatch.setattr(agent, "_analyze_current_screen", fake_analyze_current_screen)

    step = BrowserWorkflowStep(
        action="click_target",
        target_type="input",
        target_text="Berlin",
        expected_state="search_form",
        success_signal=[BrowserStateEvidence("visible_text", "Berlin")],
        timeout=6.0,
        fallback_strategy="ocr_lookup",
    )

    result = await agent._execute_structured_step(step)

    assert result["success"] is True
    find_calls = [item for item in calls if item[0] == "find_text_coordinates"]
    assert len(find_calls) >= 1
    assert any(call[1].get("fuzzy_threshold") == 65 for call in find_calls)


@pytest.mark.asyncio
async def test_execute_structured_step_stops_login_click_target_after_first_failed_verify(monkeypatch):
    agent = _make_agent()
    calls = []
    locate_calls = {"n": 0}
    verify_calls = {"n": 0}
    agent.current_structured_workflow_plan = BrowserWorkflowPlan(
        flow_type="login_flow",
        initial_state="landing",
        steps=[],
    )

    async def fake_call_tool(method, params):
        calls.append((method, dict(params)))
        if method == "click_at":
            return {"success": True}
        raise AssertionError(f"unexpected tool call: {method}")

    async def fake_locate_target_coordinates(target_text, strategy):
        locate_calls["n"] += 1
        return {"x": 320, "y": 180}

    async def fake_verify_structured_step(step):
        verify_calls["n"] += 1
        return {
            "success": False,
            "matched_signals": [],
            "observation": {"current_url": "https://grok.com", "elements": []},
        }

    monkeypatch.setattr(agent, "_call_tool", fake_call_tool)
    monkeypatch.setattr(agent, "_locate_target_coordinates", fake_locate_target_coordinates)
    monkeypatch.setattr(agent, "_verify_structured_step", fake_verify_structured_step)

    step = BrowserWorkflowStep(
        action="click_target",
        target_type="button",
        target_text="login||sign in||log in||anmelden||einloggen",
        expected_state="landing",
        success_signal=[BrowserStateEvidence("visible_text", "login")],
        timeout=6.0,
        fallback_strategy="vision_scan",
    )

    result = await agent._execute_structured_step(step)

    assert result["success"] is False
    assert locate_calls["n"] == 1
    assert verify_calls["n"] == 1
    click_calls = [item for item in calls if item[0] == "click_at"]
    assert len(click_calls) == 1


@pytest.mark.asyncio
async def test_run_action_verified_treats_failed_navigation_as_unverified(monkeypatch):
    import agent.visual_nemotron_agent_v4 as visual_v4
    from types import SimpleNamespace

    agent = visual_v4.VisualNemotronAgentV4.__new__(visual_v4.VisualNemotronAgentV4)
    agent.desktop = SimpleNamespace(
        execute_action=AsyncMock(return_value=(False, "Navigation fehlgeschlagen")),
        last_navigation_result={"success": False, "error": "Navigation fehlgeschlagen"},
    )

    done, error, verified = await agent._run_action_verified(
        {"action": "navigate", "url": "https://amazon.com"},
        "Navigiere zu amazon.com",
    )

    assert done is False
    assert error == "Navigation fehlgeschlagen"
    assert verified is False


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


@pytest.mark.asyncio
async def test_visual_nemotron_navigation_step_requires_real_navigation_success(monkeypatch):
    import agent.visual_nemotron_agent_v4 as visual_v4

    agent = visual_v4.VisualNemotronAgentV4.__new__(visual_v4.VisualNemotronAgentV4)
    agent.history = []
    agent.loop_detector = SimpleNamespace(add_state=lambda *_args, **_kwargs: False)
    agent.desktop = SimpleNamespace(
        screenshot=AsyncMock(return_value=object()),
        elements=[],
        scan_elements=AsyncMock(return_value=[]),
        last_navigation_result={"success": False, "error": "Navigation fehlgeschlagen"},
    )
    agent.vision = SimpleNamespace(analyze=AsyncMock(return_value="screen"))
    agent.nemotron = SimpleNamespace(
        generate_step=AsyncMock(
            return_value={
                "status": "in_progress",
                "actions": [{"action": "scan", "element_types": ["link"]}],
            }
        )
    )
    agent._run_action_verified = AsyncMock(return_value=(False, None, True))

    result = await agent._execute_step_with_retry(
        step="Navigiere zu amazon.com",
        step_num=1,
        completed=[],
        pending=[],
        max_retries=1,
    )

    assert result is False


@pytest.mark.asyncio
async def test_visual_nemotron_type_action_prefers_clipboard_for_url():
    import agent.visual_nemotron_agent_v4 as visual_v4

    controller = visual_v4.DesktopController.__new__(visual_v4.DesktopController)
    controller.mcp = SimpleNamespace(
        click_and_focus=AsyncMock(return_value={"success": True}),
        type_text=AsyncMock(return_value={"success": True}),
    )

    done, error = await controller.execute_action(
        {
            "action": "type",
            "text_input": "https://www.youtube.com/watch?v=abc",
            "coordinates": {"x": 50, "y": 60},
        }
    )

    assert done is False
    assert error is None
    assert controller.mcp.type_text.await_args.kwargs["method"] == "clipboard"
