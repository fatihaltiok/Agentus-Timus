from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from orchestration.approval_auth_handover_parity_harness import summarize_approval_auth_handover_results


@given(
    st.lists(
        st.fixed_dictionaries(
            {
                "scenario_id": st.text(min_size=1, max_size=32),
                "passed": st.booleans(),
            }
        ),
        max_size=16,
    )
)
@settings(max_examples=120)
def test_hypothesis_approval_auth_handover_summary_counts_match(results: list[dict[str, object]]) -> None:
    summary = summarize_approval_auth_handover_results(results)

    assert summary["total"] == len(results)
    assert summary["passed"] + summary["failed"] == summary["total"]
    assert summary["failed"] == len(summary["failed_scenarios"])
