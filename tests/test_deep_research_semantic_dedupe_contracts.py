from __future__ import annotations

import sys
from pathlib import Path

import deal

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools.deep_research.research_contracts import ClaimRecord
from tools.deep_research.tool import (
    DeepResearchSession,
    _apply_semantic_merge_candidates,
    _filter_semantic_merge_candidates,
)


@deal.post(lambda r: r is True)
def _contract_semantic_dedupe_confidence_gate() -> bool:
    session = DeepResearchSession("Chinese LLMs Qwen tool use", focus_areas=["tool use"])
    claims = [
        ClaimRecord("c1", "q", "agentic", "Qwen", "Qwen unterstuetzt Tool Use."),
        ClaimRecord("c2", "q", "agentic", "Qwen", "Qwen unterstuetzt Tool Use fuer Agenten."),
    ]
    accepted = _filter_semantic_merge_candidates(
        session,
        claims,
        [
            {
                "left_claim_text": "Qwen unterstuetzt Tool Use.",
                "right_claim_text": "Qwen unterstuetzt Tool Use fuer Agenten.",
                "reason": "near duplicate",
                "confidence": 0.84,
            }
        ],
    )
    return accepted == []


@deal.post(lambda r: r is True)
def _contract_semantic_dedupe_never_expands() -> bool:
    claims = [
        ClaimRecord("c1", "q", "agentic", "Qwen", "Qwen unterstuetzt Tool Use.", claim_type="verified_fact"),
        ClaimRecord("c2", "q", "agentic", "Qwen", "Qwen unterstuetzt Tool Use fuer Agenten.", claim_type="legacy_claim"),
    ]
    merged = _apply_semantic_merge_candidates(
        claims,
        [
            {
                "left_claim_text": "Qwen unterstuetzt Tool Use.",
                "right_claim_text": "Qwen unterstuetzt Tool Use fuer Agenten.",
                "reason": "near duplicate",
                "confidence": 0.91,
            }
        ],
    )
    return 0 < len(merged) <= len(claims)


def test_contract_semantic_dedupe_confidence_gate():
    assert _contract_semantic_dedupe_confidence_gate() is True


def test_contract_semantic_dedupe_never_expands():
    assert _contract_semantic_dedupe_never_expands() is True
