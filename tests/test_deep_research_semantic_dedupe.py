from __future__ import annotations

import pytest


def test_semantic_merge_candidates_require_confidence_and_protected_term_alignment():
    from tools.deep_research.research_contracts import ClaimRecord
    from tools.deep_research.tool import DeepResearchSession, _filter_semantic_merge_candidates

    session = DeepResearchSession(
        "Industrieroboter Sensorik",
        focus_areas=["Kraft-Momenten-Sensor", "Drehmomentsensor"],
    )
    claims = [
        ClaimRecord("c1", "q", "robotics", "robot", "Kraft-Momenten-Sensor misst Kraefte im Roboterarm."),
        ClaimRecord("c2", "q", "robotics", "robot", "Drehmomentsensor misst Drehmoment im Roboterarm."),
        ClaimRecord("c3", "q", "robotics", "robot", "Qwen unterstuetzt Tool Use in agentischen Workflows."),
        ClaimRecord("c4", "q", "robotics", "robot", "Qwen unterstuetzt Tool Use fuer agentische Workflows."),
    ]

    accepted = _filter_semantic_merge_candidates(
        session,
        claims,
        [
            {
                "left_claim_text": "Kraft-Momenten-Sensor misst Kraefte im Roboterarm.",
                "right_claim_text": "Drehmomentsensor misst Drehmoment im Roboterarm.",
                "reason": "similar sensor family",
                "confidence": 0.96,
            },
            {
                "left_claim_text": "Qwen unterstuetzt Tool Use in agentischen Workflows.",
                "right_claim_text": "Qwen unterstuetzt Tool Use fuer agentische Workflows.",
                "reason": "same capability phrased differently",
                "confidence": 0.84,
            },
            {
                "left_claim_text": "Qwen unterstuetzt Tool Use in agentischen Workflows.",
                "right_claim_text": "Qwen unterstuetzt Tool Use fuer agentische Workflows.",
                "reason": "same capability phrased differently",
                "confidence": 0.92,
            },
        ],
    )

    assert accepted == [
        {
            "left_claim_text": "Qwen unterstuetzt Tool Use in agentischen Workflows.",
            "right_claim_text": "Qwen unterstuetzt Tool Use fuer agentische Workflows.",
            "confidence": 0.92,
            "reason": "same capability phrased differently",
        }
    ]


def test_apply_semantic_merge_candidates_never_expands_claims():
    from tools.deep_research.research_contracts import ClaimRecord
    from tools.deep_research.tool import _apply_semantic_merge_candidates

    claims = [
        ClaimRecord("c1", "q", "agentic", "Qwen", "Qwen unterstuetzt Tool Use.", claim_type="verified_fact"),
        ClaimRecord("c2", "q", "agentic", "Qwen", "Qwen unterstuetzt Tool Use fuer Agenten.", claim_type="legacy_claim"),
        ClaimRecord("c3", "q", "agentic", "Qwen", "Qwen hat 32B Parameter.", claim_type="legacy_claim"),
    ]

    merged = _apply_semantic_merge_candidates(
        claims,
        [
            {
                "left_claim_text": "Qwen unterstuetzt Tool Use.",
                "right_claim_text": "Qwen unterstuetzt Tool Use fuer Agenten.",
                "confidence": 0.91,
                "reason": "near duplicate",
            }
        ],
    )

    assert len(merged) == 2
    assert len({claim.claim_text for claim in merged}) == len(merged)


@pytest.mark.asyncio
async def test_semantic_dedupe_cache_reduces_exported_legacy_claims(monkeypatch):
    from orchestration.ephemeral_workers import WorkerResult
    from tools.deep_research.tool import (
        DeepResearchSession,
        ResearchNode,
        _populate_semantic_claim_dedupe_cache,
    )

    monkeypatch.setenv("DR_WORKER_SEMANTIC_DEDUPE_ENABLED", "true")

    async def _fake_run_worker_batch(*args, **kwargs):
        return [
            WorkerResult(
                worker_type="semantic_claim_dedupe",
                status="ok",
                payload={
                    "merge_candidates": [
                        {
                            "left_claim_text": "Qwen unterstuetzt Tool Use in agentischen Workflows.",
                            "right_claim_text": "Qwen unterstuetzt Tool Use fuer agentische Workflows.",
                            "reason": "same capability",
                            "confidence": 0.93,
                        }
                    ]
                },
                provider="openai",
                model="gpt-5.4-mini",
                duration_ms=11,
                max_tokens=1500,
            )
        ]

    monkeypatch.setattr("tools.deep_research.tool.run_worker_batch", _fake_run_worker_batch)

    session = DeepResearchSession(
        "Chinese LLMs Qwen tool use",
        focus_areas=["tool use", "agentic workflows"],
    )
    session.research_tree = [
        ResearchNode(url="https://example.com/qwen-tool-use", title="Qwen tool use", content_snippet="tool use")
    ]
    session.verified_facts = [
        {
            "fact": "Qwen unterstuetzt Tool Use in agentischen Workflows.",
            "status": "verified",
            "source_count": 2,
            "example_source_url": "https://example.com/qwen-tool-use",
        }
    ]
    session.unverified_claims = [
        {
            "fact": "Qwen unterstuetzt Tool Use fuer agentische Workflows.",
            "source": "https://example.com/qwen-tool-use-2",
            "source_type": "web",
            "source_count": 1,
        }
    ]

    await _populate_semantic_claim_dedupe_cache(session, session_id="research_test_session")
    exported = session.export_contract_v2()

    qwen_claims = [claim for claim in exported["claims"] if "Qwen unterstuetzt Tool Use" in claim["claim_text"]]
    assert len(qwen_claims) == 1
    meta = session.research_metadata["semantic_claim_dedupe"]
    assert meta["status"] == "ok"
    assert meta["accepted_count"] == 1
    assert meta["fallback_used"] is False
