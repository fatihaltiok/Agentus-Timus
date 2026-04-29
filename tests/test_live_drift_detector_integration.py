from __future__ import annotations

from server import mcp_server


def test_record_live_drift_observations_emits_diagnostic_event(monkeypatch) -> None:
    observed: list[tuple[str, dict]] = []

    monkeypatch.setattr(
        mcp_server,
        "_record_chat_observation",
        lambda event_type, payload: observed.append((event_type, dict(payload))),
    )

    mcp_server._record_live_drift_observations(
        request_id="req-e1",
        session_id="sess-e1",
        query="erstelle die pdf aus /tmp/test.odt",
        reply="Der Interaktionsmodus blockiert jede Ausfuehrung.",
        agent="meta",
        followup_capsule={},
        meta_classification={"response_mode": "execute", "dominant_turn_type": "new_task"},
    )

    drift_events = [payload for event_type, payload in observed if event_type == "live_drift_detected"]
    assert drift_events
    assert drift_events[0]["drift_type"] == "execute_blocked_by_mode"
    assert drift_events[0]["request_id"] == "req-e1"
    assert drift_events[0]["session_id"] == "sess-e1"
    assert drift_events[0]["recommended_action"]


def test_record_live_drift_observations_is_best_effort(monkeypatch) -> None:
    def _raise(*args, **kwargs):
        raise RuntimeError("observation backend down")

    monkeypatch.setattr(mcp_server, "_record_chat_observation", _raise)

    mcp_server._record_live_drift_observations(
        request_id="req-e1",
        session_id="sess-e1",
        query="erstelle die pdf aus /tmp/test.odt",
        reply="Der Interaktionsmodus blockiert jede Ausfuehrung.",
        agent="meta",
        followup_capsule={},
        meta_classification={"response_mode": "execute"},
    )
