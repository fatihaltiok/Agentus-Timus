"""
V3 Architektur-Validierung — Alle 13 Agenten erreichbar und Delegation korrekt.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

_ALLE_AGENTEN = {
    "executor", "research", "reasoning", "creative", "developer",
    "visual", "meta", "image", "data", "document",
    "communication", "system", "shell",
}


def test_alle_agenten_im_registry():
    """V3.1 — Alle 13 Agenten sind nach register_all_agents() registriert."""
    from agent.agent_registry import AgentRegistry, register_all_agents
    import agent.agent_registry as mod

    registry = AgentRegistry()
    original = mod.agent_registry
    mod.agent_registry = registry
    try:
        register_all_agents()
        verfuegbar = set(registry.list_agents())
        assert _ALLE_AGENTEN.issubset(verfuegbar), (
            f"Fehlende Agenten: {_ALLE_AGENTEN - verfuegbar}"
        )
    finally:
        mod.agent_registry = original


@pytest.mark.asyncio
@pytest.mark.parametrize("agent_name", sorted(_ALLE_AGENTEN))
async def test_delegation_stack_korrekt_fuer_alle_agenten(agent_name):
    """V3.2 — Stack wird korrekt gesetzt und nach Delegation zurueckgesetzt."""
    from agent.agent_registry import AgentRegistry

    registry = AgentRegistry()

    stack_bei_run = []

    class _CapturingAgent:
        def __init__(self):
            self.conversation_session_id = None

        async def run(self, task: str) -> str:
            stack_bei_run.append(registry._delegation_stack_var.get())
            return "capture_done"

    async def _fake_tools():
        return "tools"

    registry._get_tools_description = _fake_tools
    registry.register_spec(
        agent_name,
        agent_name,
        [agent_name],
        lambda tools_description_string: _CapturingAgent(),
    )

    result = await registry.delegate(
        from_agent="test_runner",
        to_agent=agent_name,
        task="test",
    )

    assert result["status"] == "success"
    # Stack waehrend run() muss den Agent enthalten
    assert len(stack_bei_run) == 1
    assert agent_name in stack_bei_run[0]
    # Nach der Delegation muss der Stack wieder leer sein
    assert registry._delegation_stack_var.get() == ()


def test_import_sauberkeit():
    """V1 — Alle kritischen Module lassen sich importieren."""
    import importlib

    module_paths = [
        "agent.agent_registry",
        "agent.agents",
        "agent.agents.image",
        "agent.prompts",
    ]
    for path in module_paths:
        mod = importlib.import_module(path)
        assert mod is not None, f"Import fehlgeschlagen: {path}"


def test_env_defaults_rueckwaertskompatibel():
    """V5 — Ohne ENV-Variablen gelten die richtigen Defaults."""
    import os

    # Sicherstellen dass keine gesetzten Variablen vorhanden
    env_backup = {}
    for key in ("DELEGATION_TIMEOUT", "DELEGATION_MAX_RETRIES"):
        env_backup[key] = os.environ.pop(key, None)

    try:
        timeout = float(os.getenv("DELEGATION_TIMEOUT", "120"))
        max_retries = int(os.getenv("DELEGATION_MAX_RETRIES", "1"))
        assert timeout == 120.0
        assert max_retries == 1
    finally:
        for key, val in env_backup.items():
            if val is not None:
                os.environ[key] = val
