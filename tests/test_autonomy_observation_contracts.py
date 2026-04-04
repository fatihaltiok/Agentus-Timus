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
@deal.post(lambda r: isinstance(r["request_correlation"], dict))
@deal.post(lambda r: int(r["request_correlation"]["chat_requests_total"]) >= 0)
@deal.post(lambda r: int(r["request_correlation"]["dispatcher_routes_total"]) >= 0)
@deal.post(lambda r: int(r["request_correlation"]["request_routes_total"]) >= 0)
@deal.post(lambda r: int(r["request_correlation"]["task_routes_total"]) >= 0)
@deal.post(lambda r: int(r["request_correlation"]["task_started_total"]) >= 0)
@deal.post(lambda r: int(r["request_correlation"]["task_completed_total"]) >= 0)
@deal.post(lambda r: int(r["request_correlation"]["task_failed_total"]) >= 0)
@deal.post(
    lambda r: int(r["request_correlation"]["user_visible_failures_total"])
    <= int(r["request_correlation"]["chat_failed_total"])
)
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


def test_contract_summarize_autonomy_events_tracks_request_and_task_routes() -> None:
    summary = _contract_summarize_autonomy_events(
        [
            {
                "event_type": "chat_request_received",
                "payload": {"source": "canvas_chat", "request_id": "req-1"},
            },
            {
                "event_type": "dispatcher_route_selected",
                "payload": {"source": "dispatcher", "agent": "meta"},
            },
            {
                "event_type": "request_route_selected",
                "payload": {"source": "canvas_chat", "agent": "meta", "request_id": "req-1"},
            },
            {
                "event_type": "task_route_selected",
                "payload": {"source": "autonomous_runner", "agent": "research", "task_id": "task-1"},
            },
            {
                "event_type": "chat_request_failed",
                "payload": {"source": "canvas_chat", "agent": "meta", "error_class": "canvas_chat_exception"},
            },
        ]
    )
    correlation = summary["request_correlation"]
    assert correlation["chat_requests_total"] == 1
    assert correlation["dispatcher_routes_total"] == 1
    assert correlation["request_routes_total"] == 1
    assert correlation["task_routes_total"] == 1
    assert correlation["user_visible_failures_total"] == 1
