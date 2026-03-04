"""
Property-based Tests (Hypothesis) für kritische Algorithmen in Timus.

Gruppe A: _evaluate_relevance  (tools/deep_research/tool.py)
Gruppe B: Goal Progress         (orchestration/goal_queue_manager.py:161)
Gruppe C: ArXiv Relevanzfilter  (tools/deep_research/trend_researcher.py:80)
"""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st


# ---------------------------------------------------------------------------
# GRUPPE A — _evaluate_relevance Scoring-Logik
# ---------------------------------------------------------------------------
# Direkt aus tools/deep_research/tool.py extrahiert (ohne DB/HTTP):
#   base_score + min(matches * 0.05, 0.3)  →  threshold 0.4
MIN_RELEVANCE_SCORE_FOR_SOURCES = 0.4


def _compute_evaluate_relevance(
    sources: list[dict],
    query: str,
    focus: list[str],
    max_sources_to_return: int,
) -> list[tuple[dict, float]]:
    """Inline-Replikation der Scoring-Formel aus tool.py."""
    query_terms = set(query.lower().split())
    focus_terms = set(" ".join(focus).lower().split()) if focus else set()
    all_terms = query_terms | focus_terms

    relevant: list[tuple[dict, float]] = []
    for source in sources:
        base_score = source.get("score", 0.5)
        title = source.get("title", "").lower()
        snippet = source.get("snippet", "").lower()
        combined_text = f"{title} {snippet}"
        matches = sum(1 for term in all_terms if term in combined_text)
        keyword_bonus = min(matches * 0.05, 0.3)
        final_score = base_score + keyword_bonus
        if final_score >= MIN_RELEVANCE_SCORE_FOR_SOURCES:
            relevant.append((source, final_score))

    relevant.sort(key=lambda x: x[1], reverse=True)
    return relevant[:max_sources_to_return]


source_strategy = st.fixed_dictionaries({
    "score": st.floats(min_value=0.0, max_value=1.0, allow_nan=False),
    "title": st.text(max_size=100),
    "snippet": st.text(max_size=200),
})


@given(
    matches=st.integers(min_value=0, max_value=10_000),
)
def test_evaluate_keyword_bonus_never_exceeds_0_3(matches: int) -> None:
    """keyword_bonus darf niemals > 0.3 sein."""
    bonus = min(matches * 0.05, 0.3)
    assert bonus <= 0.3


@given(
    sources=st.lists(source_strategy, min_size=0, max_size=20),
    query=st.text(min_size=1, max_size=50),
    focus=st.lists(st.text(max_size=30), max_size=5),
    max_sources=st.integers(min_value=1, max_value=10),
)
@settings(max_examples=100)
def test_evaluate_result_length_never_exceeds_max(
    sources: list[dict],
    query: str,
    focus: list[str],
    max_sources: int,
) -> None:
    """Rückgabeliste niemals länger als max_sources_to_return."""
    result = _compute_evaluate_relevance(sources, query, focus, max_sources)
    assert len(result) <= max_sources


@given(
    sources=st.lists(source_strategy, min_size=2, max_size=20),
    query=st.text(min_size=1, max_size=50),
    focus=st.lists(st.text(max_size=30), max_size=5),
    max_sources=st.integers(min_value=5, max_value=20),
)
@settings(max_examples=100)
def test_evaluate_scores_descending(
    sources: list[dict],
    query: str,
    focus: list[str],
    max_sources: int,
) -> None:
    """Scores in Rückgabe müssen absteigend sortiert sein."""
    result = _compute_evaluate_relevance(sources, query, focus, max_sources)
    scores = [s for _, s in result]
    assert scores == sorted(scores, reverse=True)


def test_evaluate_empty_sources_returns_empty() -> None:
    """Leere sources-Liste → leere Rückgabe, kein Crash."""
    result = _compute_evaluate_relevance([], "test query", ["focus"], 10)
    assert result == []


# ---------------------------------------------------------------------------
# GRUPPE B — Goal Progress Formel
# ---------------------------------------------------------------------------
# Direkt aus orchestration/goal_queue_manager.py:161:
#   progress = len(completed) / len(milestones) if milestones else 0.0


def _compute_progress(milestones: list, completed: list) -> float:
    return len(completed) / len(milestones) if milestones else 0.0


@given(
    total=st.integers(min_value=1, max_value=1000),
    done=st.integers(min_value=0, max_value=1000),
)
def test_progress_always_in_bounds(total: int, done: int) -> None:
    """progress immer in [0.0, 1.0]."""
    done = min(done, total)
    milestones = list(range(total))
    completed = list(range(done))
    p = _compute_progress(milestones, completed)
    assert 0.0 <= p <= 1.0


def test_progress_zero_milestones_returns_zero() -> None:
    """total_milestones == 0 → progress == 0.0, kein ZeroDivisionError."""
    p = _compute_progress([], [])
    assert p == 0.0


@given(total=st.integers(min_value=1, max_value=1000))
def test_progress_all_completed_returns_one(total: int) -> None:
    """completed == total → progress == 1.0."""
    milestones = list(range(total))
    p = _compute_progress(milestones, milestones)
    assert p == 1.0


# ---------------------------------------------------------------------------
# GRUPPE C — ArXiv Relevanzfilter
# ---------------------------------------------------------------------------
# Direkt aus tools/deep_research/trend_researcher.py:80:
#   relevance = analysis.get("relevance", 5)
#   if relevance < _RELEVANCE_THRESHOLD:  continue


def _arxiv_filter(analysis: dict, threshold: int) -> bool:
    """True = akzeptiert, False = verworfen. Spiegelt Filterlogik aus trend_researcher.py."""
    relevance = analysis.get("relevance", 5)
    return not (relevance < threshold)


@given(
    score=st.integers(min_value=0, max_value=10),
    threshold=st.integers(min_value=1, max_value=10),
)
def test_arxiv_filter_consistency(score: int, threshold: int) -> None:
    """relevance >= threshold ↔ not (relevance < threshold)."""
    analysis = {"relevance": score}
    accepted = _arxiv_filter(analysis, threshold)
    assert accepted == (score >= threshold)


def test_arxiv_filter_missing_key_fallback_5() -> None:
    """Fehlendes relevance-Key → Fallback 5 → bei threshold=6 verworfen."""
    analysis: dict = {}
    accepted = _arxiv_filter(analysis, threshold=6)
    assert accepted is False  # 5 < 6 → verworfen


@given(threshold=st.integers(min_value=1, max_value=10))
def test_arxiv_filter_boundary_accepted(threshold: int) -> None:
    """Boundary: relevance == threshold → akzeptiert (nicht verworfen)."""
    analysis = {"relevance": threshold}
    assert _arxiv_filter(analysis, threshold) is True
