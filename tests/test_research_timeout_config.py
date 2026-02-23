"""Tests für B.1 — RESEARCH_TIMEOUT separater Timeout für Research-Agent."""
import asyncio
import pytest
from unittest.mock import AsyncMock, patch, MagicMock


def _make_registry_with_agent(agent_name: str):
    """Erstellt eine AgentRegistry mit vorinstanziiertem Mock-Agent."""
    from agent.agent_registry import AgentRegistry

    registry = AgentRegistry()
    mock_agent = MagicMock()
    mock_agent.conversation_session_id = None
    # run() gibt sofort "done" zurück (kein echtes Warten)
    mock_agent.run = AsyncMock(return_value="done")

    registry.register_spec(agent_name, agent_name, ["test"], MagicMock())
    # Direkt in _instances eintragen → _get_or_create macht keinen HTTP-Call
    registry._instances[agent_name] = mock_agent
    return registry, mock_agent


class TestResearchTimeoutConfig:

    @pytest.mark.asyncio
    async def test_research_timeout_default_180s(self, monkeypatch):
        """Ohne ENV-Variable: Research-Agent bekommt 180s Timeout."""
        monkeypatch.delenv("RESEARCH_TIMEOUT", raising=False)
        monkeypatch.delenv("DELEGATION_TIMEOUT", raising=False)

        timeout_used = []

        async def mock_wait_for(coro, timeout):
            timeout_used.append(timeout)
            # Coroutine muss "konsumiert" werden
            try:
                return await coro
            except Exception:
                return "done"

        registry, _ = _make_registry_with_agent("research")

        with patch("agent.agent_registry.asyncio.wait_for", side_effect=mock_wait_for):
            result = await registry.delegate("executor", "research", "test task")

        assert len(timeout_used) >= 1
        assert timeout_used[0] == pytest.approx(180.0), (
            f"Research-Agent sollte 180s Timeout haben, bekam {timeout_used[0]}"
        )

    @pytest.mark.asyncio
    async def test_research_timeout_env_override(self, monkeypatch):
        """RESEARCH_TIMEOUT=60 überschreibt den Default."""
        monkeypatch.setenv("RESEARCH_TIMEOUT", "60")

        timeout_used = []

        async def mock_wait_for(coro, timeout):
            timeout_used.append(timeout)
            try:
                return await coro
            except Exception:
                return "done"

        registry, _ = _make_registry_with_agent("research")

        with patch("agent.agent_registry.asyncio.wait_for", side_effect=mock_wait_for):
            result = await registry.delegate("executor", "research", "test task")

        assert len(timeout_used) >= 1
        assert timeout_used[0] == pytest.approx(60.0), (
            f"Erwartet 60s, bekam {timeout_used[0]}"
        )

    @pytest.mark.asyncio
    async def test_global_timeout_still_120s_for_other_agents(self, monkeypatch):
        """Andere Agenten bekommen den globalen DELEGATION_TIMEOUT (120s)."""
        monkeypatch.delenv("DELEGATION_TIMEOUT", raising=False)
        monkeypatch.delenv("RESEARCH_TIMEOUT", raising=False)

        for agent_name in ("executor", "meta"):
            timeout_used = []

            async def mock_wait_for(coro, timeout, _agent=agent_name):
                timeout_used.append(timeout)
                try:
                    return await coro
                except Exception:
                    return "done"

            registry, _ = _make_registry_with_agent(agent_name)

            with patch("agent.agent_registry.asyncio.wait_for", side_effect=mock_wait_for):
                await registry.delegate("research", agent_name, "test task")

            if timeout_used:
                assert timeout_used[0] == pytest.approx(120.0), (
                    f"Agent '{agent_name}' sollte 120s haben, bekam {timeout_used[0]}"
                )

    def test_deep_research_fact_limit_is_3(self):
        """_deep_verify_facts verifiziert max. 3 Fakten (war 10)."""
        import inspect
        from tools.deep_research import tool as dr_tool
        source = inspect.getsource(dr_tool)
        assert "group_idx < 3" in source, (
            "deep_research/tool.py: Limit sollte auf 3 gesetzt sein (war 10)"
        )

    def test_research_timeout_in_env_example(self):
        """RESEARCH_TIMEOUT ist in .env.example dokumentiert."""
        from pathlib import Path
        env_example = Path(__file__).parent.parent / ".env.example"
        content = env_example.read_text()
        assert "RESEARCH_TIMEOUT" in content
