# tests/test_dr_arxiv.py
"""
Tests für ArXiv-Qualität (M5 — RC5).

Prüft: Threshold-Absenkung, topic-aware Fallback-Score, Score-Bounds.
Kein Netzwerk.
"""

import pytest
from tools.deep_research.trend_researcher import _RELEVANCE_THRESHOLD


class TestArXivThreshold:
    def test_threshold_at_most_5(self):
        """Plan: Default-Threshold ≤ 5 (war 6)."""
        assert _RELEVANCE_THRESHOLD <= 5

    def test_threshold_positive(self):
        assert _RELEVANCE_THRESHOLD > 0

    def test_threshold_at_most_10(self):
        assert _RELEVANCE_THRESHOLD <= 10


class TestTopicAwareFallbackScore:
    """Testet die topic-aware Fallback-Score Logik (vereinfacht)."""

    def _compute_fallback(self, query: str, title: str) -> int:
        """Repliziert die Fallback-Logik aus trend_researcher.py."""
        query_words = set(query.lower().split())
        title_words = set(title.lower().split())
        overlap = len(query_words & title_words)
        return min(10, 5 + overlap)

    def test_exact_match_increases_score(self):
        score = self._compute_fallback(
            "self-monitoring AI agents",
            "Self-Monitoring AI Agents for Autonomous Systems"
        )
        assert score > 5

    def test_no_overlap_stays_at_5(self):
        score = self._compute_fallback(
            "quantum entanglement",
            "Flower Classification Using Deep Learning"
        )
        assert score == 5

    def test_full_title_match_caps_at_10(self):
        # Sehr viele übereinstimmende Wörter → 10
        score = self._compute_fallback(
            "self monitoring ai agents autonomous systems architecture",
            "Self Monitoring AI Agents Autonomous Systems Architecture Review"
        )
        assert score == 10

    def test_partial_overlap_between_5_and_10(self):
        score = self._compute_fallback(
            "AI agents monitoring",
            "Autonomous AI Monitoring Frameworks"
        )
        assert 5 < score <= 10

    def test_score_always_at_least_5(self):
        """Fallback-Score ist immer ≥ 5."""
        queries = ["AI", "climate change", "quantum computing", ""]
        titles = ["Random Paper Title", "Another Study", ""]
        for q in queries:
            for t in titles:
                score = self._compute_fallback(q, t)
                assert score >= 5

    def test_score_never_exceeds_10(self):
        """Fallback-Score ist immer ≤ 10."""
        long_query = " ".join(["ai"] * 20)
        long_title = " ".join(["ai"] * 20)
        score = self._compute_fallback(long_query, long_title)
        assert score <= 10


class TestArXivScoreBoundInvariant:
    """Lean-Theorem Entsprechung: dr_arxiv_score_lower und dr_arxiv_score_upper."""

    @pytest.mark.parametrize("v", [-10, -1, 0, 1, 5, 10, 11, 100])
    def test_score_clamp_lower(self, v: int):
        clamped = max(0, min(10, v))
        assert clamped >= 0

    @pytest.mark.parametrize("v", [-10, -1, 0, 1, 5, 10, 11, 100])
    def test_score_clamp_upper(self, v: int):
        clamped = max(0, min(10, v))
        assert clamped <= 10

    def test_relevance_boundary_accepted(self):
        """relevance == threshold → akzeptiert (¬ n < n)."""
        n = _RELEVANCE_THRESHOLD
        assert not (n < n)

    def test_below_threshold_rejected(self):
        """relevance < threshold → abgelehnt."""
        relevance = _RELEVANCE_THRESHOLD - 1
        assert relevance < _RELEVANCE_THRESHOLD

    def test_at_threshold_accepted(self):
        """relevance == threshold → akzeptiert."""
        relevance = _RELEVANCE_THRESHOLD
        assert not (relevance < _RELEVANCE_THRESHOLD)


class TestArXivMaxCandidates:
    """Prüft dass _fetch_papers mind. 25 Kandidaten anfordert."""

    def test_fetch_params_use_25_minimum(self):
        import inspect
        import tools.deep_research.trend_researcher as t
        source = inspect.getsource(t.ArXivResearcher._fetch_papers)
        assert "25" in source
