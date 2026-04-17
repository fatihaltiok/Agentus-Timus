from __future__ import annotations

import deal

from orchestration.phase_f_parity_harness_suite import summarize_phase_f_parity_suite


@deal.post(lambda r: r == 1)
def _contract_phase_f_parity_suite_summary_counts() -> int:
    summary = summarize_phase_f_parity_suite(
        [
            {"suite_id": "chat", "passed": True, "summary": {"total": 3, "failed": 0}},
            {"suite_id": "delegation", "passed": False, "summary": {"total": 4, "failed": 1}},
        ]
    )
    return 1 if summary["suite_total"] == 2 and summary["scenario_total"] == 7 and summary["scenario_failed"] == 1 else 0
