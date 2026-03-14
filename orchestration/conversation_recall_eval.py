"""Evaluation helpers for conversational recall quality."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ConversationRecallEvalCase:
    query: str
    recalled_items: list[dict[str, Any]]
    expected_markers: list[str]
    forbidden_markers: list[str]
    label: str = ""


def _normalize(text: str) -> str:
    return " ".join(str(text or "").lower().split())


def _item_text(item: dict[str, Any]) -> str:
    return _normalize(str(item.get("text") or item.get("content") or ""))


def _matches_expected(item_text: str, markers: list[str]) -> bool:
    normalized_markers = [_normalize(marker) for marker in markers if _normalize(marker)]
    if not normalized_markers:
        return False
    return any(marker in item_text for marker in normalized_markers)


def _matches_forbidden(item_text: str, markers: list[str]) -> bool:
    normalized_markers = [_normalize(marker) for marker in markers if _normalize(marker)]
    if not normalized_markers:
        return False
    return any(marker in item_text for marker in normalized_markers)


def evaluate_conversation_recall_case(case: ConversationRecallEvalCase) -> dict[str, Any]:
    best_rank: int | None = None
    top1_wrong = False
    top1_forbidden = False

    for index, item in enumerate(case.recalled_items, start=1):
        item_text = _item_text(item)
        if not item_text:
            continue
        if index == 1:
            top1_forbidden = _matches_forbidden(item_text, case.forbidden_markers)
            top1_wrong = not _matches_expected(item_text, case.expected_markers)
        if _matches_expected(item_text, case.expected_markers):
            best_rank = index
            break

    hit_at_1 = best_rank == 1
    hit_at_3 = best_rank is not None and best_rank <= 3
    hit_at_5 = best_rank is not None and best_rank <= 5
    useful = hit_at_3 and not top1_forbidden

    if hit_at_1:
        score = 1.0
    elif hit_at_3:
        score = 0.7
    elif hit_at_5:
        score = 0.4
    else:
        score = 0.0

    return {
        "label": case.label or case.query[:80],
        "query": case.query,
        "total_candidates": len(case.recalled_items),
        "best_rank": best_rank,
        "hit_at_1": hit_at_1,
        "hit_at_3": hit_at_3,
        "hit_at_5": hit_at_5,
        "wrong_top1": top1_wrong,
        "forbidden_top1": top1_forbidden,
        "useful": useful,
        "score": score,
    }


def summarize_conversation_recall_evals(cases: list[ConversationRecallEvalCase]) -> dict[str, Any]:
    if not cases:
        return {
            "total_cases": 0,
            "hit_rate_at_1": 0.0,
            "hit_rate_at_3": 0.0,
            "hit_rate_at_5": 0.0,
            "wrong_top1_rate": 0.0,
            "forbidden_top1_rate": 0.0,
            "useful_rate": 0.0,
            "avg_score": 0.0,
            "avg_best_rank": 0.0,
            "results": [],
        }

    results = [evaluate_conversation_recall_case(case) for case in cases]
    total = len(results)
    best_ranks = [int(item["best_rank"]) for item in results if item["best_rank"] is not None]
    return {
        "total_cases": total,
        "hit_rate_at_1": round(sum(1 for item in results if item["hit_at_1"]) / total, 3),
        "hit_rate_at_3": round(sum(1 for item in results if item["hit_at_3"]) / total, 3),
        "hit_rate_at_5": round(sum(1 for item in results if item["hit_at_5"]) / total, 3),
        "wrong_top1_rate": round(sum(1 for item in results if item["wrong_top1"]) / total, 3),
        "forbidden_top1_rate": round(sum(1 for item in results if item["forbidden_top1"]) / total, 3),
        "useful_rate": round(sum(1 for item in results if item["useful"]) / total, 3),
        "avg_score": round(sum(float(item["score"]) for item in results) / total, 3),
        "avg_best_rank": round(sum(best_ranks) / len(best_ranks), 3) if best_ranks else 0.0,
        "results": results,
    }
