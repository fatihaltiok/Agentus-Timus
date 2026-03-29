from __future__ import annotations

from typing import Any, Dict, List

import deal

from orchestration.autonomy_observation import summarize_autonomy_events


def _sanitize_events(events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    sanitized: List[Dict[str, Any]] = []
    for event in events[:6]:
        payload = event.get("payload")
        if not isinstance(payload, dict):
            payload = {}
        sanitized.append(
            {
                "event_type": str(event.get("event_type") or "")[:80],
                "payload": {
                    str(key)[:80]: value
                    for key, value in list(payload.items())[:12]
                },
            }
        )
    return sanitized


@deal.post(lambda r: isinstance(r, dict))
@deal.post(lambda r: int(r["total_events"]) >= 0)
@deal.post(lambda r: sum(int(v) for v in r["event_counts"].values()) == int(r["total_events"]))
def _contract_summarize_autonomy_events(events: List[Dict[str, Any]]) -> Dict[str, Any]:
    return summarize_autonomy_events(_sanitize_events(events))


def test_contract_summarize_autonomy_events_counts_match() -> None:
    summary = _contract_summarize_autonomy_events(
        [
            {
                "event_type": "meta_recipe_outcome",
                "payload": {
                    "goal_signature": "pricing|live|light|table",
                    "recipe_id": "simple_live_lookup_document",
                    "success": True,
                    "planner_resolution_state": "adopted",
                    "duration_ms": 1200,
                    "runtime_gap_insertions": ["runtime_goal_gap_document"],
                },
            },
            {
                "event_type": "runtime_goal_gap_inserted",
                "payload": {"adaptive_reason": "runtime_goal_gap_document"},
            },
        ]
    )
    assert summary["total_events"] == 2
    assert summary["event_counts"]["meta_recipe_outcome"] == 1
    assert summary["event_counts"]["runtime_goal_gap_inserted"] == 1
