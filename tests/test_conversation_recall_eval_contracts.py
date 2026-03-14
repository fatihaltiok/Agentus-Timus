"""CrossHair + Hypothesis contracts for conversational recall evaluation."""

from __future__ import annotations

import deal

from orchestration.conversation_recall_eval import (
    ConversationRecallEvalCase,
    evaluate_conversation_recall_case,
    summarize_conversation_recall_evals,
)


def _build_case(
    query: str,
    recalled_texts: list[str],
    expected_markers: list[str],
    forbidden_markers: list[str],
) -> ConversationRecallEvalCase:
    return ConversationRecallEvalCase(
        query=query,
        recalled_items=[{"text": text} for text in recalled_texts],
        expected_markers=expected_markers,
        forbidden_markers=forbidden_markers,
        label="contract",
    )


@deal.pre(lambda query, recalled_texts, expected_markers, forbidden_markers: bool(query.strip()))
@deal.pre(lambda query, recalled_texts, expected_markers, forbidden_markers: len(expected_markers) >= 1)
@deal.post(lambda r: 0.0 <= float(r["score"]) <= 1.0)
@deal.post(lambda r: r["best_rank"] is None or int(r["best_rank"]) >= 1)
@deal.post(lambda r: not r["hit_at_1"] or r["hit_at_3"])
@deal.post(lambda r: not r["hit_at_3"] or r["hit_at_5"])
@deal.post(lambda r: r["best_rank"] != 1 or r["hit_at_1"])
def _contract_evaluate_recall_case(
    query: str,
    recalled_texts: list[str],
    expected_markers: list[str],
    forbidden_markers: list[str],
) -> dict:
    return evaluate_conversation_recall_case(
        _build_case(query, recalled_texts, expected_markers, forbidden_markers)
    )


@deal.pre(lambda first_text, second_text, expected_marker, forbidden_marker: bool(expected_marker.strip()))
@deal.post(lambda r: 0.0 <= float(r["score"]) <= 1.0)
@deal.post(lambda r: r["best_rank"] in {None, 1, 2})
@deal.post(lambda r: not r["hit_at_1"] or r["best_rank"] == 1)
@deal.post(lambda r: not r["hit_at_1"] or r["hit_at_3"])
def _contract_evaluate_two_candidate_case(
    first_text: str,
    second_text: str,
    expected_marker: str,
    forbidden_marker: str,
) -> dict:
    case = ConversationRecallEvalCase(
        query="q",
        recalled_items=[{"text": first_text}, {"text": second_text}],
        expected_markers=[expected_marker],
        forbidden_markers=[forbidden_marker] if forbidden_marker else [],
        label="crosshair",
    )
    return evaluate_conversation_recall_case(case)


@deal.pre(lambda queries, recall_groups, marker_groups: len(queries) == len(recall_groups) == len(marker_groups))
@deal.pre(lambda queries, recall_groups, marker_groups: len(queries) >= 1)
@deal.post(lambda r: r["total_cases"] >= 1)
@deal.post(lambda r: 0.0 <= float(r["hit_rate_at_1"]) <= 1.0)
@deal.post(lambda r: 0.0 <= float(r["hit_rate_at_3"]) <= 1.0)
@deal.post(lambda r: 0.0 <= float(r["hit_rate_at_5"]) <= 1.0)
@deal.post(lambda r: 0.0 <= float(r["wrong_top1_rate"]) <= 1.0)
@deal.post(lambda r: 0.0 <= float(r["useful_rate"]) <= 1.0)
@deal.post(lambda r: float(r["hit_rate_at_1"]) <= float(r["hit_rate_at_3"]) <= float(r["hit_rate_at_5"]))
def _contract_summarize_recall_evals(
    queries: list[str],
    recall_groups: list[list[str]],
    marker_groups: list[list[str]],
) -> dict:
    cases = [
        _build_case(
            query=query,
            recalled_texts=recalled_texts,
            expected_markers=markers or ["fallback"],
            forbidden_markers=[],
        )
        for query, recalled_texts, markers in zip(queries, recall_groups, marker_groups)
    ]
    return summarize_conversation_recall_evals(cases)


@deal.post(lambda r: r["total_cases"] == 2)
@deal.post(lambda r: 0.0 <= float(r["hit_rate_at_1"]) <= 1.0)
@deal.post(lambda r: 0.0 <= float(r["hit_rate_at_3"]) <= 1.0)
@deal.post(lambda r: float(r["hit_rate_at_1"]) <= float(r["hit_rate_at_3"]) <= float(r["hit_rate_at_5"]))
def _contract_summarize_two_cases(
    first_hit: bool,
    second_hit: bool,
) -> dict:
    cases = [
        ConversationRecallEvalCase(
            query="first",
            recalled_items=[{"text": "expected one" if first_hit else "other"}],
            expected_markers=["expected"],
            forbidden_markers=[],
            label="first",
        ),
        ConversationRecallEvalCase(
            query="second",
            recalled_items=[{"text": "expected two" if second_hit else "other"}],
            expected_markers=["expected"],
            forbidden_markers=[],
            label="second",
        ),
    ]
    return summarize_conversation_recall_evals(cases)
