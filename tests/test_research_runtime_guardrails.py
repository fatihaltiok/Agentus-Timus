from __future__ import annotations

import sys
from pathlib import Path

import deal
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


@deal.post(lambda r: r in {"completed", "partial_research"})
def derive_research_state_contract(
    quality_gate_passed: bool,
    source_count: int,
    claim_count: int,
    robust_claim_count: int,
    methodology_notes_count: int,
) -> str:
    from tools.deep_research.tool import _derive_research_state_from_metrics

    return _derive_research_state_from_metrics(
        quality_gate_passed=quality_gate_passed,
        source_count=max(0, source_count),
        claim_count=max(0, claim_count),
        robust_claim_count=max(0, robust_claim_count),
        methodology_notes_count=max(0, methodology_notes_count),
    )


def test_assess_research_completion_returns_partial_when_claims_are_too_weak():
    from tools.deep_research.research_contracts import ClaimRecord, ClaimVerdict, SourceRecord, SourceTier, SourceType
    from tools.deep_research.tool import DeepResearchSession, _assess_research_completion

    session = DeepResearchSession("Pruefe Guardrails")
    session.visited_urls = {"https://a", "https://b", "https://c"}
    session.methodology_notes = ["Ran pipeline"]
    session.contract_v2.sources = [
        SourceRecord("s1", "https://a", "A", SourceType.ANALYSIS, SourceTier.B),
        SourceRecord("s2", "https://b", "B", SourceType.ANALYSIS, SourceTier.B),
        SourceRecord("s3", "https://c", "C", SourceType.ANALYSIS, SourceTier.B),
    ]
    session.contract_v2.claims = [
        ClaimRecord("c1", "q", "text", "x", "Claim 1", verdict=ClaimVerdict.INSUFFICIENT_EVIDENCE, confidence=0.2),
        ClaimRecord("c2", "q", "text", "x", "Claim 2", verdict=ClaimVerdict.VENDOR_CLAIM_ONLY, confidence=0.45),
        ClaimRecord("c3", "q", "text", "x", "Claim 3", verdict=ClaimVerdict.MIXED_EVIDENCE, confidence=0.4),
    ]

    assessment = _assess_research_completion(session, quality_gate_passed=False, fallback_triggered=True)

    assert assessment["state"] == "partial_research"
    assert "quality_gate_not_met" in assessment["stop_reasons"]
    assert assessment["telemetry"]["claim_summary"]["total"] == 3


def test_assess_research_completion_returns_completed_for_strong_research():
    from tools.deep_research.research_contracts import ClaimRecord, ClaimVerdict, EvidenceRecord, EvidenceStance, SourceRecord, SourceTier, SourceType
    from tools.deep_research.tool import DeepResearchSession, _assess_research_completion

    session = DeepResearchSession("Pruefe Guardrails")
    session.visited_urls = {"https://a", "https://b", "https://c"}
    session.methodology_notes = ["Ran pipeline"]
    session.contract_v2.sources = [
        SourceRecord("s1", "https://a", "A", SourceType.BENCHMARK, SourceTier.A, has_methodology=True),
        SourceRecord("s2", "https://b", "B", SourceType.ANALYSIS, SourceTier.B, has_methodology=True),
        SourceRecord("s3", "https://c", "C", SourceType.PAPER, SourceTier.A, has_methodology=True, is_primary=True),
    ]
    session.contract_v2.claims = [
        ClaimRecord("c1", "q", "text", "x", "Claim 1", verdict=ClaimVerdict.CONFIRMED, confidence=0.9, supports=["s1", "s2"]),
        ClaimRecord("c2", "q", "text", "x", "Claim 2", verdict=ClaimVerdict.LIKELY, confidence=0.7, supports=["s1", "s3"]),
        ClaimRecord("c3", "q", "text", "x", "Claim 3", verdict=ClaimVerdict.LIKELY, confidence=0.72, supports=["s2", "s3"]),
    ]
    session.contract_v2.evidences = [
        EvidenceRecord("e1", "c1", "s1", EvidenceStance.SUPPORTS),
        EvidenceRecord("e2", "c1", "s2", EvidenceStance.SUPPORTS),
        EvidenceRecord("e3", "c2", "s1", EvidenceStance.SUPPORTS),
        EvidenceRecord("e4", "c2", "s3", EvidenceStance.SUPPORTS),
        EvidenceRecord("e5", "c3", "s2", EvidenceStance.SUPPORTS),
        EvidenceRecord("e6", "c3", "s3", EvidenceStance.SUPPORTS),
    ]

    assessment = _assess_research_completion(session, quality_gate_passed=True, fallback_triggered=False)

    assert assessment["state"] == "completed"
    assert assessment["stop_reasons"] == []


@pytest.mark.asyncio
async def test_start_deep_research_returns_partial_status_when_guardrails_fail(monkeypatch):
    from tools.deep_research.research_contracts import ClaimRecord, ClaimVerdict, SourceRecord, SourceTier, SourceType
    from tools.deep_research.tool import start_deep_research

    async def fake_pipeline(query, session_id, current_session, verification_mode, max_depth, focus_areas):
        current_session.methodology_notes = ["pipeline executed"]
        current_session.visited_urls = {"https://a", "https://b", "https://c"}
        current_session.all_extracted_facts_raw = [{"fact": "Claim A"}]
        current_session.verified_facts = [{"fact": "Claim A", "status": "tentatively_verified"}]
        current_session.contract_v2.sources = [
            SourceRecord("s1", "https://a", "A", SourceType.ANALYSIS, SourceTier.B),
            SourceRecord("s2", "https://b", "B", SourceType.ANALYSIS, SourceTier.B),
            SourceRecord("s3", "https://c", "C", SourceType.ANALYSIS, SourceTier.B),
        ]
        current_session.contract_v2.claims = [
            ClaimRecord("c1", current_session.contract_v2.question.question_id, "text", "x", "Claim A", verdict=ClaimVerdict.LIKELY, confidence=0.7),
        ]
        return {
            "_pipeline_ok": True,
            "verified_data": {"verified_facts": current_session.verified_facts, "unverified_claims": [], "conflicts": []},
            "verified_count": 1,
            "yt_count": 0,
            "trend_count": 0,
            "analysis": {"executive_summary": "ok"},
        }

    monkeypatch.setattr("tools.deep_research.tool._run_research_pipeline", fake_pipeline)

    result = await start_deep_research("Teste Guardrail State", verification_mode="light")

    assert result["status"] == "partial_research"
    assert "completion_summary" in result
    assert "telemetry" in result
    assert "insufficient_robust_claims" in result["completion_summary"]["stop_reasons"]


@given(
    quality_gate_passed=st.booleans(),
    source_count=st.integers(min_value=0, max_value=10),
    claim_count=st.integers(min_value=0, max_value=10),
    robust_claim_count=st.integers(min_value=0, max_value=10),
    methodology_notes_count=st.integers(min_value=0, max_value=10),
)
@settings(deadline=None, max_examples=80)
def test_hypothesis_guardrail_state_contract(
    quality_gate_passed: bool,
    source_count: int,
    claim_count: int,
    robust_claim_count: int,
    methodology_notes_count: int,
):
    state = derive_research_state_contract(
        quality_gate_passed,
        source_count,
        claim_count,
        robust_claim_count,
        methodology_notes_count,
    )
    assert state in {"completed", "partial_research"}
