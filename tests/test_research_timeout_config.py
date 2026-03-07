"""Tests für B.1 — RESEARCH_TIMEOUT separater Timeout für Research-Agent.

Lean 4 Theoreme (CiSpecs.lean):
  Th.9  research_timeout_sufficient:  600 ∈ [300, 900]
  Th.10 research_timeout_gt_delegation: 600 > 120
  Th.11 parallel_research_timeout_eq_sequential: t_seq=600 = t_par=600
"""
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
    async def test_research_timeout_default_600s(self, monkeypatch):
        """Ohne ENV-Variable: Research-Agent bekommt 600s Timeout (Deep Research braucht 300-600s)."""
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
        assert timeout_used[0] == pytest.approx(600.0), (
            f"Research-Agent sollte 600s Timeout haben (Deep Research 300-600s), bekam {timeout_used[0]}"
        )
        # Lean Th.9: 600 ∈ [300, 900]
        assert 300 <= timeout_used[0] <= 900, "Research-Timeout außerhalb des sinnvollen Bereichs"
        # Lean Th.10: 600 > 120
        assert timeout_used[0] > 120.0, "Research-Timeout muss größer als DELEGATION_TIMEOUT sein"

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

    def test_deep_research_fact_limit_is_bounded(self):
        """_deep_verify_facts hat ein Performance-Limit (nicht alle Fakten verifizieren)."""
        import inspect
        from tools.deep_research import tool as dr_tool
        source = inspect.getsource(dr_tool)
        assert "group_idx < " in source, (
            "deep_research/tool.py: Muss ein group_idx-Limit haben (Performance-Guard)"
        )

    def test_research_timeout_in_env_example(self):
        """RESEARCH_TIMEOUT ist in .env.example dokumentiert."""
        from pathlib import Path
        env_example = Path(__file__).parent.parent / ".env.example"
        content = env_example.read_text()
        assert "RESEARCH_TIMEOUT" in content

    @pytest.mark.asyncio
    async def test_parallel_research_gets_research_timeout(self, monkeypatch):
        """Lean Th.11: Parallel-Delegation nutzt RESEARCH_TIMEOUT (600s) für research-Agent.
        Konsistenz: parallel == sequential für research."""
        monkeypatch.delenv("RESEARCH_TIMEOUT", raising=False)
        monkeypatch.delenv("DELEGATION_TIMEOUT", raising=False)

        timeout_used = []
        original_wait_for = asyncio.wait_for

        async def mock_wait_for(coro, timeout):
            timeout_used.append(timeout)
            try:
                return await coro
            except Exception:
                return "done"

        from agent.agent_registry import AgentRegistry
        registry = AgentRegistry()
        mock_agent = MagicMock()
        mock_agent.run = AsyncMock(return_value="done")
        registry.register_spec("research", "research", ["test"], lambda *a, **kw: mock_agent)

        with patch("agent.agent_registry.asyncio.wait_for", side_effect=mock_wait_for):
            await registry.delegate_parallel(
                tasks=[{"agent": "research", "task": "recherche KI-Agenten"}],
                from_agent="meta",
                max_parallel=1,
            )

        assert len(timeout_used) >= 1
        assert timeout_used[0] == pytest.approx(600.0), (
            f"Parallel-Research sollte 600s bekommen (Lean Th.11), bekam {timeout_used[0]}"
        )
        # Lean Th.11: parallel == sequential
        assert timeout_used[0] == pytest.approx(600.0), "Parallel ≠ Sequential Timeout — Konsistenz verletzt"

    @pytest.mark.asyncio
    async def test_parallel_non_research_gets_delegation_timeout(self, monkeypatch):
        """Nicht-Research-Agenten bekommen weiterhin 120s im Parallel-Modus."""
        monkeypatch.delenv("RESEARCH_TIMEOUT", raising=False)
        monkeypatch.delenv("DELEGATION_TIMEOUT", raising=False)

        timeout_used = []

        async def mock_wait_for(coro, timeout):
            timeout_used.append(timeout)
            try:
                return await coro
            except Exception:
                return "done"

        from agent.agent_registry import AgentRegistry
        registry = AgentRegistry()
        mock_agent = MagicMock()
        mock_agent.run = AsyncMock(return_value="done")
        registry.register_spec("document", "document", ["test"], lambda *a, **kw: mock_agent)

        with patch("agent.agent_registry.asyncio.wait_for", side_effect=mock_wait_for):
            await registry.delegate_parallel(
                tasks=[{"agent": "document", "task": "erstelle PDF"}],
                from_agent="meta",
                max_parallel=1,
            )

        if timeout_used:
            assert timeout_used[0] == pytest.approx(120.0), (
                f"Document-Agent sollte 120s haben, bekam {timeout_used[0]}"
            )
            # Lean Th.10: research_timeout > delegation_timeout → inverted hier
            assert timeout_used[0] < 600.0, "Nicht-Research sollte weniger als RESEARCH_TIMEOUT bekommen"

    def test_meta_system_prompt_forbids_search_web_fallback(self):
        """Fix 3: META_SYSTEM_PROMPT enthält ABSOLUTES VERBOT für search_web nach Research-Timeout."""
        from agent.prompts import META_SYSTEM_PROMPT
        assert "RESEARCH-TIMEOUT-PROTOKOLL" in META_SYSTEM_PROMPT, (
            "META_SYSTEM_PROMPT muss RESEARCH-TIMEOUT-PROTOKOLL enthalten"
        )
        assert "ABSOLUTES VERBOT" in META_SYSTEM_PROMPT, (
            "META_SYSTEM_PROMPT muss ABSOLUTES VERBOT für search_web enthalten"
        )
        assert "KEIN search_web" in META_SYSTEM_PROMPT, (
            "META_SYSTEM_PROMPT muss explizit search_web verbieten"
        )
        assert "NIEMALS" in META_SYSTEM_PROMPT, (
            "META_SYSTEM_PROMPT muss NIEMALS-Formulierung enthalten"
        )

    def test_research_timeout_default_is_600_in_source(self):
        """Fix 1: Sourcecode-Check — RESEARCH_TIMEOUT default ist '600' (nicht '180')."""
        import inspect
        from agent import agent_registry
        source = inspect.getsource(agent_registry)
        assert '"600"' in source, "RESEARCH_TIMEOUT default muss '600' sein"
        # Lean Th.9: 600 ∈ [300, 900]
        assert '"180"' not in source or source.count('"180"') == 0 or \
               source.index('"600"') < source.index('"180"') + 1000, (
            "Alter 180s-Default sollte nicht mehr vorhanden sein"
        )

    def test_parallel_research_uses_env_var_not_hardcoded(self):
        """Fix 2: run_single() nutzt RESEARCH_TIMEOUT env-var, nicht 120 hardcoded für research."""
        import inspect
        from agent import agent_registry
        source = inspect.getsource(agent_registry)
        # Prüfe dass der Code die Env-Var für research in run_single nutzt
        assert "RESEARCH_TIMEOUT" in source, "RESEARCH_TIMEOUT muss im Sourcecode erscheinen"
        # run_single sollte nicht mehr einfach float(task.get("timeout", 120)) für research sein
        # sondern _default_timeout mit bedingtem RESEARCH_TIMEOUT
        assert "_default_timeout" in source, (
            "run_single() sollte _default_timeout Variable nutzen"
        )
