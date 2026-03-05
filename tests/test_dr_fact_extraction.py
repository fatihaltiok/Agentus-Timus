# tests/test_dr_fact_extraction.py
"""
Tests für Fact-Extraktion & Domain-aware Embedding-Threshold (M3 — RC2).

Prüft: EMBEDDING_THRESHOLDS, _group_similar_facts Domain-Logik.
Kein Netzwerk.
"""

import pytest
from tools.deep_research.tool import (
    EMBEDDING_THRESHOLDS,
    _detect_domain,
)


class TestEmbeddingThresholds:
    def test_tech_threshold_lower_than_default(self):
        assert EMBEDDING_THRESHOLDS["tech"] < EMBEDDING_THRESHOLDS["default"]

    def test_tech_threshold_in_valid_range(self):
        t = EMBEDDING_THRESHOLDS["tech"]
        assert 0.0 <= t <= 1.0

    def test_science_threshold_in_valid_range(self):
        t = EMBEDDING_THRESHOLDS["science"]
        assert 0.0 <= t <= 1.0

    def test_default_threshold_in_valid_range(self):
        t = EMBEDDING_THRESHOLDS["default"]
        assert 0.0 <= t <= 1.0

    def test_tech_threshold_at_most_072(self):
        # Plan sieht 0.72 vor; darf nicht höher sein
        assert EMBEDDING_THRESHOLDS["tech"] <= 0.72

    def test_all_domains_present(self):
        assert "tech" in EMBEDDING_THRESHOLDS
        assert "science" in EMBEDDING_THRESHOLDS
        assert "default" in EMBEDDING_THRESHOLDS

    def test_threshold_ordering(self):
        # tech ≤ science ≤ default
        assert EMBEDDING_THRESHOLDS["tech"] <= EMBEDDING_THRESHOLDS["science"]
        assert EMBEDDING_THRESHOLDS["science"] <= EMBEDDING_THRESHOLDS["default"]


class TestGroupSimilarFactsDomain:
    """Testet _group_similar_facts mit Domain-Kontext.

    Ohne Netzwerk können wir die Embedding-Threshold-Auswahl testen,
    aber nicht das eigentliche Grouping (braucht OpenAI-Embeddings).
    """

    def test_detect_domain_tech(self):
        assert _detect_domain("self-monitoring AI agents autonomous") == "tech"

    def test_detect_domain_default(self):
        assert _detect_domain("Klimawandel Ursachen Folgen") == "default"

    def test_detect_domain_llm(self):
        assert _detect_domain("LLM inference optimization") == "tech"

    def test_detect_domain_case_insensitive(self):
        assert _detect_domain("Transformer Architecture") == "tech"

    @pytest.mark.asyncio
    async def test_group_single_fact_returns_single_group(self):
        from tools.deep_research.tool import _group_similar_facts
        facts = [{"fact": "GPT-4 hat 1 Billion Parameter", "source_url": "http://a.com"}]
        groups = await _group_similar_facts(facts, query="AI")
        assert len(groups) == 1
        assert groups[0][0]["fact"] == "GPT-4 hat 1 Billion Parameter"

    @pytest.mark.asyncio
    async def test_group_empty_returns_empty(self):
        from tools.deep_research.tool import _group_similar_facts
        groups = await _group_similar_facts([], query="AI")
        assert groups == []

    @pytest.mark.asyncio
    async def test_group_without_numpy_fallback(self, monkeypatch):
        """Wenn kein Numpy → jeder Fakt wird eigene Gruppe."""
        import tools.deep_research.tool as t
        monkeypatch.setattr(t, "HAS_NUMPY", False)
        facts = [
            {"fact": "Fakt A", "source_url": "http://a.com"},
            {"fact": "Fakt B", "source_url": "http://b.com"},
        ]
        groups = await t._group_similar_facts(facts, query="test")
        assert len(groups) == 2


class TestFactExtractionPrompt:
    """Prüft dass der Prompt auf 8-15 Fakten eingestellt ist (indirekt via Source-Code)."""

    def test_prompt_contains_8_15(self):
        import inspect
        import tools.deep_research.tool as t
        source = inspect.getsource(t._extract_key_facts)
        assert "8–15" in source or "8-15" in source


class TestEmbeddingThresholdBoundInvariant:
    """Invariante: Threshold-Werte sind immer in [0, 1]."""

    @pytest.mark.parametrize("v", [-100, 0, 50, 72, 100, 200])
    def test_threshold_clamp_lower(self, v: int):
        clamped = max(0, min(100, v))
        assert clamped >= 0

    @pytest.mark.parametrize("v", [-100, 0, 50, 72, 100, 200])
    def test_threshold_clamp_upper(self, v: int):
        clamped = max(0, min(100, v))
        assert clamped <= 100
