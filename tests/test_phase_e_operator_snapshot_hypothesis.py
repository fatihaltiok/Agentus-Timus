from __future__ import annotations

from hypothesis import given, strategies as st

from orchestration.phase_e_operator_snapshot import summarize_phase_e_operator_lanes


@given(
    improvement_blocked=st.booleans(),
    memory_blocked=st.booleans(),
    improvement_time=st.one_of(st.just(""), st.datetimes().map(lambda dt: dt.isoformat())),
    memory_time=st.one_of(st.just(""), st.datetimes().map(lambda dt: dt.isoformat())),
)
def test_hypothesis_summarize_phase_e_operator_lanes_counts_blocked_lanes_correctly(
    improvement_blocked: bool,
    memory_blocked: bool,
    improvement_time: str,
    memory_time: str,
) -> None:
    summary = summarize_phase_e_operator_lanes(
        {
            "improvement": {
                "blocked": improvement_blocked,
                "last_action": {"observed_at": improvement_time},
            },
            "memory_curation": {
                "blocked": memory_blocked,
                "last_action": {"observed_at": memory_time},
            },
        }
    )

    assert summary["blocked_lane_count"] == len(summary["blocked_lanes"])
    assert set(summary["blocked_lanes"]).issubset({"improvement", "memory_curation"})
