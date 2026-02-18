"""
Hardening-Tests fuer Agent-zu-Agent Delegation.
"""

import asyncio
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


class _DummyAgent:
    def __init__(self):
        self.conversation_session_id = None
        self.seen_sessions = []

    async def run(self, task: str) -> str:
        self.seen_sessions.append(self.conversation_session_id)
        return f"ok:{task}"


@pytest.mark.asyncio
async def test_agent_registry_alias_development_maps_to_developer():
    from agent.agent_registry import AgentRegistry

    registry = AgentRegistry()
    target = _DummyAgent()

    async def _fake_tools_description():
        return "tools"

    registry._get_tools_description = _fake_tools_description
    registry.register_spec(
        "developer",
        "developer",
        ["code"],
        lambda tools_description_string: target,
    )

    result = await registry.delegate(
        from_agent="executor",
        to_agent="development",
        task="fix bug",
    )

    assert result == "ok:fix bug"


@pytest.mark.asyncio
async def test_delegation_stack_is_task_local_for_parallel_calls():
    from agent.agent_registry import AgentRegistry

    registry = AgentRegistry()

    class _SlowAgent:
        async def run(self, task: str) -> str:
            await asyncio.sleep(0.02)
            return f"ok:{task}"

    async def _fake_tools_description():
        return "tools"

    registry._get_tools_description = _fake_tools_description
    registry.register_spec(
        "research",
        "research",
        ["research"],
        lambda tools_description_string: _SlowAgent(),
    )

    result_a, result_b = await asyncio.gather(
        registry.delegate(from_agent="meta", to_agent="research", task="a"),
        registry.delegate(from_agent="meta", to_agent="research", task="b"),
    )

    assert result_a == "ok:a"
    assert result_b == "ok:b"


@pytest.mark.asyncio
async def test_delegate_propagates_session_id_from_source_agent_and_restores_target():
    from agent.agent_registry import AgentRegistry

    registry = AgentRegistry()
    source = _DummyAgent()
    source.conversation_session_id = "sess-123"
    target = _DummyAgent()

    async def _fake_tools_description():
        return "tools"

    registry._get_tools_description = _fake_tools_description
    registry.register_spec(
        "executor",
        "executor",
        ["execution"],
        lambda tools_description_string: source,
    )
    registry.register_spec(
        "research",
        "research",
        ["research"],
        lambda tools_description_string: target,
    )

    # Simuliert bereits laufenden Source-Agenten im Registry-Cache.
    registry._instances["executor"] = source

    result = await registry.delegate(
        from_agent="executor",
        to_agent="research",
        task="remember context",
    )

    assert result == "ok:remember context"
    assert target.seen_sessions == ["sess-123"]
    assert target.conversation_session_id is None


@pytest.mark.asyncio
async def test_delegate_tool_returns_error_status_when_registry_reports_error(monkeypatch):
    import agent.agent_registry as agent_registry_module
    from tools.delegation_tool.tool import delegate_to_agent

    class _FakeRegistry:
        def normalize_agent_name(self, name: str) -> str:
            return name

        def get_current_agent_name(self):
            return "meta"

        async def delegate(self, from_agent: str, to_agent: str, task: str, session_id=None):
            assert from_agent == "meta"
            return "FEHLER: Agent nicht registriert"

    monkeypatch.setattr(agent_registry_module, "agent_registry", _FakeRegistry())

    result = await delegate_to_agent(agent_type="unknown", task="do x")

    assert result["status"] == "error"
    assert "FEHLER:" in result["error"]


@pytest.mark.asyncio
async def test_delegate_logs_canvas_edge_and_events(monkeypatch, tmp_path):
    import importlib
    from orchestration.canvas_store import CanvasStore
    from agent.agent_registry import AgentRegistry

    canvas_store_module = importlib.import_module("orchestration.canvas_store")
    test_store = CanvasStore(tmp_path / "canvas_store_delegation.json")
    monkeypatch.setattr(canvas_store_module, "canvas_store", test_store)

    registry = AgentRegistry()
    source = _DummyAgent()
    source.conversation_session_id = "sess-canvas-1"
    target = _DummyAgent()

    async def _fake_tools_description():
        return "tools"

    registry._get_tools_description = _fake_tools_description
    registry.register_spec(
        "executor",
        "executor",
        ["execution"],
        lambda tools_description_string: source,
    )
    registry.register_spec(
        "research",
        "research",
        ["research"],
        lambda tools_description_string: target,
    )

    # Source-Agent im Cache, damit Session-ID automatisch aufgeloest wird.
    registry._instances["executor"] = source

    canvas = test_store.create_canvas("Delegation Canvas")
    test_store.attach_session(canvas_id=canvas["id"], session_id="sess-canvas-1")

    result = await registry.delegate(
        from_agent="executor",
        to_agent="research",
        task="collect evidence",
    )

    assert result == "ok:collect evidence"

    loaded = test_store.get_canvas(canvas["id"])
    assert loaded is not None
    edges = [
        e for e in loaded["edges"]
        if e.get("source") == "agent:executor"
        and e.get("target") == "agent:research"
        and e.get("kind") == "delegation"
    ]
    assert edges, "Delegation-Edge wurde nicht geloggt"

    delegation_events = [
        ev for ev in loaded["events"]
        if ev.get("type") == "delegation" and ev.get("session_id") == "sess-canvas-1"
    ]
    assert any(ev.get("status") == "running" for ev in delegation_events)
    assert any(ev.get("status") == "completed" for ev in delegation_events)
