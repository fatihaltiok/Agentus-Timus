"""
tests/test_research_improvements.py — Phase-3: Research Agent Verbesserungen

Tests für:
  - _deduplicate_sources: URL-basierte Duplikat-Entfernung (Th.45)
  - _rank_sources: Ranking-Score ∈ [0, 10] (Th.46)
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from agent.agents.research import DeepResearchAgent


# ──────────────────────────────────────────────────────────────────
# _normalize_url
# ──────────────────────────────────────────────────────────────────

def test_normalize_removes_https():
    assert DeepResearchAgent._normalize_url("https://arxiv.org/abs/1234") == "arxiv.org/abs/1234"


def test_normalize_removes_www():
    assert DeepResearchAgent._normalize_url("https://www.nature.com/articles/x") == "nature.com/articles/x"


def test_normalize_removes_query():
    assert DeepResearchAgent._normalize_url("https://example.com/page?foo=bar") == "example.com/page"


def test_normalize_removes_trailing_slash():
    assert DeepResearchAgent._normalize_url("https://github.com/user/repo/") == "github.com/user/repo"


# ──────────────────────────────────────────────────────────────────
# _deduplicate_sources (Th.45: unique ≤ total)
# ──────────────────────────────────────────────────────────────────

def test_dedup_removes_exact_duplicates():
    sources = [
        {"url": "https://arxiv.org/abs/1234"},
        {"url": "https://arxiv.org/abs/1234"},
        {"url": "https://arxiv.org/abs/5678"},
    ]
    result = DeepResearchAgent._deduplicate_sources(sources)
    assert len(result) == 2
    assert len(result) <= len(sources)


def test_dedup_removes_http_https_variants():
    sources = [
        {"url": "http://arxiv.org/abs/1234"},
        {"url": "https://arxiv.org/abs/1234"},
    ]
    result = DeepResearchAgent._deduplicate_sources(sources)
    assert len(result) == 1


def test_dedup_removes_www_variants():
    sources = [
        {"url": "https://www.nature.com/articles/x"},
        {"url": "https://nature.com/articles/x"},
    ]
    result = DeepResearchAgent._deduplicate_sources(sources)
    assert len(result) == 1


def test_dedup_keeps_different_urls():
    sources = [
        {"url": "https://arxiv.org/abs/1"},
        {"url": "https://arxiv.org/abs/2"},
        {"url": "https://github.com/user/repo"},
    ]
    result = DeepResearchAgent._deduplicate_sources(sources)
    assert len(result) == 3


def test_dedup_empty_list():
    assert DeepResearchAgent._deduplicate_sources([]) == []


def test_dedup_preserves_no_url_entries():
    sources = [{"title": "No URL 1"}, {"title": "No URL 2"}]
    result = DeepResearchAgent._deduplicate_sources(sources)
    assert len(result) == 2


@given(n=st.integers(min_value=0, max_value=20))
@settings(max_examples=100)
def test_dedup_invariant_unique_le_total(n):
    """Th.45: unique_count ≤ total_count."""
    sources = [{"url": f"https://example.com/page{i % 3}"} for i in range(n)]
    result = DeepResearchAgent._deduplicate_sources(sources)
    assert len(result) <= len(sources)


# ──────────────────────────────────────────────────────────────────
# _rank_sources (Th.46: score ∈ [0, 10])
# ──────────────────────────────────────────────────────────────────

def test_rank_arxiv_gets_authority_bonus():
    sources = [{"url": "https://arxiv.org/abs/1234", "relevance_score": 0.5}]
    result = DeepResearchAgent._rank_sources(sources)
    assert result[0]["ranking_score"] > 2  # Domain-Bonus (+2) + relevance


def test_rank_score_in_bounds():
    sources = [
        {"url": "https://arxiv.org/abs/1", "relevance_score": 1.0, "verified": True},
        {"url": "https://unknown.xyz/page", "relevance_score": 0.0},
    ]
    result = DeepResearchAgent._rank_sources(sources)
    for s in result:
        assert 0 <= s["ranking_score"] <= 10


@given(
    relevance=st.floats(min_value=0.0, max_value=1.0, allow_nan=False),
    authority=st.booleans(),
)
@settings(max_examples=200)
def test_rank_score_invariant_bounds(relevance, authority):
    """Th.46: ranking_score ∈ [0, 10]."""
    url = "https://arxiv.org/abs/1" if authority else "https://unknown.xyz/1"
    sources = [{"url": url, "relevance_score": relevance}]
    result = DeepResearchAgent._rank_sources(sources)
    score = result[0]["ranking_score"]
    assert 0 <= score <= 10


def test_rank_sorted_descending():
    sources = [
        {"url": "https://unknown.xyz/1", "relevance_score": 0.1},
        {"url": "https://arxiv.org/abs/1", "relevance_score": 0.9, "verified": True},
    ]
    result = DeepResearchAgent._rank_sources(sources)
    assert result[0]["ranking_score"] >= result[1]["ranking_score"]


def test_rank_empty_list():
    assert DeepResearchAgent._rank_sources([]) == []


def test_rank_penalizes_german_state_affiliated_sources():
    sources = [
        {"url": "https://www.bundestag.de/dokumente/textarchiv", "relevance_score": 0.9, "verified": True},
        {"url": "https://www.reuters.com/world/europe/example", "relevance_score": 0.9, "verified": True},
    ]
    result = DeepResearchAgent._rank_sources(sources)
    assert result[0]["url"].startswith("https://www.reuters.com")
    flagged = next(item for item in result if "bundestag.de" in item["url"])
    assert flagged["source_policy_flag"] == "german_state_affiliated"
