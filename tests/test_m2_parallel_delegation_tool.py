"""
Tests für Meilenstein 2 — delegate_multiple_agents Tool.

Phasen:
  T1 — Tool ist in registry_v2 registriert
  T2 — Eingabe-Validierung (leere tasks, falscher max_parallel)
  T3 — Tool ruft agent_registry.delegate_parallel() auf
  T4 — Rückgabe-Struktur korrekt
  T5 — max_parallel wird begrenzt (1–10)
"""

import pytest
from unittest.mock import AsyncMock, patch


# ── T1: Tool ist registriert ──────────────────────────────────────────────────

class TestToolRegistrierung:

    def test_tool_in_registry(self):
        """delegate_multiple_agents muss in tool_registry_v2 vorhanden sein."""
        import tools.delegation_tool.parallel_delegation_tool  # noqa: F401
        from tools.tool_registry_v2 import registry_v2

        registered = list(registry_v2._tools.keys())
        assert "delegate_multiple_agents" in registered, (
            f"delegate_multiple_agents nicht in Registry. Gefunden: {registered}"
        )

    def test_tool_hat_korrekte_parameter(self):
        """Tool muss 'tasks' und 'max_parallel' als Parameter haben."""
        import tools.delegation_tool.parallel_delegation_tool  # noqa: F401
        from tools.tool_registry_v2 import registry_v2

        tool_def = registry_v2._tools.get("delegate_multiple_agents")
        assert tool_def is not None

        param_namen = [p.name for p in tool_def.parameters]
        assert "tasks" in param_namen
        assert "max_parallel" in param_namen

    def test_tool_category_system(self):
        """Tool muss in SYSTEM-Kategorie sein."""
        import tools.delegation_tool.parallel_delegation_tool  # noqa: F401
        from tools.tool_registry_v2 import registry_v2, ToolCategory

        tool_def = registry_v2._tools.get("delegate_multiple_agents")
        assert tool_def is not None
        assert tool_def.category == ToolCategory.SYSTEM


# ── T2: Eingabe-Validierung ───────────────────────────────────────────────────

class TestEingabeValidierung:

    @pytest.mark.asyncio
    async def test_leere_tasks_gibt_fehler(self):
        """Leeres tasks-Array → sofortiger Fehler, kein Crash."""
        from tools.delegation_tool.parallel_delegation_tool import delegate_multiple_agents

        result = await delegate_multiple_agents(tasks=[])

        assert result["status"] == "error"
        assert "leer" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_max_parallel_wird_auf_10_begrenzt(self):
        """max_parallel > 10 wird auf 10 begrenzt."""
        mock_result = {
            "trace_id": "test",
            "total_tasks": 1,
            "success": 1,
            "partial": 0,
            "errors": 0,
            "results": [{"task_id": "t1", "agent": "executor", "status": "success", "result": "ok"}],
            "summary": "1/1 erfolgreich",
        }

        with patch("agent.agent_registry.agent_registry.delegate_parallel",
                   new=AsyncMock(return_value=mock_result),
                   create=True) as mock_delegate:

            from tools.delegation_tool.parallel_delegation_tool import delegate_multiple_agents
            await delegate_multiple_agents(
                tasks=[{"agent": "executor", "task": "test"}],
                max_parallel=999,
            )

            call_kwargs = mock_delegate.call_args.kwargs
            assert call_kwargs["max_parallel"] <= 10

    @pytest.mark.asyncio
    async def test_max_parallel_wird_auf_1_begrenzt(self):
        """max_parallel < 1 wird auf 1 begrenzt."""
        mock_result = {
            "trace_id": "test", "total_tasks": 1,
            "success": 1, "partial": 0, "errors": 0,
            "results": [], "summary": "1/1 erfolgreich",
        }

        with patch("agent.agent_registry.agent_registry.delegate_parallel",
                   new=AsyncMock(return_value=mock_result),
                   create=True) as mock_delegate:

            from tools.delegation_tool.parallel_delegation_tool import delegate_multiple_agents
            await delegate_multiple_agents(
                tasks=[{"agent": "executor", "task": "test"}],
                max_parallel=0,
            )

            call_kwargs = mock_delegate.call_args.kwargs
            assert call_kwargs["max_parallel"] >= 1


# ── T3: delegate_parallel wird aufgerufen ────────────────────────────────────

class TestDelegatParallelAufruf:

    @pytest.mark.asyncio
    async def test_ruft_delegate_parallel_auf(self):
        """Tool muss agent_registry.delegate_parallel() aufrufen."""
        mock_result = {
            "trace_id": "abc123",
            "total_tasks": 2,
            "success": 2,
            "partial": 0,
            "errors": 0,
            "results": [],
            "summary": "2/2 erfolgreich | 0 partiell | 0 Fehler",
        }

        with patch("agent.agent_registry.agent_registry.delegate_parallel",
                   new=AsyncMock(return_value=mock_result),
                   create=True) as mock_delegate:

            from tools.delegation_tool.parallel_delegation_tool import delegate_multiple_agents

            tasks = [
                {"task_id": "t1", "agent": "research", "task": "Thema A"},
                {"task_id": "t2", "agent": "developer", "task": "Code B"},
            ]
            await delegate_multiple_agents(tasks=tasks)

            mock_delegate.assert_called_once()
            call_kwargs = mock_delegate.call_args.kwargs
            assert call_kwargs["tasks"] == tasks
            assert call_kwargs["from_agent"] == "meta"

    @pytest.mark.asyncio
    async def test_gibt_registry_ergebnis_zurueck(self):
        """Rückgabe von delegate_parallel wird 1:1 weitergegeben."""
        expected = {
            "trace_id": "xyz999",
            "total_tasks": 1,
            "success": 1,
            "partial": 0,
            "errors": 0,
            "results": [{"task_id": "t1", "status": "success"}],
            "summary": "1/1 erfolgreich",
        }

        with patch("agent.agent_registry.agent_registry.delegate_parallel",
                   new=AsyncMock(return_value=expected),
                   create=True):

            from tools.delegation_tool.parallel_delegation_tool import delegate_multiple_agents
            result = await delegate_multiple_agents(
                tasks=[{"agent": "research", "task": "Test"}]
            )

            assert result == expected


# ── T4: Rückgabe-Struktur ─────────────────────────────────────────────────────

class TestRueckgabeStruktur:

    @pytest.mark.asyncio
    async def test_rueckgabe_hat_pflichtfelder(self):
        """Erfolgreiche Rückgabe muss alle Pflichtfelder haben."""
        mock_result = {
            "trace_id": "abc",
            "total_tasks": 1,
            "success": 1,
            "partial": 0,
            "errors": 0,
            "results": [{"task_id": "t1", "agent": "executor",
                         "status": "success", "result": "Ergebnis"}],
            "summary": "1/1 erfolgreich | 0 partiell | 0 Fehler",
        }

        with patch("agent.agent_registry.agent_registry.delegate_parallel",
                   new=AsyncMock(return_value=mock_result),
                   create=True):

            from tools.delegation_tool.parallel_delegation_tool import delegate_multiple_agents
            result = await delegate_multiple_agents(
                tasks=[{"agent": "executor", "task": "Hallo"}]
            )

        for field in ["trace_id", "total_tasks", "success", "errors", "results", "summary"]:
            assert field in result, f"Pflichtfeld '{field}' fehlt in Rückgabe"
