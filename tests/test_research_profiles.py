from __future__ import annotations

import sys
from pathlib import Path

import deal
from hypothesis import given, settings
from hypothesis import strategies as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools.deep_research.research_contracts import (
    ClaimVerdict,
    EvidenceRecord,
    EvidenceStance,
    ResearchProfile,
    SourceRecord,
    SourceTier,
    SourceType,
    compute_claim_verdict,
    get_research_profile_policy,
)


@deal.pre(lambda profile: profile in {p.value for p in ResearchProfile})
@deal.post(lambda r: r >= 1)
def profile_confirm_threshold_contract(profile: str) -> int:
    return get_research_profile_policy(ResearchProfile(profile)).min_high_quality_independent_for_confirmed


def test_policy_profile_requires_authoritative_primary_source_for_confirmed():
    sources = [
        SourceRecord(
            "s1",
            "https://analysis.example/policy",
            "Policy Analysis",
            SourceType.ANALYSIS,
            SourceTier.B,
            has_methodology=True,
        ),
        SourceRecord(
            "s2",
            "https://press.example/policy",
            "Press Coverage",
            SourceType.PRESS,
            SourceTier.B,
            has_methodology=True,
        ),
    ]
    evidences = [
        EvidenceRecord("e1", "c1", "s1", EvidenceStance.SUPPORTS),
        EvidenceRecord("e2", "c1", "s2", EvidenceStance.SUPPORTS),
    ]

    verdict = compute_claim_verdict(ResearchProfile.POLICY_REGULATION, evidences, sources)

    assert verdict == ClaimVerdict.LIKELY


def test_policy_profile_confirms_with_regulator_source():
    sources = [
        SourceRecord(
            "s1",
            "https://eur-lex.europa.eu/example",
            "EU Regulation",
            SourceType.REGULATOR,
            SourceTier.A,
            is_primary=True,
            is_official=True,
        )
    ]
    evidences = [EvidenceRecord("e1", "c1", "s1", EvidenceStance.SUPPORTS)]

    verdict = compute_claim_verdict(ResearchProfile.POLICY_REGULATION, evidences, sources)

    assert verdict == ClaimVerdict.CONFIRMED


def test_scientific_profile_does_not_confirm_without_primary_or_methodological_support():
    sources = [
        SourceRecord("s1", "https://analysis.example/a", "Analysis A", SourceType.ANALYSIS, SourceTier.B),
        SourceRecord("s2", "https://analysis.example/b", "Analysis B", SourceType.ANALYSIS, SourceTier.B),
    ]
    evidences = [
        EvidenceRecord("e1", "c1", "s1", EvidenceStance.SUPPORTS),
        EvidenceRecord("e2", "c1", "s2", EvidenceStance.SUPPORTS),
    ]

    verdict = compute_claim_verdict(ResearchProfile.SCIENTIFIC, evidences, sources)

    assert verdict == ClaimVerdict.LIKELY


def test_news_profile_does_not_confirm_only_with_youtube():
    sources = [
        SourceRecord(
            "s1",
            "https://youtube.com/watch?v=1",
            "Official stream",
            SourceType.YOUTUBE,
            SourceTier.A,
            is_official=True,
            has_transcript=True,
        ),
        SourceRecord(
            "s2",
            "https://youtube.com/watch?v=2",
            "Conference replay",
            SourceType.YOUTUBE,
            SourceTier.B,
            has_transcript=True,
        ),
    ]
    evidences = [
        EvidenceRecord("e1", "c1", "s1", EvidenceStance.SUPPORTS),
        EvidenceRecord("e2", "c1", "s2", EvidenceStance.SUPPORTS),
    ]

    verdict = compute_claim_verdict(ResearchProfile.NEWS, evidences, sources)

    assert verdict == ClaimVerdict.LIKELY


def test_vendor_comparison_requires_methodological_support_for_confirmed():
    sources = [
        SourceRecord("s1", "https://analysis.example/a", "Analysis A", SourceType.ANALYSIS, SourceTier.B),
        SourceRecord("s2", "https://analysis.example/b", "Analysis B", SourceType.ANALYSIS, SourceTier.B),
    ]
    evidences = [
        EvidenceRecord("e1", "c1", "s1", EvidenceStance.SUPPORTS),
        EvidenceRecord("e2", "c1", "s2", EvidenceStance.SUPPORTS),
    ]

    verdict = compute_claim_verdict(ResearchProfile.VENDOR_COMPARISON, evidences, sources)

    assert verdict == ClaimVerdict.LIKELY


@given(profile=st.sampled_from([p.value for p in ResearchProfile]))
@settings(deadline=None, max_examples=40)
def test_hypothesis_all_profiles_have_positive_confirm_threshold(profile: str):
    threshold = profile_confirm_threshold_contract(profile)
    assert threshold >= 1


@given(
    profile=st.sampled_from([
        ResearchProfile.FACT_CHECK,
        ResearchProfile.NEWS,
        ResearchProfile.SCIENTIFIC,
        ResearchProfile.VENDOR_COMPARISON,
        ResearchProfile.MARKET_INTELLIGENCE,
        ResearchProfile.POLICY_REGULATION,
        ResearchProfile.COMPETITIVE_LANDSCAPE,
    ])
)
@settings(deadline=None, max_examples=30)
def test_hypothesis_vendor_only_never_confirms_under_any_profile(profile: ResearchProfile):
    source = SourceRecord(
        "vendor-1",
        "https://vendor.example/blog",
        "Vendor Claim",
        SourceType.VENDOR,
        SourceTier.A,
        is_official=True,
    )
    evidence = EvidenceRecord("e1", "c1", "vendor-1", EvidenceStance.SUPPORTS)
    verdict = compute_claim_verdict(profile, [evidence], [source])
    assert verdict != ClaimVerdict.CONFIRMED
