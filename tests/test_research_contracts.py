from __future__ import annotations

import sys
from pathlib import Path

import deal
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools.deep_research.research_contracts import (
    BiasRisk,
    ClaimRecord,
    ClaimVerdict,
    EvidenceRecord,
    EvidenceStance,
    ResearchProfile,
    SourceRecord,
    SourceTier,
    SourceType,
    aggregate_overall_confidence,
    claim_is_on_topic,
    choose_research_profile,
    classify_source_tier,
    compute_claim_verdict,
    extract_claim_source_count,
    filter_claims_for_query,
    initial_research_contract,
    is_youtube_hard_evidence,
)


@deal.post(lambda r: r in {p.value for p in ResearchProfile})
def choose_profile_contract(query: str) -> str:
    return choose_research_profile(query).value


@deal.pre(lambda source_type, *_: source_type in {t.value for t in SourceType})
@deal.post(lambda r: r in {t.value for t in SourceTier})
def classify_source_tier_contract(
    source_type: str,
    is_official: bool,
    has_transcript: bool,
    has_methodology: bool,
) -> str:
    return classify_source_tier(
        SourceType(source_type),
        is_official=is_official,
        has_transcript=has_transcript,
        has_methodology=has_methodology,
    ).value


@deal.pre(lambda scores: all(0.0 <= s <= 1.0 for s in scores))
@deal.post(lambda r: 0.0 <= r <= 1.0)
def aggregate_confidence_contract(scores: list[float]) -> float:
    claims = [
        ClaimRecord(
            claim_id=f"c{i}",
            question_id="q1",
            domain="text",
            subject="topic",
            claim_text=f"claim {i}",
            confidence=score,
        )
        for i, score in enumerate(scores)
    ]
    return aggregate_overall_confidence(claims)


@deal.post(lambda r: r != ClaimVerdict.CONFIRMED.value)
def contradictory_verdict_contract() -> str:
    sources = [
        SourceRecord("s1", "https://a", "A", SourceType.BENCHMARK, SourceTier.A, has_methodology=True),
        SourceRecord("s2", "https://b", "B", SourceType.ANALYSIS, SourceTier.B, has_methodology=True),
    ]
    evidences = [
        EvidenceRecord("e1", "c1", "s1", EvidenceStance.SUPPORTS),
        EvidenceRecord("e2", "c1", "s2", EvidenceStance.CONTRADICTS),
    ]
    return compute_claim_verdict(ResearchProfile.SCIENTIFIC, evidences, sources).value


def test_initial_contract_uses_profile_selection():
    contract = initial_research_contract("Vergleiche Benchmarks von KI-Modellen")
    assert contract.question.profile == ResearchProfile.VENDOR_COMPARISON
    assert contract.claims == []
    assert contract.sources == []


def test_official_youtube_with_transcript_is_hard_evidence():
    source = SourceRecord(
        source_id="s1",
        url="https://youtube.com/watch?v=1",
        title="Launch",
        source_type=SourceType.YOUTUBE,
        tier=SourceTier.A,
        is_official=True,
        has_transcript=True,
    )
    assert is_youtube_hard_evidence(source) is True


def test_non_transcript_youtube_is_not_hard_evidence():
    source = SourceRecord(
        source_id="s2",
        url="https://youtube.com/watch?v=2",
        title="Review",
        source_type=SourceType.YOUTUBE,
        tier=SourceTier.D,
        is_official=False,
        has_transcript=False,
    )
    assert is_youtube_hard_evidence(source) is False


def test_vendor_only_evidence_stays_vendor_claim_only():
    source = SourceRecord(
        source_id="vendor-1",
        url="https://vendor.example/blog",
        title="Vendor Claim",
        source_type=SourceType.VENDOR,
        tier=SourceTier.A,
        is_official=True,
    )
    evidence = EvidenceRecord(
        evidence_id="e1",
        claim_id="c1",
        source_id="vendor-1",
        stance=EvidenceStance.SUPPORTS,
    )
    verdict = compute_claim_verdict(
        ResearchProfile.VENDOR_COMPARISON,
        [evidence],
        [source],
    )
    assert verdict == ClaimVerdict.VENDOR_CLAIM_ONLY


def test_two_independent_high_quality_sources_confirm_vendor_comparison():
    sources = [
        SourceRecord(
            source_id="b1",
            url="https://benchmark.example/1",
            title="Benchmark A",
            source_type=SourceType.BENCHMARK,
            tier=SourceTier.A,
            has_methodology=True,
        ),
        SourceRecord(
            source_id="a1",
            url="https://analysis.example/1",
            title="Independent Analysis",
            source_type=SourceType.ANALYSIS,
            tier=SourceTier.B,
            has_methodology=True,
        ),
    ]
    evidences = [
        EvidenceRecord("e1", "c1", "b1", EvidenceStance.SUPPORTS),
        EvidenceRecord("e2", "c1", "a1", EvidenceStance.SUPPORTS),
    ]
    verdict = compute_claim_verdict(
        ResearchProfile.VENDOR_COMPARISON,
        evidences,
        sources,
    )
    assert verdict == ClaimVerdict.CONFIRMED


def test_duplicate_evidence_from_same_source_never_confirms_strict_profile():
    source = SourceRecord(
        source_id="s1",
        url="https://arxiv.org/abs/1234.5678",
        title="Single Paper",
        source_type=SourceType.PAPER,
        tier=SourceTier.A,
        has_methodology=True,
    )
    evidences = [
        EvidenceRecord("e1", "c1", "s1", EvidenceStance.SUPPORTS, notes="source_count=1"),
        EvidenceRecord("e2", "c1", "s1", EvidenceStance.SUPPORTS, notes="source_count=1"),
        EvidenceRecord("e3", "c1", "s1", EvidenceStance.SUPPORTS, notes="source_count=1"),
    ]
    verdict = compute_claim_verdict(ResearchProfile.SCIENTIFIC, evidences, [source])
    assert verdict != ClaimVerdict.CONFIRMED


def test_contradicting_evidence_makes_claim_contested():
    sources = [
        SourceRecord("s1", "https://a", "A", SourceType.BENCHMARK, SourceTier.A, has_methodology=True),
        SourceRecord("s2", "https://b", "B", SourceType.ANALYSIS, SourceTier.B, has_methodology=True),
    ]
    evidences = [
        EvidenceRecord("e1", "c1", "s1", EvidenceStance.SUPPORTS),
        EvidenceRecord("e2", "c1", "s2", EvidenceStance.CONTRADICTS),
    ]
    verdict = compute_claim_verdict(ResearchProfile.SCIENTIFIC, evidences, sources)
    assert verdict == ClaimVerdict.CONTESTED


@given(
    support_count=st.integers(min_value=1, max_value=3),
    contradict_count=st.integers(min_value=1, max_value=3),
)
@settings(deadline=None, max_examples=50)
def test_hypothesis_support_and_contradiction_never_confirm(
    support_count: int,
    contradict_count: int,
):
    sources = []
    evidences = []
    for idx in range(support_count):
        source_id = f"s-support-{idx}"
        sources.append(
            SourceRecord(
                source_id,
                f"https://support-{idx}.example",
                f"Support {idx}",
                SourceType.BENCHMARK,
                SourceTier.A,
                has_methodology=True,
            )
        )
        evidences.append(EvidenceRecord(f"e-support-{idx}", "c1", source_id, EvidenceStance.SUPPORTS))
    for idx in range(contradict_count):
        source_id = f"s-contradict-{idx}"
        sources.append(
            SourceRecord(
                source_id,
                f"https://contradict-{idx}.example",
                f"Contradict {idx}",
                SourceType.ANALYSIS,
                SourceTier.B,
                has_methodology=True,
            )
        )
        evidences.append(EvidenceRecord(f"e-contradict-{idx}", "c1", source_id, EvidenceStance.CONTRADICTS))

    verdict = compute_claim_verdict(ResearchProfile.SCIENTIFIC, evidences, sources)
    assert verdict != ClaimVerdict.CONFIRMED


def test_profile_selection_policy_keywords():
    assert choose_research_profile("Welche Regulierung gilt in der EU?") == ResearchProfile.POLICY_REGULATION


def test_extract_claim_source_count_from_notes():
    assert extract_claim_source_count("legacy_status=verified; source_count=3") == 3
    assert extract_claim_source_count("no_count_here") == 0


def test_claim_is_on_topic_filters_admin_metadata():
    query = "Chinese LLMs Qwen DeepSeek AI agents capabilities comparison 2025 2026"
    assert claim_is_on_topic(query, "DeepSeek-R1 zeigt starke Reasoning-Leistung in Coding-Benchmarks.") is True
    assert claim_is_on_topic(query, "Als Kontaktadresse ist research@deepseek.com angegeben.") is False


def test_filter_claims_for_query_removes_off_topic_claims():
    query = "Chinese LLMs Qwen DeepSeek AI agents capabilities comparison 2025 2026"
    claims = [
        ClaimRecord("c1", "q1", "coding", "DeepSeek", "DeepSeek-R1 ist stark in Coding und Reasoning."),
        ClaimRecord("c2", "q1", "general", "DeepSeek", "Als Kontaktadresse ist research@deepseek.com angegeben."),
    ]
    filtered = filter_claims_for_query(claims, query)
    assert [claim.claim_id for claim in filtered] == ["c1"]


@given(
    query=st.text(min_size=1, max_size=60),
)
@settings(deadline=None, max_examples=100)
def test_hypothesis_profile_selection_always_returns_valid_profile(query: str):
    assert choose_research_profile(query) in set(ResearchProfile)


@given(
    is_official=st.booleans(),
    has_transcript=st.booleans(),
    has_methodology=st.booleans(),
)
@settings(deadline=None, max_examples=100)
def test_hypothesis_youtube_without_transcript_never_beats_b(
    is_official: bool,
    has_transcript: bool,
    has_methodology: bool,
):
    tier = classify_source_tier(
        SourceType.YOUTUBE,
        is_official=is_official,
        has_transcript=has_transcript,
        has_methodology=has_methodology,
    )
    if not has_transcript:
        assert tier == SourceTier.D


@given(scores=st.lists(st.floats(min_value=0.0, max_value=1.0), min_size=0, max_size=10))
@settings(deadline=None, max_examples=100)
def test_hypothesis_aggregate_confidence_stays_bounded(scores: list[float]):
    result = aggregate_confidence_contract(scores)
    assert 0.0 <= result <= 1.0
