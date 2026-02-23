"""
M1 Gate-Tests — Registry-Vollstaendigkeit.

Sicherstellt dass alle 13 Agenten registriert sind und grundlegende
Delegationen funktionieren.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


class _DummyAgent:
    def __init__(self):
        self.conversation_session_id = None

    async def run(self, task: str) -> str:
        return f"ok:{task}"


def _make_registry_with_dummy(agent_name: str):
    from agent.agent_registry import AgentRegistry

    registry = AgentRegistry()

    async def _fake_tools():
        return "tools"

    registry._get_tools_description = _fake_tools
    registry.register_spec(
        agent_name,
        agent_name,
        [agent_name],
        lambda tools_description_string: _DummyAgent(),
    )
    return registry


def test_alle_agenten_registriert():
    """T1.1 — Alle 13 Agenten sind nach register_all_agents() verfuegbar."""
    from agent.agent_registry import AgentRegistry, register_all_agents

    # Frische Registry damit keine globalen Zustandsprobleme
    registry = AgentRegistry()

    # Temporaer globale registry ersetzen
    import agent.agent_registry as mod
    original = mod.agent_registry
    mod.agent_registry = registry
    try:
        register_all_agents()
        verfuegbar = set(registry.list_agents())
        erwartet = {
            "executor", "research", "reasoning", "creative", "developer",
            "visual", "meta", "image", "data", "document",
            "communication", "system", "shell",
        }
        assert erwartet.issubset(verfuegbar), (
            f"Fehlende Agenten: {erwartet - verfuegbar}"
        )
    finally:
        mod.agent_registry = original


@pytest.mark.asyncio
async def test_delegation_zu_data():
    """T1.2 — Delegation zu data-Agent moeglich (kein 'nicht registriert'-Fehler)."""
    registry = _make_registry_with_dummy("data")
    result = await registry.delegate(
        from_agent="executor",
        to_agent="data",
        task="analyse csv",
    )
    assert result["status"] == "success", f"Erwartet success, bekam: {result}"
    assert "ok:analyse csv" in result["result"]


@pytest.mark.asyncio
async def test_delegation_zu_shell():
    """T1.3 — Delegation zu shell-Agent moeglich."""
    registry = _make_registry_with_dummy("shell")
    result = await registry.delegate(
        from_agent="executor",
        to_agent="shell",
        task="list files",
    )
    assert result["status"] == "success", f"Erwartet success, bekam: {result}"
    assert "ok:list files" in result["result"]


@pytest.mark.asyncio
async def test_image_session_propagation():
    """T1.4 — Session-ID wird korrekt an image-Agent gesetzt."""
    from agent.agent_registry import AgentRegistry

    registry = AgentRegistry()

    class _SessionCapture:
        def __init__(self):
            self.conversation_session_id = None
            self.captured = None

        async def run(self, task: str) -> str:
            self.captured = self.conversation_session_id
            return "analyse done"

    target = _SessionCapture()

    async def _fake_tools():
        return "tools"

    registry._get_tools_description = _fake_tools
    registry.register_spec(
        "image",
        "image",
        ["image"],
        lambda tools_description_string: target,
    )

    await registry.delegate(
        from_agent="executor",
        to_agent="image",
        task="analyse bild",
        session_id="sess-img-42",
    )

    assert target.captured == "sess-img-42", (
        f"Session-ID nicht propagiert. Erhalten: {target.captured}"
    )


@pytest.mark.asyncio
async def test_kein_zirkular_data_executor():
    """T1.5 — Loop-Prevention funktioniert fuer neue Agenten."""
    from agent.agent_registry import AgentRegistry

    registry = AgentRegistry()

    async def _fake_tools():
        return "tools"

    registry._get_tools_description = _fake_tools
    registry.register_spec(
        "data", "data", ["data"],
        lambda tools_description_string: _DummyAgent(),
    )
    registry.register_spec(
        "executor", "executor", ["execution"],
        lambda tools_description_string: _DummyAgent(),
    )

    # Delegation-Stack simulieren: data ist bereits auf dem Stack
    token = registry._delegation_stack_var.set(("data",))
    try:
        result = await registry.delegate(
            from_agent="executor",
            to_agent="data",
            task="loop task",
        )
        assert result["status"] == "error"
        assert "Zirkulaer" in result["error"] or "zirkul" in result["error"].lower()
    finally:
        registry._delegation_stack_var.reset(token)
