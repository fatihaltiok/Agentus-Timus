from __future__ import annotations

import sys
from pathlib import Path

import deal
from hypothesis import given, settings
from hypothesis import strategies as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools.deep_research.research_contracts import (
    ClaimRecord,
    ClaimVerdict,
    build_domain_scorecards,
    sort_claims_for_report,
    summarize_claims,
)


@deal.pre(lambda confirmed, likely, mixed, vendor, insufficient: min(confirmed, likely, mixed, vendor, insufficient) >= 0)
def summary_contract(confirmed: int, likely: int, mixed: int, vendor: int, insufficient: int) -> dict:
    claims = (
        [ClaimRecord(f"c{i}", "q", "text", "x", f"confirmed {i}", verdict=ClaimVerdict.CONFIRMED) for i in range(confirmed)]
        + [ClaimRecord(f"l{i}", "q", "text", "x", f"likely {i}", verdict=ClaimVerdict.LIKELY) for i in range(likely)]
        + [ClaimRecord(f"m{i}", "q", "text", "x", f"mixed {i}", verdict=ClaimVerdict.MIXED_EVIDENCE) for i in range(mixed)]
        + [ClaimRecord(f"v{i}", "q", "text", "x", f"vendor {i}", verdict=ClaimVerdict.VENDOR_CLAIM_ONLY) for i in range(vendor)]
        + [ClaimRecord(f"i{i}", "q", "text", "x", f"insufficient {i}", verdict=ClaimVerdict.INSUFFICIENT_EVIDENCE) for i in range(insufficient)]
    )
    return summarize_claims(claims)


def test_domain_scorecards_group_by_domain_and_keep_counts():
    claims = [
        ClaimRecord("c1", "q", "coding", "Qwen", "Claim 1", verdict=ClaimVerdict.CONFIRMED, confidence=0.9),
        ClaimRecord("c2", "q", "coding", "Qwen", "Claim 2", verdict=ClaimVerdict.LIKELY, confidence=0.7),
        ClaimRecord("c3", "q", "video", "MiniMax", "Claim 3", verdict=ClaimVerdict.MIXED_EVIDENCE, confidence=0.4),
    ]

    scorecards = build_domain_scorecards(claims)

    assert len(scorecards) == 2
    coding = next(card for card in scorecards if card["domain"] == "coding")
    assert coding["total"] == 2
    assert coding["confirmed"] == 1
    assert coding["likely"] == 1


def test_sort_claims_for_report_prioritizes_confirmed_over_likely():
    claims = [
        ClaimRecord("c1", "q", "text", "A", "Likely claim", verdict=ClaimVerdict.LIKELY, confidence=0.7),
        ClaimRecord("c2", "q", "text", "A", "Confirmed claim", verdict=ClaimVerdict.CONFIRMED, confidence=0.6),
    ]

    ordered = sort_claims_for_report(claims)

    assert ordered[0].verdict == ClaimVerdict.CONFIRMED


@given(
    confirmed=st.integers(min_value=0, max_value=5),
    likely=st.integers(min_value=0, max_value=5),
    mixed=st.integers(min_value=0, max_value=5),
    vendor=st.integers(min_value=0, max_value=5),
    insufficient=st.integers(min_value=0, max_value=5),
)
@settings(deadline=None, max_examples=50)
def test_hypothesis_summary_contract_total_is_conserved(
    confirmed: int,
    likely: int,
    mixed: int,
    vendor: int,
    insufficient: int,
):
    summary = summary_contract(confirmed, likely, mixed, vendor, insufficient)
    assert summary["total"] == confirmed + likely + mixed + vendor + insufficient
