from __future__ import annotations

import deal

from orchestration.longrunner_queue_parity_harness import summarize_longrunner_queue_parity_results


@deal.post(lambda r: r == 1)
def _contract_longrunner_queue_parity_summary_counts() -> int:
    summary = summarize_longrunner_queue_parity_results(
        [
            {"scenario_id": "ok1", "passed": True},
            {"scenario_id": "fail1", "passed": False},
            {"scenario_id": "ok2", "passed": True},
        ]
    )
    return 1 if summary["total"] == 3 and summary["passed"] == 2 and summary["failed"] == 1 else 0
