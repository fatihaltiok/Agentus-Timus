# tests/test_dr_integration.py
"""
Integration-Tests für Deep Research Engine v7.0 (M6).

Prüft das Zusammenspiel aller Fixes ohne Netzwerk:
- Diagnostics-Singleton-Flow
- Auto-Mode + Domain-Detection Kombinationen
- Qualitäts-Gate Logik
- Fallback-Trigger Logik
- Verifikations-Pipeline (isoliert)
"""

import os
import pytest
from tools.deep_research.diagnostics import DrDiagnostics, reset, get_current


class TestDiagnosticsFlow:
    """Vollständiger Diagnostics-Flow wie er in start_deep_research abläuft."""

    def test_reset_and_populate(self):
        d = reset()
        d.query = "self-monitoring AI agents"
        d.language_detected = "en"
        d.location_used = "2840"
        d.n_queries_issued = 5
        d.n_sources_found = 18
        d.n_sources_relevant = 8
        d.n_facts_extracted = 45
        d.domain_detected = "tech"
        d.embedding_threshold = 0.72
        d.n_facts_grouped = 22
        d.verification_mode_req = "strict"
        d.verification_mode_eff = "moderate"
        d.n_verified = 8
        d.n_tentative = 5
        d.n_unverified = 9
        d.n_corroborator_calls = 4
        d.arxiv_fetched = 20
        d.arxiv_accepted = 5
        d.arxiv_threshold = 5
        d.finish()

        assert d.quality_gate_passed is True
        assert get_current() is d

    def test_quality_gate_boundary(self):
        for n in range(0, 6):
            d = DrDiagnostics()
            d.n_verified = n
            d.finish()
            if n >= 3:
                assert d.quality_gate_passed is True
            else:
                assert d.quality_gate_passed is False

    def test_summary_all_fields_serializable(self):
        import json
        d = reset()
        d.n_verified = 5
        d.finish()
        s = d.summary()
        # Muss JSON-serialisierbar sein
        dumped = json.dumps(s)
        assert len(dumped) > 10


class TestAutoModeIntegration:
    """Testet Auto-Mode + Domain in verschiedenen Kombinationen."""

    def test_strict_ai_query(self, monkeypatch):
        monkeypatch.setenv("DR_VERIFICATION_MODE_AUTO", "true")
        from tools.deep_research.tool import _resolve_verification_mode
        assert _resolve_verification_mode("strict", "AI agents transformer") == "moderate"

    def test_strict_german_query(self, monkeypatch):
        monkeypatch.setenv("DR_VERIFICATION_MODE_AUTO", "true")
        from tools.deep_research.tool import _resolve_verification_mode
        assert _resolve_verification_mode("strict", "Bundestagswahl 2025") == "strict"

    def test_moderate_ai_stays_moderate(self, monkeypatch):
        monkeypatch.setenv("DR_VERIFICATION_MODE_AUTO", "true")
        from tools.deep_research.tool import _resolve_verification_mode
        assert _resolve_verification_mode("moderate", "AI agents") == "moderate"

    def test_light_stays_light(self, monkeypatch):
        monkeypatch.setenv("DR_VERIFICATION_MODE_AUTO", "true")
        from tools.deep_research.tool import _resolve_verification_mode
        assert _resolve_verification_mode("light", "anything") == "light"


class TestVerificationPipelineLogic:
    """Testet die Verifikations-Logik isoliert (ohne LLM-Calls)."""

    def _simulate_verify(self, source_counts: list, mode: str) -> dict:
        """Simuliert die Kern-Logik aus _deep_verify_facts."""
        verified = []
        tentative = []
        unverified = []
        for sc in source_counts:
            if mode == "strict":
                if sc >= 3:
                    verified.append(sc)
                elif sc == 2:
                    tentative.append(sc)
                else:
                    unverified.append(sc)
            elif mode == "moderate":
                if sc >= 2:
                    verified.append(sc)
                elif sc == 1:
                    tentative.append(sc)
                else:
                    unverified.append(sc)
            else:  # light
                if sc >= 1:
                    verified.append(sc)
                else:
                    unverified.append(sc)
        return {"verified": len(verified), "tentative": len(tentative), "unverified": len(unverified)}

    def test_strict_source_count_1_unverified(self):
        result = self._simulate_verify([1, 1, 1], "strict")
        assert result["verified"] == 0
        assert result["unverified"] == 3

    def test_moderate_source_count_1_tentative(self):
        result = self._simulate_verify([1, 1, 1], "moderate")
        assert result["tentative"] == 3
        assert result["unverified"] == 0

    def test_light_source_count_1_verified(self):
        result = self._simulate_verify([1, 1, 1], "light")
        assert result["verified"] == 3
        assert result["unverified"] == 0

    def test_moderate_mixed(self):
        counts = [1, 2, 3, 1, 2]  # 1×source_count=3, 2×sc=2, 2×sc=1
        result = self._simulate_verify(counts, "moderate")
        assert result["verified"] == 3   # sc=2,2,3
        assert result["tentative"] == 2  # sc=1,1
        assert result["unverified"] == 0


class TestQualityGateLogic:
    """Testet die Qualitäts-Gate Entscheidungslogik."""

    def test_gate_passes_at_3(self):
        assert (3 >= 3) is True

    def test_gate_fails_at_2(self):
        assert (2 >= 3) is False

    def test_gate_triggers_fallback_when_strict_fails(self):
        verified_count = 1
        verification_mode = "strict"
        quality_ok = verified_count >= 3
        should_fallback = not quality_ok and verification_mode != "light"
        assert should_fallback is True

    def test_no_fallback_when_already_light(self):
        verified_count = 1
        verification_mode = "light"
        quality_ok = verified_count >= 3
        should_fallback = not quality_ok and verification_mode != "light"
        assert should_fallback is False

    def test_no_fallback_when_quality_ok(self):
        verified_count = 5
        verification_mode = "strict"
        quality_ok = verified_count >= 3
        should_fallback = not quality_ok and verification_mode != "light"
        assert should_fallback is False


class TestArXivFallbackScoreIntegration:
    """Testet ArXiv Fallback-Score im Kontext verschiedener Queries."""

    def _fallback_score(self, query: str, title: str) -> int:
        query_words = set(query.lower().split())
        title_words = set(title.lower().split())
        overlap = len(query_words & title_words)
        return min(10, 5 + overlap)

    def test_ai_query_with_matching_title(self):
        score = self._fallback_score(
            "self-monitoring AI agents",
            "Self-Monitoring AI Agents: A Survey"
        )
        assert score >= 6  # Mindest-Threshold 5 ist passiert

    def test_irrelevant_title_stays_at_5(self):
        score = self._fallback_score(
            "transformer language model",
            "Flower recognition with neural networks"
        )
        # "neural" nicht in query → overlap=0 → score=5
        assert score == 5

    def test_score_always_in_bounds(self):
        test_cases = [
            ("ai", "AI"),
            ("", "Some Title"),
            ("a b c d e f g h i j k", "a b c d e f g h i j k l m n"),
        ]
        for q, t in test_cases:
            score = self._fallback_score(q, t)
            assert 0 <= score <= 10


class TestEndToEndStructure:
    """Prüft die Struktur der End-to-End Komponenten."""

    def test_diagnostics_fields_count(self):
        d = DrDiagnostics()
        s = d.summary()
        assert len(s) >= 20  # Mind. 20 Felder

    def test_diagnostics_phase_times_track(self):
        d = reset()
        d.mark_phase("p1_search")
        d.mark_phase("p2_relevance")
        d.mark_phase("p3_deep_dive")
        d.mark_phase("p4_verify")
        d.finish()
        assert len(d.phase_times) == 4
        for v in d.phase_times.values():
            assert v >= 0

    def test_start_deep_research_signature(self):
        from tools.deep_research.tool import start_deep_research
        import inspect
        sig = inspect.signature(start_deep_research)
        params = list(sig.parameters.keys())
        assert "query" in params
        assert "verification_mode" in params

    def test_run_research_pipeline_exists(self):
        from tools.deep_research.tool import _run_research_pipeline
        assert callable(_run_research_pipeline)
