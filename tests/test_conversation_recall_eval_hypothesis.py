from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from tests.test_conversation_recall_eval_contracts import (
    _contract_evaluate_recall_case,
    _contract_summarize_recall_evals,
)


@given(
    st.text(min_size=1, max_size=40).filter(lambda text: bool(text.strip())),
    st.lists(st.text(min_size=1, max_size=80), min_size=1, max_size=5),
    st.lists(st.text(min_size=1, max_size=20), min_size=1, max_size=3),
    st.lists(st.text(min_size=1, max_size=20), max_size=3),
)
@settings(max_examples=80)
def test_hypothesis_recall_eval_bounds(
    query: str,
    recalled_texts: list[str],
    expected_markers: list[str],
    forbidden_markers: list[str],
):
    result = _contract_evaluate_recall_case(
        query,
        recalled_texts,
        expected_markers,
        forbidden_markers,
    )

    assert 0.0 <= result["score"] <= 1.0
    assert result["best_rank"] is None or 1 <= result["best_rank"] <= len(recalled_texts)
    assert (not result["hit_at_1"]) or result["best_rank"] == 1


@given(
    st.lists(st.text(min_size=1, max_size=30), min_size=1, max_size=4),
    st.lists(
        st.lists(st.text(min_size=1, max_size=40), min_size=1, max_size=4),
        min_size=1,
        max_size=4,
    ),
    st.lists(
        st.lists(st.text(min_size=1, max_size=15), min_size=1, max_size=3),
        min_size=1,
        max_size=4,
    ),
)
@settings(max_examples=60)
def test_hypothesis_recall_summary_rates_are_bounded(
    queries: list[str],
    recall_groups: list[list[str]],
    marker_groups: list[list[str]],
):
    size = min(len(queries), len(recall_groups), len(marker_groups))
    result = _contract_summarize_recall_evals(
        queries[:size],
        recall_groups[:size],
        marker_groups[:size],
    )

    assert result["total_cases"] == size
    assert 0.0 <= result["hit_rate_at_1"] <= 1.0
    assert 0.0 <= result["hit_rate_at_3"] <= 1.0
    assert 0.0 <= result["hit_rate_at_5"] <= 1.0
    assert result["hit_rate_at_1"] <= result["hit_rate_at_3"] <= result["hit_rate_at_5"]
