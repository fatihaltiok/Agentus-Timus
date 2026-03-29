from __future__ import annotations

import deal
from hypothesis import given, settings
from hypothesis import strategies as st

from orchestration.diagnosis_records import build_diagnosis_records, select_lead_diagnosis
from orchestration.root_cause_tasks import build_root_cause_task_payload, classify_change_focus


@deal.post(lambda r: r["primary_change_type"] in {"", "type_normalization", "state_invalidation", "loop_guard", "parsing_fix", "logic_fix"})
@deal.post(lambda r: len(r["followup_change_types"]) <= 3)
def _contract_classify_change_focus(text: str):
    return classify_change_focus(text)


@deal.post(lambda r: r.state in {"primary_fix_emitted", "verification_needed"})
@deal.post(lambda r: len(r.followup_tasks) <= 4)
def _contract_build_root_cause_task_payload(
    claim: str,
    evidence_level: str,
    with_path: bool,
):
    records = build_diagnosis_records(
        [
            {
                "source_agent": "system",
                "claim": claim,
                "evidence_level": evidence_level,
                "confidence": 0.9,
                "actionability": 0.9,
                "verified_paths": ["/tmp/root_cause.py"] if with_path else [],
            }
        ],
        existing_paths=["/tmp/root_cause.py"] if with_path else [],
    )
    return build_root_cause_task_payload(select_lead_diagnosis(records))


@given(st.text(max_size=120))
@settings(max_examples=80)
def test_hypothesis_classify_change_focus_shape(text: str) -> None:
    result = _contract_classify_change_focus(text)
    assert result["primary_change_type"] in {"", "type_normalization", "state_invalidation", "loop_guard", "parsing_fix", "logic_fix"}
    assert len(result["followup_change_types"]) <= 3


@given(
    st.text(min_size=0, max_size=120),
    st.sampled_from(["verified", "corroborated", "observed", "hypothesis", "unverified"]),
    st.booleans(),
)
@settings(max_examples=80)
def test_hypothesis_root_cause_payload_state_is_valid(
    claim: str,
    evidence_level: str,
    with_path: bool,
) -> None:
    result = _contract_build_root_cause_task_payload(claim, evidence_level, with_path)
    assert result.state in {"primary_fix_emitted", "verification_needed"}
    assert len(result.followup_tasks) <= 4
