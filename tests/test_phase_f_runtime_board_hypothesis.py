from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from orchestration.phase_f_runtime_board import summarize_phase_f_runtime_board_lanes


@given(
    st.dictionaries(
        st.sampled_from(
            [
                "stack",
                "request_flow",
                "communication",
                "approval_auth",
                "improvement",
                "memory_curation",
                "recovery",
                "providers",
            ]
        ),
        st.fixed_dictionaries(
            {
                "blocked": st.booleans(),
                "degraded": st.booleans(),
                "risk_class": st.sampled_from(["none", "low", "medium", "high", "critical"]),
                "action": st.sampled_from(["allow", "observe", "hold", "recover", "freeze"]),
            }
        ),
        max_size=8,
    )
)
@settings(max_examples=120)
def test_hypothesis_phase_f_runtime_board_summary_counts_match(lanes: dict[str, dict[str, object]]) -> None:
    summary = summarize_phase_f_runtime_board_lanes(lanes)

    assert summary["lane_count"] == len(lanes)
    assert summary["blocked_lane_count"] == len(summary["blocked_lanes"])
    assert summary["degraded_lane_count"] == len(summary["degraded_lanes"])
    assert summary["state"] in {"ok", "warn", "critical"}
    assert summary["highest_risk_class"] in {"none", "low", "medium", "high", "critical"}
    assert summary["recommended_action"] in {"allow", "observe", "hold", "recover", "freeze"}
