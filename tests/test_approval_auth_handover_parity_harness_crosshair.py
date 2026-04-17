from __future__ import annotations

from typing import Any

import deal

from orchestration.approval_auth_handover_parity_harness import summarize_approval_auth_handover_results


@deal.post(lambda r: int(r["total"]) >= 0)
@deal.post(lambda r: int(r["passed"]) >= 0)
@deal.post(lambda r: int(r["failed"]) >= 0)
@deal.post(lambda r: int(r["passed"]) + int(r["failed"]) == int(r["total"]))
@deal.post(lambda r: len(r["failed_scenarios"]) == int(r["failed"]))
def _contract_summarize_approval_auth_handover_results(results: list[dict[str, Any]]) -> dict[str, Any]:
    return summarize_approval_auth_handover_results(results)


def test_contract_approval_auth_handover_summary_counts_match() -> None:
    summary = _contract_summarize_approval_auth_handover_results(
        [
            {"scenario_id": "a", "passed": True},
            {"scenario_id": "b", "passed": False},
        ]
    )

    assert summary["total"] == 2
    assert summary["passed"] == 1
    assert summary["failed"] == 1
    assert summary["failed_scenarios"] == ["b"]
