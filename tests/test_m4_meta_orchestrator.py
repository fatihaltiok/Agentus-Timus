"""
M4 Gate-Tests — Meta-Agent als aktiver Orchestrator.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def _base_registry():
    from agent.agent_registry import AgentRegistry

    registry = AgentRegistry()

    async def _fake_tools():
        return "tools"

    registry._get_tools_description = _fake_tools
    return registry


def test_meta_system_prompt_enthaelt_delegation_sektion():
    """T4.1-Grundlage — META_SYSTEM_PROMPT hat DELEGATION-Sektion."""
    from agent.prompts import META_SYSTEM_PROMPT

    assert "DELEGATION" in META_SYSTEM_PROMPT, (
        "META_SYSTEM_PROMPT fehlt DELEGATION-Sektion"
    )
    assert "delegate_to_agent" in META_SYSTEM_PROMPT, (
        "META_SYSTEM_PROMPT fehlt delegate_to_agent Beispiel"
    )
    assert "research" in META_SYSTEM_PROMPT
    assert "data" in META_SYSTEM_PROMPT
    assert "developer" in META_SYSTEM_PROMPT


def test_meta_system_prompt_routes_browser_workflows_to_visual():
    from agent.prompts import META_SYSTEM_PROMPT

    assert 'delegate_to_agent("visual"' in META_SYSTEM_PROMPT
    assert "Browser-/Webseiten-Bedienung" in META_SYSTEM_PROMPT
    assert "Shell ist NUR fuer" in META_SYSTEM_PROMPT
    assert "Jede Visual-Teilaufgabe braucht einen klaren Erfolgshinweis" in META_SYSTEM_PROMPT


def test_meta_system_prompt_prefers_structured_delegation_handoffs():
    from agent.prompts import META_SYSTEM_PROMPT

    assert "STRUKTURIERTE DELEGATION" in META_SYSTEM_PROMPT
    assert "# DELEGATION HANDOFF" in META_SYSTEM_PROMPT
    assert "expected_output" in META_SYSTEM_PROMPT
    assert "success_signal" in META_SYSTEM_PROMPT


def test_meta_delegation_aliases():
    """T4.3 — 'koordinator' und 'orchestrator' sind Aliases fuer 'meta'."""
    from agent.agent_registry import AgentRegistry

    registry = AgentRegistry()
    assert registry.normalize_agent_name("koordinator") == "meta"
    assert registry.normalize_agent_name("orchestrator") == "meta"


@pytest.mark.asyncio
async def test_meta_delegation_tiefe_ok():
    """T4.3 — meta → research → executor ist erlaubt (Tiefe = 3)."""
    registry = _base_registry()

    class _DummyAgent:
        async def run(self, task: str) -> str:
            return f"ok:{task}"

    registry.register_spec("meta", "meta", ["meta"], lambda tools_description_string: _DummyAgent())
    registry.register_spec("research", "research", ["research"], lambda tools_description_string: _DummyAgent())
    registry.register_spec("executor", "executor", ["execution"], lambda tools_description_string: _DummyAgent())

    # Simuliere Stack meta → research (Tiefe 2), dann executor (Tiefe 3 — erlaubt)
    token = registry._delegation_stack_var.set(("meta", "research"))
    try:
        result = await registry.delegate(
            from_agent="research",
            to_agent="executor",
            task="subtask",
        )
        assert result["status"] == "success", f"Tiefe 3 soll erlaubt sein: {result}"
    finally:
        registry._delegation_stack_var.reset(token)


@pytest.mark.asyncio
async def test_meta_kein_zirkular():
    """T4.4 — meta → meta wird verhindert."""
    registry = _base_registry()

    class _DummyAgent:
        async def run(self, task: str) -> str:
            return "ok"

    registry.register_spec("meta", "meta", ["meta"], lambda tools_description_string: _DummyAgent())

    # Simuliere dass meta bereits auf dem Stack ist
    token = registry._delegation_stack_var.set(("meta",))
    try:
        result = await registry.delegate(
            from_agent="executor",
            to_agent="meta",
            task="loop task",
        )
        assert result["status"] == "error"
        assert "Zirkulaer" in result["error"] or "zirkul" in result["error"].lower()
    finally:
        registry._delegation_stack_var.reset(token)


def test_neue_aliases_vorhanden():
    """T4.3b — Alle M3-Aliases sind registriert."""
    from agent.agent_registry import AgentRegistry

    registry = AgentRegistry()
    assert registry.normalize_agent_name("daten") == "data"
    assert registry.normalize_agent_name("bash") == "shell"
    assert registry.normalize_agent_name("terminal") == "shell"
    assert registry.normalize_agent_name("monitoring") == "system"
