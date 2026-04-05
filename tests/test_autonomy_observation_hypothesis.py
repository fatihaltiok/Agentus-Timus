from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from tests.test_autonomy_observation_contracts import _contract_summarize_autonomy_events


@given(
    st.lists(
        st.sampled_from(
            [
                {"event_type": "chat_request_received", "payload": {"source": "canvas_chat", "request_id": "req"}},
                {"event_type": "chat_request_completed", "payload": {"source": "canvas_chat", "agent": "meta"}},
                {"event_type": "chat_request_failed", "payload": {"source": "canvas_chat", "agent": "meta", "error_class": "canvas_chat_exception"}},
                {"event_type": "dispatcher_route_selected", "payload": {"source": "dispatcher", "agent": "meta"}},
                {"event_type": "request_route_selected", "payload": {"source": "canvas_chat", "agent": "meta"}},
                {"event_type": "task_route_selected", "payload": {"source": "autonomous_runner", "agent": "research"}},
                {"event_type": "task_execution_started", "payload": {"source": "autonomous_runner", "task_id": "task"}},
                {"event_type": "task_execution_completed", "payload": {"source": "autonomous_runner", "agent": "research"}},
                {"event_type": "task_execution_failed", "payload": {"source": "autonomous_runner", "agent": "research", "error_class": "task_exception"}},
            ]
        ),
        min_size=0,
        max_size=6,
    )
)
@settings(max_examples=80)
def test_hypothesis_autonomy_observation_request_correlation_is_bounded(events):
    summary = _contract_summarize_autonomy_events(events)
    correlation = summary["request_correlation"]

    assert correlation["chat_requests_total"] >= 0
    assert correlation["chat_completed_total"] >= 0
    assert correlation["chat_failed_total"] >= 0
    assert correlation["dispatcher_routes_total"] >= 0
    assert correlation["request_routes_total"] >= 0
    assert correlation["task_routes_total"] >= 0
    assert correlation["task_started_total"] >= 0
    assert correlation["task_completed_total"] >= 0
    assert correlation["task_failed_total"] >= 0
    assert correlation["user_visible_failures_total"] <= correlation["chat_failed_total"]
    assert len(correlation["recent_requests"]) <= 8
    assert len(correlation["recent_routes"]) <= 8
    assert len(correlation["recent_outcomes"]) <= 8
