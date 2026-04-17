from __future__ import annotations

import sys
from pathlib import Path

from hypothesis import given, settings
from hypothesis import strategies as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from orchestration.phase_f_contract_eval import summarize_phase_f_contract_results


@given(
    st.lists(
        st.fixed_dictionaries(
            {
                "contract_id": st.text(min_size=1, max_size=24),
                "passed": st.booleans(),
                "area": st.text(max_size=18),
            }
        ),
        max_size=16,
    )
)
@settings(max_examples=120)
def test_hypothesis_phase_f_contract_summary_counts_match(results: list[dict[str, object]]) -> None:
    summary = summarize_phase_f_contract_results(results)

    assert summary["total"] == len(results)
    assert summary["passed"] + summary["failed"] == summary["total"]
    assert 0.0 <= float(summary["pass_rate"]) <= 1.0
    if summary["failed"] == 0:
        assert summary["state"] == "pass"
        assert summary["failed_contracts"] == []
    else:
        assert summary["state"] == "fail"
        assert len(summary["failed_contracts"]) >= 1
