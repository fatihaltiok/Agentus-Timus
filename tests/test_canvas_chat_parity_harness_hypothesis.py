from __future__ import annotations

from hypothesis import given, strategies as st

from orchestration.canvas_chat_parity_harness import summarize_canvas_chat_harness_results


@given(
    passed_flags=st.lists(st.booleans(), min_size=0, max_size=20),
)
def test_canvas_chat_parity_harness_summary_counts_are_consistent(
    passed_flags: list[bool],
) -> None:
    rows = [
        {"scenario_id": f"scenario_{index}", "passed": flag}
        for index, flag in enumerate(passed_flags)
    ]
    summary = summarize_canvas_chat_harness_results(rows)

    assert summary["total"] == len(passed_flags)
    assert summary["passed"] + summary["failed"] == len(passed_flags)
    assert len(summary["failed_scenarios"]) == summary["failed"]
