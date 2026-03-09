"""
Tests für Meilenstein 5 — Parallele Delegation (Integrationstests).

Phasen:
  T1 — MemoryAccessGuard ist ContextVar-basiert (Isolation zwischen Tasks)
  T2 — ResultAggregator + delegate_parallel() End-to-End
  T3 — Semaphore-Einhaltung (max_parallel)
  T4 — Timeout liefert partial-Status (kein Absturz)
  T5 — META_SYSTEM_PROMPT enthält parallele Delegation
  T6 — ResultAggregator.inject_into_session() End-to-End
  T7 — Mehrere parallele Tasks — alle Agenten erreichbar
"""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


# ── Hilfsfunktion: Mock-Agent ─────────────────────────────────────────────────

def _mock_agent(return_value: str = "ok"):
    m = MagicMock()
    m.run = AsyncMock(return_value=return_value)
    return m


def _make_registry(agents: dict):
    """Erstellt Registry mit benannten Mock-Agenten."""
    from agent.agent_registry import AgentRegistry, AgentSpec
    registry = AgentRegistry()
    for name, ret in agents.items():
        rv = ret
        registry._specs[name] = AgentSpec(
            name=name, agent_type=name,
            capabilities=[name],
            factory=lambda tools_desc, _rv=rv, **kw: _mock_agent(_rv),
        )
    return registry


# ── T1: ContextVar-Isolation ──────────────────────────────────────────────────

class TestContextVarIsolation:

    def test_guard_set_und_reset_in_sync(self):
        """set_read_only + is_read_only Grundverhalten."""
        from memory.memory_guard import MemoryAccessGuard
        MemoryAccessGuard.set_read_only(True)
        assert MemoryAccessGuard.is_read_only() is True
        MemoryAccessGuard.set_read_only(False)
        assert MemoryAccessGuard.is_read_only() is False

    def test_guard_blockiert_schreibzugriff(self):
        """check_write_permission wirft PermissionError wenn read-only."""
        from memory.memory_guard import MemoryAccessGuard
        MemoryAccessGuard.set_read_only(True)
        with pytest.raises(PermissionError):
            MemoryAccessGuard.check_write_permission()
        MemoryAccessGuard.set_read_only(False)

    @pytest.mark.asyncio
    async def test_context_var_isolation_zwischen_tasks(self):
        """
        Zwei asyncio-Tasks können ihren eigenen read-only Status unabhängig setzen.
        Task A setzt True, Task B setzt False → beide stören sich nicht.
        """
        from memory.memory_guard import MemoryAccessGuard

        results = {}

        async def task_a():
            MemoryAccessGuard.set_read_only(True)
            await asyncio.sleep(0.02)  # Pause — Task B läuft in dieser Zeit
            results["a"] = MemoryAccessGuard.is_read_only()
            MemoryAccessGuard.set_read_only(False)

        async def task_b():
            await asyncio.sleep(0.01)  # Etwas später starten
            MemoryAccessGuard.set_read_only(False)
            results["b"] = MemoryAccessGuard.is_read_only()

        await asyncio.gather(task_a(), task_b())

        # Task A hat True gesetzt und liest True — Task B hat ihn nicht überschrieben
        assert results["a"] is True, (
            "Task A sollte read_only=True sehen, auch wenn Task B False gesetzt hat"
        )
        assert results["b"] is False

    @pytest.mark.asyncio
    async def test_guard_nach_delegate_parallel_auf_false(self):
        """Nach delegate_parallel muss is_read_only() im Haupt-Task False sein."""
        from memory.memory_guard import MemoryAccessGuard
        registry = _make_registry({"executor": "ok"})

        assert MemoryAccessGuard.is_read_only() is False
        await registry.delegate_parallel(tasks=[
            {"agent": "executor", "task": "Test"},
        ])
        assert MemoryAccessGuard.is_read_only() is False


# ── T2: ResultAggregator End-to-End ──────────────────────────────────────────

class TestResultAggregatorEndToEnd:

    @pytest.mark.asyncio
    async def test_format_results_auf_echtem_parallel_output(self):
        """delegate_parallel() → ResultAggregator.format_results() kein Absturz."""
        from agent.result_aggregator import ResultAggregator
        registry = _make_registry({"research": "Recherche-Ergebnis", "developer": "Code"})

        result = await registry.delegate_parallel(tasks=[
            {"task_id": "t1", "agent": "research",  "task": "Thema A"},
            {"task_id": "t2", "agent": "developer", "task": "Code B"},
        ])

        formatted = ResultAggregator.format_results(result)
        assert isinstance(formatted, str)
        assert "t1" in formatted
        assert "t2" in formatted
        assert "research" in formatted
        assert "developer" in formatted

    @pytest.mark.asyncio
    async def test_inject_into_session_end_to_end(self):
        """inject_into_session() ruft add_message() einmalig auf."""
        from agent.result_aggregator import ResultAggregator
        registry = _make_registry({"executor": "Ergebnis"})

        result = await registry.delegate_parallel(tasks=[
            {"task_id": "t1", "agent": "executor", "task": "Test"},
        ])

        mock_session = MagicMock()
        ResultAggregator.inject_into_session(mock_session, result)
        mock_session.add_message.assert_called_once()

        # Kein metadata-Parameter
        kwargs = mock_session.add_message.call_args.kwargs
        assert "metadata" not in kwargs

    @pytest.mark.asyncio
    async def test_has_errors_nach_fehler(self):
        from agent.result_aggregator import ResultAggregator
        from agent.agent_registry import AgentRegistry
        registry = AgentRegistry()  # leere Registry

        result = await registry.delegate_parallel(tasks=[
            {"agent": "nicht_vorhanden", "task": "Test"},
        ])
        assert ResultAggregator.has_errors(result) is True

    @pytest.mark.asyncio
    async def test_success_count_nach_erfolg(self):
        from agent.result_aggregator import ResultAggregator
        registry = _make_registry({"executor": "ok"})

        result = await registry.delegate_parallel(tasks=[
            {"agent": "executor", "task": "A"},
            {"agent": "executor", "task": "B"},
        ])
        assert ResultAggregator.success_count(result) == 2

    @pytest.mark.asyncio
    async def test_has_partial_nach_partial_marker(self):
        from agent.result_aggregator import ResultAggregator
        registry = _make_registry({"executor": "Limit erreicht."})

        result = await registry.delegate_parallel(tasks=[
            {"agent": "executor", "task": "Test"},
        ])
        assert ResultAggregator.has_partial(result) is True


# ── T3: Semaphore ─────────────────────────────────────────────────────────────

class TestSemaphoreIntegration:

    @pytest.mark.asyncio
    async def test_max_parallel_eingehalten(self):
        """6 Tasks mit max_parallel=2 — nie mehr als 2 gleichzeitig."""
        concurrent_max = 0
        currently_running = 0

        def factory(tools_desc, **kw):
            nonlocal concurrent_max, currently_running

            async def slow(task):
                nonlocal concurrent_max, currently_running
                currently_running += 1
                concurrent_max = max(concurrent_max, currently_running)
                await asyncio.sleep(0.03)
                currently_running -= 1
                return "ok"

            m = MagicMock()
            m.run = slow
            return m

        from agent.agent_registry import AgentRegistry, AgentSpec
        registry = AgentRegistry()
        registry._specs["executor"] = AgentSpec(
            name="executor", agent_type="executor",
            capabilities=["execution"], factory=factory,
        )

        await registry.delegate_parallel(
            tasks=[{"agent": "executor", "task": f"T{i}"} for i in range(6)],
            max_parallel=2,
        )

        assert concurrent_max <= 2, f"Max 2 erwartet, aber {concurrent_max} liefen gleichzeitig"

    @pytest.mark.asyncio
    async def test_budget_cap_reduziert_effektive_parallelitaet(self, monkeypatch):
        """Budget-Softlimit kann max_parallel runtime-seitig weiter begrenzen."""
        concurrent_max = 0
        currently_running = 0

        def factory(tools_desc, **kw):
            nonlocal concurrent_max, currently_running

            async def slow(task):
                nonlocal concurrent_max, currently_running
                currently_running += 1
                concurrent_max = max(concurrent_max, currently_running)
                await asyncio.sleep(0.03)
                currently_running -= 1
                return "ok"

            m = MagicMock()
            m.run = slow
            return m

        from agent.agent_registry import AgentRegistry, AgentSpec
        from orchestration.llm_budget_guard import LLMBudgetDecision

        monkeypatch.setattr(
            "agent.agent_registry.cap_parallelism_for_budget",
            lambda **kwargs: (
                1,
                LLMBudgetDecision(
                    blocked=False,
                    warning=True,
                    soft_limited=True,
                    max_tokens_cap=256,
                    state="soft_limit",
                    scopes=[],
                    message="soft active",
                ),
            ),
        )

        registry = AgentRegistry()
        registry._specs["executor"] = AgentSpec(
            name="executor", agent_type="executor",
            capabilities=["execution"], factory=factory,
        )

        result = await registry.delegate_parallel(
            tasks=[{"agent": "executor", "task": f"T{i}"} for i in range(4)],
            max_parallel=4,
        )

        assert concurrent_max <= 1
        assert result["effective_max_parallel"] == 1
        assert result["budget_state"] == "soft_limit"


# ── T4: Timeout → partial ─────────────────────────────────────────────────────

class TestTimeoutIntegration:

    @pytest.mark.asyncio
    async def test_timeout_ergibt_partial(self):
        """Langsamer Agent → status: partial, kein Absturz."""
        from agent.agent_registry import AgentRegistry, AgentSpec

        def slow_factory(tools_desc, **kw):
            m = MagicMock()
            async def slow(task):
                await asyncio.sleep(999)
            m.run = slow
            return m

        registry = AgentRegistry()
        registry._specs["executor"] = AgentSpec(
            name="executor", agent_type="executor",
            capabilities=["execution"], factory=slow_factory,
        )

        result = await registry.delegate_parallel(
            tasks=[{"agent": "executor", "task": "Langsam", "timeout": 0.1}],
        )

        assert result["results"][0]["status"] == "partial"
        assert result["partial"] == 1

    @pytest.mark.asyncio
    async def test_gemischte_tasks_timeout_und_success(self):
        """Ein Task schnell (success), einer langsam (partial) — beide im Ergebnis."""
        from agent.agent_registry import AgentRegistry, AgentSpec

        def fast_factory(tools_desc, **kw):
            m = MagicMock()
            m.run = AsyncMock(return_value="schnell fertig")
            return m

        def slow_factory(tools_desc, **kw):
            m = MagicMock()
            async def slow(task):
                await asyncio.sleep(999)
            m.run = slow
            return m

        registry = AgentRegistry()
        registry._specs["fast"] = AgentSpec("fast", "fast", ["fast"], factory=fast_factory)
        registry._specs["slow"] = AgentSpec("slow", "slow", ["slow"], factory=slow_factory)

        result = await registry.delegate_parallel(tasks=[
            {"task_id": "t1", "agent": "fast", "task": "Schnell"},
            {"task_id": "t2", "agent": "slow", "task": "Langsam", "timeout": 0.1},
        ])

        assert result["total_tasks"] == 2
        assert result["success"] == 1
        assert result["partial"] == 1

        statuses = {r["task_id"]: r["status"] for r in result["results"]}
        assert statuses["t1"] == "success"
        assert statuses["t2"] == "partial"


# ── T5: META_SYSTEM_PROMPT enthält parallele Delegation ──────────────────────

class TestMetaPromptErweiterung:

    def test_prompt_enthaelt_delegate_multiple_agents(self):
        from agent.prompts import META_SYSTEM_PROMPT
        # Formatierung mit Platzhaltern
        prompt = META_SYSTEM_PROMPT.format(
            current_date="2026-02-24",
            tools_description="test",
        )
        assert "delegate_multiple_agents" in prompt, (
            "META_SYSTEM_PROMPT muss delegate_multiple_agents erwähnen"
        )

    def test_prompt_enthaelt_parallel_beispiel(self):
        from agent.prompts import META_SYSTEM_PROMPT
        prompt = META_SYSTEM_PROMPT.format(
            current_date="2026-02-24",
            tools_description="test",
        )
        assert "PARALLEL" in prompt or "parallel" in prompt.lower()

    def test_prompt_enthaelt_unabhaengig_hinweis(self):
        from agent.prompts import META_SYSTEM_PROMPT
        prompt = META_SYSTEM_PROMPT.format(
            current_date="2026-02-24",
            tools_description="test",
        )
        assert "UNABHAENGIG" in prompt or "unabhängig" in prompt.lower() or "UNABHÄNGIG" in prompt

    def test_prompt_enthaelt_results_und_artifacts_hinweis(self):
        from agent.prompts import META_SYSTEM_PROMPT
        prompt = META_SYSTEM_PROMPT.format(
            current_date="2026-02-24",
            tools_description="test",
        )
        assert "results[]" in prompt
        assert "artifacts" in prompt

    def test_prompt_markiert_metadata_als_ausnahme_fallback(self):
        from agent.prompts import META_SYSTEM_PROMPT
        prompt = META_SYSTEM_PROMPT.format(
            current_date="2026-02-24",
            tools_description="test",
        )
        assert "Ausnahme-Fallback" in prompt or "nicht der Normalfall" in prompt


# ── T6: Regression — delegate() + delegate_parallel() koexistieren ────────────

class TestRegression:

    def test_beide_methoden_existieren(self):
        from agent.agent_registry import AgentRegistry
        assert hasattr(AgentRegistry, "delegate")
        assert hasattr(AgentRegistry, "delegate_parallel")

    @pytest.mark.asyncio
    async def test_delegate_gibt_dict_zurueck(self):
        from agent.agent_registry import AgentRegistry
        registry = AgentRegistry()
        result = await registry.delegate(
            from_agent="meta", to_agent="nicht_vorhanden", task="Test",
        )
        assert isinstance(result, dict)
        assert result["status"] == "error"

    @pytest.mark.asyncio
    async def test_delegate_parallel_gibt_dict_zurueck(self):
        from agent.agent_registry import AgentRegistry
        registry = AgentRegistry()
        result = await registry.delegate_parallel(tasks=[
            {"agent": "nicht_vorhanden", "task": "Test"},
        ])
        assert isinstance(result, dict)
        assert "trace_id" in result
        assert result["errors"] == 1
