# tests/test_dr_diagnostics.py
"""
Tests für DrDiagnostics (M1).

Prüft: Felder, Defaults, Methoden, Summary-Dict, print_report (raucht nicht).
Kein Netzwerk, keine LLM-Calls.
"""

import time
import pytest
from tools.deep_research.diagnostics import DrDiagnostics, get_current, reset, set_current


class TestDrDiagnosticsDefaults:
    def test_default_query_empty(self):
        d = DrDiagnostics()
        assert d.query == ""

    def test_default_language(self):
        d = DrDiagnostics()
        assert d.language_detected == "unknown"

    def test_default_n_facts_zero(self):
        d = DrDiagnostics()
        assert d.n_facts_extracted == 0
        assert d.n_verified == 0
        assert d.n_tentative == 0
        assert d.n_unverified == 0

    def test_default_quality_gate_false(self):
        d = DrDiagnostics()
        assert d.quality_gate_passed is False

    def test_default_fallback_false(self):
        d = DrDiagnostics()
        assert d.fallback_triggered is False

    def test_default_phase_times_empty(self):
        d = DrDiagnostics()
        assert d.phase_times == {}


class TestDrDiagnosticsMarkPhase:
    def test_mark_phase_stores_key(self):
        d = DrDiagnostics()
        d.mark_phase("search")
        assert "search" in d.phase_times

    def test_mark_phase_non_negative(self):
        d = DrDiagnostics()
        d.mark_phase("verify")
        assert d.phase_times["verify"] >= 0.0

    def test_mark_multiple_phases(self):
        d = DrDiagnostics()
        for phase in ["p1", "p2", "p3"]:
            d.mark_phase(phase)
        assert set(d.phase_times.keys()) == {"p1", "p2", "p3"}


class TestDrDiagnosticsFinish:
    def test_finish_sets_duration(self):
        d = DrDiagnostics()
        time.sleep(0.01)
        d.finish()
        assert d.duration_seconds > 0.0

    def test_finish_quality_gate_true_when_three_verified(self):
        d = DrDiagnostics()
        d.n_verified = 3
        d.finish()
        assert d.quality_gate_passed is True

    def test_finish_quality_gate_false_when_two_verified(self):
        d = DrDiagnostics()
        d.n_verified = 2
        d.finish()
        assert d.quality_gate_passed is False

    def test_finish_quality_gate_true_when_many_verified(self):
        d = DrDiagnostics()
        d.n_verified = 10
        d.finish()
        assert d.quality_gate_passed is True


class TestDrDiagnosticsSummary:
    def test_summary_is_dict(self):
        d = DrDiagnostics(query="test")
        s = d.summary()
        assert isinstance(s, dict)

    def test_summary_has_required_keys(self):
        d = DrDiagnostics(query="test")
        s = d.summary()
        required = {
            "query", "language_detected", "location_used",
            "n_queries_issued", "n_sources_found", "n_sources_relevant",
            "n_facts_extracted", "n_facts_grouped", "embedding_threshold",
            "domain_detected", "n_verified", "n_tentative", "n_unverified",
            "verification_mode_req", "verification_mode_eff",
            "n_corroborator_calls", "arxiv_fetched", "arxiv_accepted",
            "arxiv_threshold", "duration_seconds", "quality_gate_passed",
            "fallback_triggered", "phase_times",
        }
        assert required.issubset(s.keys())

    def test_summary_query_matches(self):
        d = DrDiagnostics(query="self-monitoring AI")
        assert d.summary()["query"] == "self-monitoring AI"


class TestDrDiagnosticsSingleton:
    def test_reset_returns_fresh_instance(self):
        d1 = reset()
        d1.n_verified = 5
        d2 = reset()
        assert d2.n_verified == 0

    def test_get_current_returns_set_instance(self):
        d = DrDiagnostics(query="singleton-test")
        set_current(d)
        assert get_current() is d

    def test_reset_sets_current(self):
        d = reset()
        assert get_current() is d


class TestDrDiagnosticsPrintReport:
    def test_print_report_does_not_raise(self, capsys):
        d = DrDiagnostics(query="print test")
        d.n_verified = 5
        d.n_tentative = 2
        d.n_facts_extracted = 30
        d.arxiv_accepted = 4
        d.finish()
        d.print_report()  # darf keine Exception werfen
        captured = capsys.readouterr()
        assert "Diagnose" in captured.out

    def test_print_report_shows_fallback(self, capsys):
        d = DrDiagnostics(query="fallback test")
        d.fallback_triggered = True
        d.finish()
        d.print_report()
        captured = capsys.readouterr()
        assert "light" in captured.out.lower() or "Fallback" in captured.out
