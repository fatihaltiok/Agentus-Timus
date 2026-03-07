"""
Tests für Meilenstein 4 — ResultAggregator.

Phasen:
  T1 — format_results() Grundverhalten
  T2 — format_results() Randwerte + Trunkierung
  T3 — inject_into_session() ruft add_message() korrekt auf
  T4 — Hilfsmethoden (success_count, has_errors, has_partial)
  T5 — Regression: delegate_parallel() liefert kompatibles Format
"""

import pytest
from unittest.mock import MagicMock


# ── Hilfsdaten ────────────────────────────────────────────────────────────────

def _make_aggregated(
    trace_id="abc123",
    success=2, partial=0, errors=0,
    results=None,
):
    total = success + partial + errors
    if results is None:
        results = [
            {"task_id": "t1", "agent": "research",  "status": "success", "result": "Ergebnis A"},
            {"task_id": "t2", "agent": "developer", "status": "success", "result": "Ergebnis B"},
        ]
    return {
        "trace_id":    trace_id,
        "total_tasks": total,
        "success":     success,
        "partial":     partial,
        "errors":      errors,
        "results":     results,
        "summary":     f"{success}/{total} erfolgreich | {partial} partiell | {errors} Fehler",
    }


# ── T1: format_results() Grundverhalten ──────────────────────────────────────

class TestFormatResultsGrundverhalten:

    def test_trace_id_in_ausgabe(self):
        from agent.result_aggregator import ResultAggregator
        agg = _make_aggregated(trace_id="xyz987")
        out = ResultAggregator.format_results(agg)
        assert "xyz987" in out

    def test_summary_in_ausgabe(self):
        from agent.result_aggregator import ResultAggregator
        agg = _make_aggregated(success=2, errors=0)
        out = ResultAggregator.format_results(agg)
        assert "erfolgreich" in out

    def test_agenten_in_ausgabe(self):
        from agent.result_aggregator import ResultAggregator
        agg = _make_aggregated()
        out = ResultAggregator.format_results(agg)
        assert "research" in out
        assert "developer" in out

    def test_task_ids_in_ausgabe(self):
        from agent.result_aggregator import ResultAggregator
        agg = _make_aggregated()
        out = ResultAggregator.format_results(agg)
        assert "t1" in out
        assert "t2" in out

    def test_status_grossbuchstaben(self):
        from agent.result_aggregator import ResultAggregator
        agg = _make_aggregated(results=[
            {"task_id": "t1", "agent": "research", "status": "success", "result": "ok"},
        ])
        out = ResultAggregator.format_results(agg)
        assert "SUCCESS" in out

    def test_ergebnis_inhalt_in_ausgabe(self):
        from agent.result_aggregator import ResultAggregator
        agg = _make_aggregated(results=[
            {"task_id": "t1", "agent": "research", "status": "success", "result": "Mein Recherche-Ergebnis"},
        ])
        out = ResultAggregator.format_results(agg)
        assert "Mein Recherche-Ergebnis" in out

    def test_artifacts_in_ausgabe(self):
        from agent.result_aggregator import ResultAggregator
        agg = _make_aggregated(results=[
            {
                "task_id": "t1",
                "agent": "research",
                "status": "success",
                "result": "ok",
                "artifacts": [{"type": "pdf", "path": "/tmp/report.pdf"}],
            },
        ])
        out = ResultAggregator.format_results(agg)
        assert "Artifacts:" in out
        assert "/tmp/report.pdf" in out

    def test_quality_und_blackboard_in_ausgabe(self):
        from agent.result_aggregator import ResultAggregator
        agg = _make_aggregated(results=[
            {
                "task_id": "t1",
                "agent": "research",
                "status": "success",
                "result": "ok",
                "quality": 80,
                "blackboard_key": "delegation:research:123",
            },
        ])
        out = ResultAggregator.format_results(agg)
        assert "Quality: 80" in out
        assert "delegation:research:123" in out

    def test_metadata_in_ausgabe_wenn_keine_artifacts(self):
        from agent.result_aggregator import ResultAggregator
        agg = _make_aggregated(results=[
            {
                "task_id": "t1",
                "agent": "research",
                "status": "success",
                "result": "ok",
                "metadata": {"session_id": "abc123"},
            },
        ])
        out = ResultAggregator.format_results(agg)
        assert "Metadata:" in out
        assert "session_id: abc123" in out

    def test_error_message_in_ausgabe(self):
        """Bei Fehlern wird 'error'-Feld statt 'result' gezeigt."""
        from agent.result_aggregator import ResultAggregator
        agg = _make_aggregated(
            success=0, errors=1,
            results=[
                {"task_id": "t1", "agent": "executor", "status": "error", "error": "Agent nicht erreichbar"},
            ],
        )
        out = ResultAggregator.format_results(agg)
        assert "Agent nicht erreichbar" in out

    def test_partial_status_korrekt(self):
        from agent.result_aggregator import ResultAggregator
        agg = _make_aggregated(
            success=0, partial=1,
            results=[
                {"task_id": "t1", "agent": "research", "status": "partial", "result": "Teilergebnis"},
            ],
        )
        out = ResultAggregator.format_results(agg)
        assert "PARTIAL" in out

    def test_rueckgabe_ist_string(self):
        from agent.result_aggregator import ResultAggregator
        agg = _make_aggregated()
        out = ResultAggregator.format_results(agg)
        assert isinstance(out, str)

    def test_markdown_header_vorhanden(self):
        from agent.result_aggregator import ResultAggregator
        agg = _make_aggregated()
        out = ResultAggregator.format_results(agg)
        assert "##" in out


# ── T2: Randwerte + Trunkierung ───────────────────────────────────────────────

class TestFormatResultsRandwerte:

    def test_leere_results_kein_absturz(self):
        from agent.result_aggregator import ResultAggregator
        agg = _make_aggregated(success=0, results=[])
        out = ResultAggregator.format_results(agg)
        assert isinstance(out, str)
        assert "abc123" in out

    def test_langes_ergebnis_wird_trunkiert(self):
        from agent.result_aggregator import ResultAggregator
        langer_text = "X" * 2000
        agg = _make_aggregated(results=[
            {"task_id": "t1", "agent": "research", "status": "success", "result": langer_text},
        ])
        out = ResultAggregator.format_results(agg)
        # Max 800 Zeichen pro Ergebnis
        # Das Ergebnis darf nicht mehr als 800 'X' enthalten
        assert out.count("X") <= 800

    def test_fehlende_felder_kein_absturz(self):
        """Ergebnis ohne 'agent', 'task_id', 'result' → kein Absturz."""
        from agent.result_aggregator import ResultAggregator
        agg = _make_aggregated(results=[
            {"status": "success"},  # Alle Felder fehlen
        ])
        out = ResultAggregator.format_results(agg)
        assert isinstance(out, str)

    def test_leeres_aggregated_kein_absturz(self):
        from agent.result_aggregator import ResultAggregator
        out = ResultAggregator.format_results({})
        assert isinstance(out, str)
        assert "N/A" in out  # trace_id Fallback


# ── T3: inject_into_session() ─────────────────────────────────────────────────

class TestInjectIntoSession:

    def test_add_message_wird_aufgerufen(self):
        from agent.result_aggregator import ResultAggregator
        mock_session = MagicMock()
        agg = _make_aggregated()

        ResultAggregator.inject_into_session(mock_session, agg)

        mock_session.add_message.assert_called_once()

    def test_role_ist_system(self):
        from agent.result_aggregator import ResultAggregator
        mock_session = MagicMock()
        agg = _make_aggregated()

        ResultAggregator.inject_into_session(mock_session, agg)

        kwargs = mock_session.add_message.call_args.kwargs
        # Entweder als keyword-arg oder positional
        if kwargs:
            assert kwargs.get("role") == "system"
        else:
            args = mock_session.add_message.call_args.args
            assert args[0] == "system" or "system" in str(args)

    def test_kein_metadata_parameter(self):
        """inject_into_session darf kein metadata-kwarg an add_message übergeben."""
        from agent.result_aggregator import ResultAggregator
        mock_session = MagicMock()
        agg = _make_aggregated()

        ResultAggregator.inject_into_session(mock_session, agg)

        kwargs = mock_session.add_message.call_args.kwargs
        assert "metadata" not in kwargs, (
            "metadata darf nicht übergeben werden — Timus add_message() hat diesen Parameter nicht"
        )

    def test_content_enthaelt_trace_id(self):
        from agent.result_aggregator import ResultAggregator
        mock_session = MagicMock()
        agg = _make_aggregated(trace_id="test999")

        ResultAggregator.inject_into_session(mock_session, agg)

        # Content muss trace_id enthalten
        call_kwargs = mock_session.add_message.call_args.kwargs
        call_args   = mock_session.add_message.call_args.args
        content = call_kwargs.get("content") or (call_args[1] if len(call_args) > 1 else "")
        assert "test999" in content


# ── T4: Hilfsmethoden ────────────────────────────────────────────────────────

class TestHilfsmethoden:

    def test_success_count_korrekt(self):
        from agent.result_aggregator import ResultAggregator
        agg = _make_aggregated(success=3, partial=1, errors=0)
        assert ResultAggregator.success_count(agg) == 3

    def test_success_count_leer(self):
        from agent.result_aggregator import ResultAggregator
        assert ResultAggregator.success_count({}) == 0

    def test_has_errors_true(self):
        from agent.result_aggregator import ResultAggregator
        agg = _make_aggregated(success=0, errors=2)
        assert ResultAggregator.has_errors(agg) is True

    def test_has_errors_false(self):
        from agent.result_aggregator import ResultAggregator
        agg = _make_aggregated(success=2, errors=0)
        assert ResultAggregator.has_errors(agg) is False

    def test_has_partial_true(self):
        from agent.result_aggregator import ResultAggregator
        agg = _make_aggregated(success=1, partial=1, errors=0)
        assert ResultAggregator.has_partial(agg) is True

    def test_has_partial_false(self):
        from agent.result_aggregator import ResultAggregator
        agg = _make_aggregated(success=1, partial=0, errors=0)
        assert ResultAggregator.has_partial(agg) is False


# ── T5: Regression — delegate_parallel() Format kompatibel ───────────────────

class TestRegressionKompatibilitaet:

    @pytest.mark.asyncio
    async def test_delegate_parallel_format_passt_zu_aggregator(self):
        """Ausgabe von delegate_parallel() kann direkt an ResultAggregator übergeben werden."""
        from agent.result_aggregator import ResultAggregator
        from unittest.mock import AsyncMock, MagicMock

        from agent.agent_registry import AgentRegistry, AgentSpec

        registry = AgentRegistry()
        registry._specs["executor"] = AgentSpec(
            name="executor", agent_type="executor",
            capabilities=["execution"],
            factory=lambda tools_desc, **kw: _make_mock_agent("Ergebnis"),
        )

        result = await registry.delegate_parallel(tasks=[
            {"task_id": "t1", "agent": "executor", "task": "Test"},
        ])

        # ResultAggregator darf nicht abstürzen
        formatted = ResultAggregator.format_results(result)
        assert isinstance(formatted, str)
        assert "t1" in formatted

    @pytest.mark.asyncio
    async def test_has_errors_auf_delegate_parallel_output(self):
        from agent.result_aggregator import ResultAggregator
        from agent.agent_registry import AgentRegistry

        registry = AgentRegistry()  # leere Registry

        result = await registry.delegate_parallel(tasks=[
            {"agent": "nicht_vorhanden", "task": "Test"},
        ])

        assert ResultAggregator.has_errors(result) is True
        assert ResultAggregator.success_count(result) == 0


def _make_mock_agent(return_value: str):
    from unittest.mock import MagicMock, AsyncMock
    m = MagicMock()
    m.run = AsyncMock(return_value=return_value)
    return m
