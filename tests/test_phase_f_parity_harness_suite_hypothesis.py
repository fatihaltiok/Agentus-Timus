from __future__ import annotations

from hypothesis import given, strategies as st

from orchestration.phase_f_parity_harness_suite import summarize_phase_f_parity_suite


@given(
    suite_rows=st.lists(
        st.fixed_dictionaries(
            {
                "suite_id": st.text(min_size=1, max_size=8),
                "passed": st.booleans(),
                "summary": st.fixed_dictionaries(
                    {
                        "total": st.integers(min_value=0, max_value=20),
                        "failed": st.integers(min_value=0, max_value=20),
                    }
                ),
            }
        ),
        min_size=0,
        max_size=10,
    )
)
def test_phase_f_parity_suite_summary_counts_are_consistent(
    suite_rows: list[dict[str, object]],
) -> None:
    normalized_rows: list[dict[str, object]] = []
    expected_scenario_total = 0
    expected_failed_scenarios = 0
    for index, row in enumerate(suite_rows):
        summary = dict(row["summary"])
        total = int(summary["total"])
        failed = min(total, int(summary["failed"]))
        normalized_rows.append(
            {
                "suite_id": f"s{index}",
                "passed": bool(row["passed"]),
                "summary": {"total": total, "failed": failed},
            }
        )
        expected_scenario_total += total
        expected_failed_scenarios += failed

    summary = summarize_phase_f_parity_suite(normalized_rows)

    assert summary["suite_total"] == len(normalized_rows)
    assert summary["suite_passed"] + summary["suite_failed"] == len(normalized_rows)
    assert summary["scenario_total"] == expected_scenario_total
    assert summary["scenario_failed"] == expected_failed_scenarios
