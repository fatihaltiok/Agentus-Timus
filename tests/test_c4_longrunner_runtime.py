from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from server import mcp_server


class _FakeRequest:
    def __init__(self, payload):
        self._payload = payload

    async def json(self):
        return self._payload


@pytest.fixture(autouse=True)
def _stub_chat_side_effects(monkeypatch):
    monkeypatch.setattr(mcp_server, "_log_chat_interaction", lambda **kwargs: None)


def _capture_progress_events():
    captured: list[dict] = []

    def _callback(*args, **kwargs):
        stage = str(kwargs.get("stage") or (args[0] if args else "") or "").strip()
        payload = kwargs.get("payload")
        if not isinstance(payload, dict):
            payload = args[1] if len(args) > 1 and isinstance(args[1], dict) else {}
        captured.append({"stage": stage, "payload": dict(payload or {})})

    return captured, _callback


def _prepare_canvas_runtime(monkeypatch, tmp_path):
    mcp_server._chat_history.clear()
    monkeypatch.setenv("TIMUS_SESSION_STORAGE_ROOT", str(tmp_path))
    monkeypatch.setattr(mcp_server, "_semantic_store_chat_turn", lambda **kwargs: None)
    monkeypatch.setattr(mcp_server, "_semantic_recall_chat_turns", lambda **kwargs: [])


@pytest.mark.asyncio
async def test_canvas_chat_emits_longrun_started_progress_and_completed(monkeypatch, tmp_path):
    _prepare_canvas_runtime(monkeypatch, tmp_path)
    events: list[dict] = []
    monkeypatch.setattr(mcp_server, "_broadcast_sse", lambda event: events.append(dict(event)))

    async def fake_build_tools_description():
        return "tools"

    async def fake_get_agent_decision(query, session_id=None, request_id=None):
        return "executor"

    async def fake_run_agent(agent_name, query, tools_description, session_id=None):
        hook = getattr(fake_dispatcher, "_agent_progress_hook", None)
        if callable(hook):
            hook(
                {
                    "agent": agent_name,
                    "stage": "simple_live_lookup_start",
                    "payload": {"query": "KI auf X"},
                }
            )
        return "Hier ist die Antwort."

    fake_dispatcher = SimpleNamespace(
        get_agent_decision=fake_get_agent_decision,
        run_agent=fake_run_agent,
    )

    monkeypatch.setattr(mcp_server, "_build_tools_description", fake_build_tools_description)
    monkeypatch.setitem(sys.modules, "main_dispatcher", fake_dispatcher)

    response = await mcp_server.canvas_chat(
        _FakeRequest({"query": "Was ist neu?", "session_id": "c4_canvas"})
    )

    assert response["status"] == "success"
    longrun_events = [
        event
        for event in events
        if event.get("type") in {"run_started", "progress", "run_completed"}
    ]
    assert [event["type"] for event in longrun_events] == [
        "run_started",
        "progress",
        "run_completed",
    ]
    assert {event["run_id"] for event in longrun_events} == {longrun_events[0]["run_id"]}
    assert {event["request_id"] for event in longrun_events} == {longrun_events[0]["request_id"]}
    assert [event["seq"] for event in longrun_events] == [1, 2, 3]
    assert longrun_events[1]["stage"] == "simple_live_lookup_start"


@pytest.mark.asyncio
async def test_canvas_chat_emits_longrun_failed_on_runtime_error(monkeypatch, tmp_path):
    _prepare_canvas_runtime(monkeypatch, tmp_path)
    events: list[dict] = []
    monkeypatch.setattr(mcp_server, "_broadcast_sse", lambda event: events.append(dict(event)))

    async def fake_build_tools_description():
        return "tools"

    async def fake_get_agent_decision(query, session_id=None, request_id=None):
        return "executor"

    async def fake_run_agent(agent_name, query, tools_description, session_id=None):
        raise RuntimeError("boom")

    fake_dispatcher = SimpleNamespace(
        get_agent_decision=fake_get_agent_decision,
        run_agent=fake_run_agent,
    )

    monkeypatch.setattr(mcp_server, "_build_tools_description", fake_build_tools_description)
    monkeypatch.setitem(sys.modules, "main_dispatcher", fake_dispatcher)

    response = await mcp_server.canvas_chat(
        _FakeRequest({"query": "Was ist neu?", "session_id": "c4_canvas_fail"})
    )

    assert response.status_code == 500
    payload = json.loads(response.body)
    assert payload["status"] == "error"
    failed = [event for event in events if event.get("type") == "run_failed"]
    assert len(failed) == 1
    assert failed[0]["error_class"] == "RuntimeError"
    assert failed[0]["error_code"] == "canvas_chat_exception"


@pytest.mark.asyncio
async def test_agent_registry_transport_hook_emits_blocker_payload(monkeypatch):
    from agent.agent_registry import AgentRegistry
    import agent.agent_registry as agent_registry_mod

    registry = AgentRegistry()

    async def _fake_tools():
        return "tools"

    registry._get_tools_description = _fake_tools
    emitted: list[dict] = []
    monkeypatch.setattr(agent_registry_mod, "_delegation_transport_hook", lambda payload: emitted.append(payload))

    class _BlockingExecutor:
        conversation_session_id = None

        async def run(self, task: str) -> str:
            callback = getattr(self, "_delegation_progress_callback", None)
            if callable(callback):
                callback(
                    stage="fetch_primary_source_blocked",
                    payload={
                        "kind": "blocker",
                        "blocker_reason": "auth_required",
                        "message": "Login erforderlich.",
                        "user_action_required": "Bitte Zugang freigeben.",
                    },
                )
            return "warte auf nutzer"

    registry.register_spec(
        "executor",
        "executor",
        ["executor"],
        lambda tools_description_string: _BlockingExecutor(),
    )

    result = await registry.delegate(
        from_agent="meta",
        to_agent="executor",
        task="\n".join(
            [
                "# DELEGATION HANDOFF",
                "target_agent: executor",
                "goal: Fuehre eine kompakte aktuelle Live-Recherche aus.",
                "handoff_data:",
                "- task_type: simple_live_lookup",
            ]
        ),
    )

    assert result["status"] == "success"
    assert any(event.get("kind") == "blocker" for event in emitted)
    blocker = next(event for event in emitted if event.get("kind") == "blocker")
    assert blocker["stage"] == "fetch_primary_source_blocked"
    assert blocker["payload"]["blocker_reason"] == "auth_required"


@pytest.mark.asyncio
async def test_agent_registry_transport_hook_emits_partial_result(monkeypatch):
    from agent.agent_registry import AgentRegistry
    import agent.agent_registry as agent_registry_mod

    registry = AgentRegistry()

    async def _fake_tools():
        return "tools"

    registry._get_tools_description = _fake_tools
    emitted: list[dict] = []
    monkeypatch.setattr(agent_registry_mod, "_delegation_transport_hook", lambda payload: emitted.append(payload))

    class _PartialResearch:
        conversation_session_id = None

        async def run(self, task: str):
            return {"status": "partial", "result": "Drei Quellen bereits ausgewertet.", "error": "Timeout"}

    registry.register_spec(
        "research",
        "research",
        ["research"],
        lambda tools_description_string: _PartialResearch(),
    )

    result = await registry.delegate(
        from_agent="meta",
        to_agent="research",
        task="Suche aktuelle Quellen zu KI.",
    )

    assert result["status"] == "partial"
    partial = next(event for event in emitted if event.get("kind") == "partial_result")
    assert partial["stage"] == "delegation_partial"
    assert "Drei Quellen" in partial["payload"]["content_preview"]


@pytest.mark.asyncio
async def test_visual_nemotron_emits_blocker_progress():
    from agent.visual_nemotron_agent_v4 import VisualNemotronAgentV4

    emitted, callback = _capture_progress_events()
    agent = VisualNemotronAgentV4(progress_callback=callback)

    async def fake_screenshot():
        return object()

    async def fake_analyze(screenshot, step):
        return "Vision-Kontext"

    async def fake_generate_step(**kwargs):
        return {"status": "step_blocked", "actions": []}

    agent.desktop.screenshot = fake_screenshot
    agent.vision.analyze = fake_analyze
    agent.nemotron.generate_step = fake_generate_step

    result = await agent._execute_step_with_retry(
        step="Klicke den Login-Button",
        step_num=1,
        completed=[],
        pending=[],
    )

    assert result is False
    blocker = next(event for event in emitted if event["stage"] == "visual_step_blocked")
    assert blocker["payload"]["kind"] == "blocker"
    assert blocker["payload"]["blocker_reason"] == "step_blocked"
