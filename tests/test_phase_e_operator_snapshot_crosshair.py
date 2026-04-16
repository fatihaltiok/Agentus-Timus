from __future__ import annotations

import deal

from orchestration.phase_e_operator_snapshot import summarize_phase_e_operator_lanes


@deal.post(lambda r: r == 1)
def _contract_blocked_lane_count_matches_names_crosshair() -> int:
    summary = summarize_phase_e_operator_lanes(
        {
            "improvement": {
                "blocked": True,
                "last_action": {"observed_at": "2026-04-16T00:10:00+02:00"},
            },
            "memory_curation": {
                "blocked": False,
                "last_action": {"observed_at": "2026-04-16T00:09:00+02:00"},
            },
        }
    )
    return 1 if summary["blocked_lane_count"] == len(summary["blocked_lanes"]) == 1 else 0


@deal.post(lambda r: r == "2026-04-16T00:11:00+02:00")
def _contract_last_activity_uses_latest_observed_at_crosshair() -> str:
    summary = summarize_phase_e_operator_lanes(
        {
            "improvement": {
                "blocked": False,
                "last_action": {"observed_at": "2026-04-16T00:10:00+02:00"},
            },
            "memory_curation": {
                "blocked": False,
                "last_action": {"observed_at": "2026-04-16T00:11:00+02:00"},
            },
        }
    )
    return str(summary["last_activity_at"])
