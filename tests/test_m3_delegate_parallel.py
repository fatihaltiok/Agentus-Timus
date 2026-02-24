"""
Tests für Meilenstein 3 — delegate_parallel() in AgentRegistry.

Phasen:
  T1 — Methode existiert und gibt korrekte Struktur zurück
  T2 — Fan-Out: alle Tasks werden gestartet
  T3 — Fan-In: Ergebnisse korrekt aggregiert (success/partial/error)
  T4 — Frische Instanz pro Task (kein Singleton-Conflict)
  T5 — MemoryAccessGuard: read-only wird gesetzt und zurückgesetzt
  T6 — Semaphore begrenzt parallele Ausführung
  T7 — Timeout liefert partial-Status (kein Absturz)
  T8 — Unbekannter Agent → error-Status (kein Absturz)
  T9 — Regression: bestehende delegate()-Methode unverändert
"""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


# ── Hilfsfunktion: Registry mit Mock-Agenten befüllen ────────────────────────

def _make_registry_with_mock(agent_name: str, return_value: str = "Ergebnis"):
    """Erstellt eine Registry mit einem Mock-Agenten."""
    from agent.agent_registry import AgentRegistry

    registry = AgentRegistry()

    mock_agent = MagicMock()
    mock_agent.run = AsyncMock(return_value=return_value)

    # Factory gibt immer eine frische Mock-Instanz zurück
    def factory(tools_desc, **kwargs):
        m = MagicMock()
        m.run = AsyncMock(return_value=return_value)
        return m

    from agent.agent_registry import AgentSpec
    registry._specs[agent_name] = AgentSpec(
        name=agent_name,
        agent_type=agent_name,
        capabilities=[agent_name],
        factory=factory,
    )
    return registry


# ── T1: Methode existiert + Rückgabe-Struktur ────────────────────────────────

class TestMethodeExistiert:

    @pytest.mark.asyncio
    async def test_methode_vorhanden(self):
        """delegate_parallel muss in AgentRegistry existieren."""
        from agent.agent_registry import AgentRegistry
        assert hasattr(AgentRegistry, "delegate_parallel")

    @pytest.mark.asyncio
    async def test_rueckgabe_hat_pflichtfelder(self):
        """Rückgabe muss alle Pflichtfelder enthalten."""
        registry = _make_registry_with_mock("executor", "ok")

        result = await registry.delegate_parallel(
            tasks=[{"task_id": "t1", "agent": "executor", "task": "Test"}]
        )

        for field in ["trace_id", "total_tasks", "success", "partial", "errors", "results", "summary"]:
            assert field in result, f"Pflichtfeld '{field}' fehlt"

    @pytest.mark.asyncio
    async def test_trace_id_ist_string(self):
        registry = _make_registry_with_mock("executor", "ok")
        result = await registry.delegate_parallel(
            tasks=[{"agent": "executor", "task": "Test"}]
        )
        assert isinstance(result["trace_id"], str)
        assert len(result["trace_id"]) == 12


# ── T2: Fan-Out — alle Tasks werden ausgeführt ───────────────────────────────

class TestFanOut:

    @pytest.mark.asyncio
    async def test_alle_tasks_werden_ausgefuehrt(self):
        """Alle 3 Tasks müssen ausgeführt werden."""
        call_count = 0

        def factory(tools_desc, **kwargs):
            nonlocal call_count
            m = MagicMock()

            async def run(task):
                nonlocal call_count
                call_count += 1
                return f"Ergebnis-{call_count}"

            m.run = run
            return m

        from agent.agent_registry import AgentRegistry, AgentSpec
        registry = AgentRegistry()
        for name in ["research", "developer", "creative"]:
            registry._specs[name] = AgentSpec(
                name=name, agent_type=name,
                capabilities=[name], factory=factory,
            )

        result = await registry.delegate_parallel(tasks=[
            {"task_id": "t1", "agent": "research",  "task": "Recherche"},
            {"task_id": "t2", "agent": "developer",  "task": "Code"},
            {"task_id": "t3", "agent": "creative",   "task": "Bild"},
        ])

        assert call_count == 3
        assert result["total_tasks"] == 3

    @pytest.mark.asyncio
    async def test_ergebnisse_enthalten_alle_task_ids(self):
        """Jedes Ergebnis muss task_id enthalten."""
        registry = _make_registry_with_mock("executor", "ok")

        result = await registry.delegate_parallel(tasks=[
            {"task_id": "alpha", "agent": "executor", "task": "A"},
            {"task_id": "beta",  "agent": "executor", "task": "B"},
        ])

        task_ids = [r.get("task_id") for r in result["results"]]
        assert "alpha" in task_ids
        assert "beta"  in task_ids


# ── T3: Fan-In — Zähler korrekt ──────────────────────────────────────────────

class TestFanIn:

    @pytest.mark.asyncio
    async def test_success_count_korrekt(self):
        registry = _make_registry_with_mock("executor", "Ergebnis")
        result = await registry.delegate_parallel(tasks=[
            {"agent": "executor", "task": "A"},
            {"agent": "executor", "task": "B"},
        ])
        assert result["success"] == 2
        assert result["errors"]  == 0
        assert result["partial"] == 0

    @pytest.mark.asyncio
    async def test_error_count_bei_unbekanntem_agent(self):
        from agent.agent_registry import AgentRegistry
        registry = AgentRegistry()  # leere Registry

        result = await registry.delegate_parallel(tasks=[
            {"agent": "nicht_vorhanden", "task": "Test"},
        ])

        assert result["errors"] == 1
        assert result["success"] == 0
        assert result["results"][0]["status"] == "error"

    @pytest.mark.asyncio
    async def test_partial_bei_partial_marker(self):
        """'Limit erreicht.' → status: partial."""
        registry = _make_registry_with_mock("executor", "Limit erreicht.")

        result = await registry.delegate_parallel(tasks=[
            {"agent": "executor", "task": "Test"},
        ])

        assert result["results"][0]["status"] == "partial"
        assert result["partial"] == 1

    @pytest.mark.asyncio
    async def test_summary_format(self):
        registry = _make_registry_with_mock("executor", "ok")
        result = await registry.delegate_parallel(tasks=[
            {"agent": "executor", "task": "Test"},
        ])
        assert "erfolgreich" in result["summary"]
        assert "Fehler"      in result["summary"]


# ── T4: Frische Instanz pro Task ─────────────────────────────────────────────

class TestFrischeInstanz:

    @pytest.mark.asyncio
    async def test_jeder_task_bekommt_neue_instanz(self):
        """Factory muss für jeden Task erneut aufgerufen werden."""
        factory_calls = []

        def counting_factory(tools_desc, **kwargs):
            factory_calls.append(1)
            m = MagicMock()
            m.run = AsyncMock(return_value="ok")
            return m

        from agent.agent_registry import AgentRegistry, AgentSpec
        registry = AgentRegistry()
        registry._specs["executor"] = AgentSpec(
            name="executor", agent_type="executor",
            capabilities=["execution"], factory=counting_factory,
        )

        await registry.delegate_parallel(tasks=[
            {"task_id": "t1", "agent": "executor", "task": "A"},
            {"task_id": "t2", "agent": "executor", "task": "B"},
            {"task_id": "t3", "agent": "executor", "task": "C"},
        ])

        assert len(factory_calls) == 3, (
            f"Erwartet 3 Factory-Aufrufe, bekommen: {len(factory_calls)}"
        )


# ── T5: MemoryAccessGuard ─────────────────────────────────────────────────────

class TestMemoryAccessGuard:

    @pytest.mark.asyncio
    async def test_guard_wird_pro_task_gesetzt_und_zurueckgesetzt(self):
        """
        Nach Abschluss aller Tasks muss is_read_only() False sein
        (ContextVar des Test-Tasks ist nie auf True gesetzt worden).
        """
        from memory.memory_guard import MemoryAccessGuard

        registry = _make_registry_with_mock("executor", "ok")

        # Vor dem Aufruf: nicht read-only
        assert MemoryAccessGuard.is_read_only() is False

        await registry.delegate_parallel(tasks=[
            {"agent": "executor", "task": "Test"},
        ])

        # Nach dem Aufruf: immer noch nicht read-only (ContextVar des Haupt-Tasks)
        assert MemoryAccessGuard.is_read_only() is False

    @pytest.mark.asyncio
    async def test_guard_bei_exception_zurueckgesetzt(self):
        """Auch bei Exception im Agent muss read-only zurückgesetzt werden."""
        from memory.memory_guard import MemoryAccessGuard
        from agent.agent_registry import AgentRegistry, AgentSpec

        def failing_factory(tools_desc, **kwargs):
            m = MagicMock()
            m.run = AsyncMock(side_effect=RuntimeError("Simulierter Fehler"))
            return m

        registry = AgentRegistry()
        registry._specs["executor"] = AgentSpec(
            name="executor", agent_type="executor",
            capabilities=["execution"], factory=failing_factory,
        )

        result = await registry.delegate_parallel(tasks=[
            {"agent": "executor", "task": "Test"},
        ])

        assert result["errors"] == 1
        # Haupt-Task-Context bleibt unverändert
        assert MemoryAccessGuard.is_read_only() is False


# ── T6: Semaphore begrenzt parallele Ausführung ───────────────────────────────

class TestSemaphore:

    @pytest.mark.asyncio
    async def test_max_parallel_wird_eingehalten(self):
        """Mit max_parallel=2 dürfen nie mehr als 2 Tasks gleichzeitig laufen."""
        concurrent_high_watermark = 0
        currently_running = 0

        def factory(tools_desc, **kwargs):
            nonlocal concurrent_high_watermark, currently_running

            async def slow_run(task):
                nonlocal concurrent_high_watermark, currently_running
                currently_running += 1
                concurrent_high_watermark = max(concurrent_high_watermark, currently_running)
                await asyncio.sleep(0.05)
                currently_running -= 1
                return "ok"

            m = MagicMock()
            m.run = slow_run
            return m

        from agent.agent_registry import AgentRegistry, AgentSpec
        registry = AgentRegistry()
        registry._specs["executor"] = AgentSpec(
            name="executor", agent_type="executor",
            capabilities=["execution"], factory=factory,
        )

        await registry.delegate_parallel(
            tasks=[{"agent": "executor", "task": f"Task {i}"} for i in range(6)],
            max_parallel=2,
        )

        assert concurrent_high_watermark <= 2, (
            f"Max 2 parallel erlaubt, aber {concurrent_high_watermark} liefen gleichzeitig"
        )


# ── T7: Timeout → partial ────────────────────────────────────────────────────

class TestTimeout:

    @pytest.mark.asyncio
    async def test_timeout_ergibt_partial(self):
        """Task der zu lange dauert → status: partial, kein Absturz."""
        from agent.agent_registry import AgentRegistry, AgentSpec

        def slow_factory(tools_desc, **kwargs):
            m = MagicMock()
            async def slow_run(task):
                await asyncio.sleep(999)
            m.run = slow_run
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
        assert "Timeout" in result["results"][0]["error"]
        assert result["partial"] == 1


# ── T8: Ungültige Eingaben ────────────────────────────────────────────────────

class TestUngueltigeEingaben:

    @pytest.mark.asyncio
    async def test_fehlende_agent_field(self):
        """Task ohne 'agent' → error, kein Absturz."""
        from agent.agent_registry import AgentRegistry
        registry = AgentRegistry()

        result = await registry.delegate_parallel(tasks=[
            {"task_id": "t1", "task": "Kein Agent angegeben"},
        ])

        assert result["results"][0]["status"] == "error"
        assert result["errors"] == 1

    @pytest.mark.asyncio
    async def test_fehlende_task_field(self):
        """Task ohne 'task' → error, kein Absturz."""
        from agent.agent_registry import AgentRegistry
        registry = AgentRegistry()

        result = await registry.delegate_parallel(tasks=[
            {"task_id": "t1", "agent": "executor"},
        ])

        assert result["results"][0]["status"] == "error"

    @pytest.mark.asyncio
    async def test_unbekannter_agent(self):
        """Nicht registrierter Agent → error mit hilfreicher Meldung."""
        from agent.agent_registry import AgentRegistry
        registry = AgentRegistry()

        result = await registry.delegate_parallel(tasks=[
            {"agent": "nicht_existierender_agent", "task": "Test"},
        ])

        assert result["results"][0]["status"] == "error"
        assert "nicht registriert" in result["results"][0]["error"]


# ── T9: Regression — delegate() unverändert ──────────────────────────────────

class TestRegression:

    @pytest.mark.asyncio
    async def test_delegate_methode_noch_vorhanden(self):
        """Die bestehende delegate()-Methode muss weiterhin existieren."""
        from agent.agent_registry import AgentRegistry
        assert hasattr(AgentRegistry, "delegate")

    @pytest.mark.asyncio
    async def test_delegate_gibt_dict_zurueck(self):
        """delegate() gibt weiterhin strukturiertes Dict zurück."""
        from agent.agent_registry import AgentRegistry
        registry = AgentRegistry()

        # Delegation zu nicht-existierendem Agent → error-Dict (kein Exception)
        result = await registry.delegate(
            from_agent="meta",
            to_agent="nicht_vorhanden",
            task="Test",
        )

        assert isinstance(result, dict)
        assert result["status"] == "error"
