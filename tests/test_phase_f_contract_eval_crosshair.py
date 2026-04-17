from __future__ import annotations

from typing import Any

import deal

from orchestration.phase_f_contract_eval import summarize_phase_f_contract_results


@deal.post(lambda r: int(r["total"]) >= 0)
@deal.post(lambda r: int(r["passed"]) >= 0)
@deal.post(lambda r: int(r["failed"]) >= 0)
@deal.post(lambda r: int(r["passed"]) + int(r["failed"]) == int(r["total"]))
@deal.post(lambda r: 0.0 <= float(r["pass_rate"]) <= 1.0)
@deal.post(lambda r: r["state"] in {"pass", "fail"})
@deal.post(lambda r: isinstance(r["failed_contracts"], list))
@deal.post(lambda r: isinstance(r["areas"], list))
def _contract_summarize_phase_f_contract_results(results: list[dict[str, Any]]) -> dict[str, Any]:
    return summarize_phase_f_contract_results(results)


def test_contract_phase_f_summary_counts_match() -> None:
    summary = _contract_summarize_phase_f_contract_results(
        [
            {"contract_id": "a", "passed": True, "area": "lane"},
            {"contract_id": "b", "passed": False, "area": "handoff"},
        ]
    )

    assert summary["total"] == 2
    assert summary["passed"] == 1
    assert summary["failed"] == 1
    assert summary["state"] == "fail"
    assert summary["failed_contracts"] == ["b"]
