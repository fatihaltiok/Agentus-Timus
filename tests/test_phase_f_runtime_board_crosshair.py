from __future__ import annotations

from typing import Any

import deal

from orchestration.phase_f_runtime_board import summarize_phase_f_runtime_board_lanes


@deal.post(lambda r: int(r["lane_count"]) >= 0)
@deal.post(lambda r: int(r["blocked_lane_count"]) == len(r["blocked_lanes"]))
@deal.post(lambda r: int(r["degraded_lane_count"]) == len(r["degraded_lanes"]))
@deal.post(lambda r: r["state"] in {"ok", "warn", "critical"})
@deal.post(lambda r: r["highest_risk_class"] in {"none", "low", "medium", "high", "critical"})
@deal.post(lambda r: r["recommended_action"] in {"allow", "observe", "hold", "recover", "freeze"})
def _contract_summarize_phase_f_runtime_board_lanes(lanes: dict[str, dict[str, Any]]) -> dict[str, Any]:
    return summarize_phase_f_runtime_board_lanes(lanes)


def test_contract_phase_f_runtime_board_summary_counts_match() -> None:
    summary = _contract_summarize_phase_f_runtime_board_lanes(
        {
            "request_flow": {"blocked": False, "degraded": True, "risk_class": "medium", "action": "hold"},
            "improvement": {"blocked": True, "degraded": True, "risk_class": "critical", "action": "freeze"},
        }
    )

    assert summary["lane_count"] == 2
    assert summary["blocked_lane_count"] == 1
    assert summary["degraded_lane_count"] == 2
    assert summary["state"] == "critical"
    assert summary["recommended_action"] == "freeze"
