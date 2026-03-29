from __future__ import annotations

import deal
from hypothesis import given, settings
from hypothesis import strategies as st

from orchestration.diagnosis_records import (
    build_diagnosis_records,
    compile_developer_task_brief,
    normalize_evidence_level,
    select_lead_diagnosis,
)


@deal.post(lambda r: r in {"verified", "corroborated", "observed", "hypothesis", "unverified"})
def _contract_normalize_evidence_level(raw: str) -> str:
    return normalize_evidence_level(raw)


@deal.post(lambda r: r.lead_diagnosis is None or bool(r.lead_diagnosis.claim))
@deal.post(lambda r: len(r.supporting_diagnoses) <= 4)
@deal.post(lambda r: len(r.rejected_diagnoses) <= 8)
def _contract_select_lead_diagnosis(
    claim_a: str,
    evidence_a: str,
    claim_b: str,
    evidence_b: str,
) -> object:
    records = build_diagnosis_records(
        [
            {
                "source_agent": "system",
                "claim": claim_a,
                "evidence_level": evidence_a,
                "confidence": 0.8,
                "actionability": 0.9,
            },
            {
                "source_agent": "meta",
                "claim": claim_b,
                "evidence_level": evidence_b,
                "confidence": 0.4,
                "actionability": 0.4,
            },
        ],
        existing_paths=[],
    )
    return select_lead_diagnosis(records)


@deal.post(lambda r: len(r.verified_paths) <= 8)
@deal.post(lambda r: len(r.verified_functions) <= 8)
@deal.post(lambda r: len(r.supporting_diagnoses) <= 4)
@deal.post(lambda r: len(r.suppressed_claims) <= 8)
def _contract_compile_developer_task_brief(
    claim_a: str,
    evidence_a: str,
    claim_b: str,
    evidence_b: str,
) -> object:
    records = build_diagnosis_records(
        [
            {
                "source_agent": "system",
                "claim": claim_a,
                "evidence_level": evidence_a,
                "confidence": 0.9,
                "actionability": 0.9,
                "verified_functions": ["select_active_location_snapshot"],
            },
            {
                "source_agent": "meta",
                "claim": claim_b,
                "evidence_level": evidence_b,
                "confidence": 0.2,
                "actionability": 0.3,
            },
        ],
        existing_paths=[],
    )
    resolution = select_lead_diagnosis(records)
    return compile_developer_task_brief(resolution)


@given(st.text(max_size=40))
@settings(max_examples=60)
def test_hypothesis_normalize_evidence_level_is_always_valid(raw: str) -> None:
    result = _contract_normalize_evidence_level(raw)
    assert result in {"verified", "corroborated", "observed", "hypothesis", "unverified"}


@given(
    st.text(min_size=0, max_size=120),
    st.sampled_from(["verified", "corroborated", "observed", "hypothesis", "unverified", "belegt"]),
    st.text(min_size=0, max_size=120),
    st.sampled_from(["verified", "corroborated", "observed", "hypothesis", "unverified", "likely"]),
)
@settings(max_examples=80)
def test_hypothesis_lead_diagnosis_shape_is_bounded(
    claim_a: str,
    evidence_a: str,
    claim_b: str,
    evidence_b: str,
) -> None:
    result = _contract_select_lead_diagnosis(claim_a, evidence_a, claim_b, evidence_b)
    assert len(result.supporting_diagnoses) <= 4
    assert len(result.rejected_diagnoses) <= 8


@given(
    st.text(min_size=0, max_size=120),
    st.sampled_from(["verified", "corroborated", "observed", "hypothesis", "unverified"]),
    st.text(min_size=0, max_size=120),
    st.sampled_from(["verified", "corroborated", "observed", "hypothesis", "unverified"]),
)
@settings(max_examples=80)
def test_hypothesis_developer_task_brief_caps_lists(
    claim_a: str,
    evidence_a: str,
    claim_b: str,
    evidence_b: str,
) -> None:
    result = _contract_compile_developer_task_brief(claim_a, evidence_a, claim_b, evidence_b)
    assert len(result.verified_paths) <= 8
    assert len(result.verified_functions) <= 8
    assert len(result.suppressed_claims) <= 8
