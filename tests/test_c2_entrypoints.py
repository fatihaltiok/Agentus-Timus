"""C2 Entrypoint-Tests: HTTP-Endpoints und CLI.

Monkeypatcht die IO-Schicht — testet Import, Routing, Serialisierung
und Fehlerverhalten der neuen C2-Einstiegspunkte.
"""
from __future__ import annotations

import sys
from io import StringIO
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


# ---------------------------------------------------------------------------
# HTTP-Endpoint-Tests
# ---------------------------------------------------------------------------

@pytest.fixture()
def client():
    from fastapi.testclient import TestClient
    from server.mcp_server import app
    return TestClient(app, raise_server_exceptions=False)


def _fake_summary():
    return {
        "total_events": 3,
        "event_counts": {"chat_request_received": 1},
        "meta_diagnostics": {"dispatcher_meta_fallback_total": 0},
        "recipe_outcomes": {"total": 0},
        "runtime_gaps": {"total_insertions": 0},
        "self_hardening": {"total": 0},
        "request_correlation": {
            "chat_requests_total": 1,
            "chat_completed_total": 1,
            "chat_failed_total": 0,
            "dispatcher_routes_total": 1,
            "request_routes_total": 1,
            "task_routes_total": 0,
            "task_started_total": 0,
            "task_completed_total": 0,
            "task_failed_total": 0,
            "user_visible_failures_total": 0,
            "by_agent": {},
            "by_source": {},
            "by_error_class": {},
            "recent_requests": [],
            "recent_routes": [],
            "recent_outcomes": [],
            "recent_failures": [],
        },
        "user_impact": {
            "response_never_delivered_total": 0,
            "silent_failure_total": 0,
            "user_visible_timeout_total": 0,
            "misroute_recovered_total": 0,
            "recent_impacts": [],
        },
        "top_goal_signatures": [],
        "session": {},
        "window": {},
        "log_path": "/dev/null",
    }


def _fake_trace():
    return [
        {
            "id": "abc",
            "observed_at": "2026-04-05T10:00:00",
            "event_type": "chat_request_received",
            "payload": {"request_id": "req-test", "session_id": "s1", "source": "canvas_chat"},
        },
        {
            "id": "def",
            "observed_at": "2026-04-05T10:00:01",
            "event_type": "dispatcher_route_selected",
            "payload": {"request_id": "req-test", "agent": "meta", "decision_source": "llm"},
        },
    ]


def test_observation_endpoint_returns_success(client):
    with (
        patch("orchestration.autonomy_observation.build_autonomy_observation_summary", return_value=_fake_summary()),
        patch("orchestration.autonomy_observation.render_autonomy_observation_markdown", return_value="# Test\n"),
    ):
        resp = client.get("/autonomy/observation")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"
    assert "summary" in data
    assert "markdown" in data


def test_observation_endpoint_has_user_impact_block(client):
    with (
        patch("orchestration.autonomy_observation.build_autonomy_observation_summary", return_value=_fake_summary()),
        patch("orchestration.autonomy_observation.render_autonomy_observation_markdown", return_value="# Test\n"),
    ):
        resp = client.get("/autonomy/observation")
    ui = resp.json()["summary"]["user_impact"]
    assert "response_never_delivered_total" in ui
    assert "silent_failure_total" in ui
    assert "user_visible_timeout_total" in ui
    assert "misroute_recovered_total" in ui


def test_improvement_endpoint_returns_top_candidates(client):
    async def _fake_combined_candidates(self):
        return [
            {
                "candidate_id": "m12:1",
                "source": "self_improvement_engine",
                "category": "routing",
                "problem": "Routing schwach",
                "proposed_action": "Routing haerten",
                "status": "open",
                "priority_score": 1.1,
            }
        ]

    with patch(
        "orchestration.self_improvement_engine.get_improvement_engine",
        return_value=type(
            "_Engine",
            (),
            {
                "get_tool_stats": staticmethod(lambda days=7: [{"tool_name": "scan_ui"}]),
                "get_routing_stats": staticmethod(lambda days=7: {"total_decisions": 4}),
                "get_suggestions": staticmethod(
                    lambda applied=False: [
                        {"candidate_id": "m12:1", "severity": "high", "problem": "Routing schwach"}
                    ]
                ),
                "get_normalized_suggestions": staticmethod(
                    lambda applied=False: [
                        {
                            "candidate_id": "m12:1",
                            "source": "self_improvement_engine",
                            "category": "routing",
                            "problem": "Routing schwach",
                            "proposed_action": "Routing haerten",
                            "status": "open",
                        }
                    ]
                ),
            },
        )(),
    ), patch(
        "orchestration.session_reflection.SessionReflectionLoop.get_improvement_suggestions",
        _fake_combined_candidates,
    ), patch(
        "orchestration.improvement_task_autonomy.get_improvement_task_autonomy_settings",
        return_value={
            "enabled": True,
            "allow_self_modify": False,
            "max_autoenqueue": 1,
            "candidate_limit": 5,
        },
    ), patch(
        "orchestration.improvement_task_autonomy.build_improvement_task_governance_view",
        return_value={
            "rollout_guard_state": "verification_backpressure",
            "rollout_guard_blocked": True,
            "rollout_guard_reasons": ["verification_sample_total:3"],
            "shadowed_guard_states": ["strict_force_off"],
            "verification_backpressure": {
                "blocked": True,
                "active": True,
                "shadowed": False,
                "sample_total": 3,
                "negative_total": 3,
                "verified_rate": 0.0,
            },
        },
    ), patch(
        "orchestration.improvement_task_autonomy.get_improvement_task_rollout_guard",
        return_value={
            "state": "verification_backpressure",
            "blocked": True,
            "reasons": ["verification_sample_total:3"],
            "shadowed_guard_states": ["strict_force_off"],
            "verification_backpressure": {
                "blocked": True,
                "active": True,
                "shadowed": False,
                "sample_total": 3,
                "negative_total": 3,
                "verified_rate": 0.0,
            },
        },
    ), patch(
        "orchestration.autonomy_observation.build_autonomy_observation_summary",
        return_value={
            "improvement_runtime": {
                "execution_verified_total": 1,
                "verified_rate": 1.0,
                "not_verified_rate": 0.0,
            },
            "memory_curation_runtime": {
                "curation_completed_total": 2,
                "verification_pass_rate": 1.0,
            },
        },
    ):
        resp = client.get("/autonomy/improvement")

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"
    assert data["open_suggestions"] == 1
    assert data["candidate_count"] == 1
    assert data["top_candidates"][0]["candidate_id"] == "m12:1"
    assert data["top_candidates"][0]["problem"] == "Routing schwach"
    assert data["top_candidate_insights"][0]["candidate_id"] == "m12:1"
    assert "prio=" in data["top_candidate_insights"][0]["summary"]
    assert data["top_compiled_tasks"][0]["candidate_id"] == "m12:1"
    assert data["top_compiled_tasks"][0]["task_kind"] == "developer_task"
    assert data["top_task_promotion_decisions"][0]["candidate_id"] == "m12:1"
    assert data["top_task_promotion_decisions"][0]["requested_fix_mode"] == "developer_task"
    assert data["top_task_bridge_decisions"][0]["candidate_id"] == "m12:1"
    assert data["top_task_bridge_decisions"][0]["bridge_state"] == "not_e3_eligible"
    assert data["top_task_execution_candidates"][0]["candidate_id"] == "m12:1"
    assert data["top_task_execution_candidates"][0]["creation_state"] == "not_creatable"
    assert data["task_autonomy_settings"]["enabled"] is True
    assert data["improvement_governance"]["rollout_guard_state"] == "verification_backpressure"
    assert data["improvement_governance"]["rollout_guard_blocked"] is True
    assert data["improvement_governance"]["shadowed_guard_states"] == ["strict_force_off"]
    assert data["top_task_autonomy_decisions"][0]["candidate_id"] == "m12:1"
    assert data["top_task_autonomy_decisions"][0]["rollout_guard_state"] == "verification_backpressure"
    assert data["top_task_autonomy_decisions"][0]["shadowed_guard_states"] == ["strict_force_off"]
    assert data["top_task_autonomy_decisions"][0]["autoenqueue_state"] == "not_creatable"
    assert data["improvement_runtime"]["execution_verified_total"] == 1
    assert data["improvement_runtime"]["verified_rate"] == 1.0
    assert data["memory_curation_runtime"]["curation_completed_total"] == 2
    assert data["memory_curation_runtime"]["verification_pass_rate"] == 1.0


def test_memory_curation_endpoint_returns_governance_and_metrics(client):
    with patch(
        "orchestration.autonomy_observation.build_autonomy_observation_summary",
        return_value={
            "memory_curation_runtime": {
                "autonomy_completed_total": 3,
                "verification_pass_rate": 1.0,
            }
        },
    ), patch(
        "orchestration.task_queue.get_queue",
        return_value=type("_Queue", (), {})(),
    ), patch(
        "orchestration.memory_curation.get_memory_curation_autonomy_settings",
        return_value={
            "enabled": True,
            "interval_heartbeats": 12,
            "max_actions": 1,
            "allowed_actions": ["summarize", "archive", "devalue"],
        },
    ), patch(
        "orchestration.memory_curation.get_memory_curation_status",
        return_value={
            "status": "ok",
            "current_metrics": {
                "active_items": 12,
                "archived_items": 4,
                "summary_items": 2,
            },
            "last_snapshots": [{"snapshot_id": "snap-m1", "status": "completed"}],
            "pending_candidates": [{"candidate_id": "mc:1", "action": "summarize"}],
            "pending_retrieval_probes": [{"probe_id": "probe-m1", "query": "robotik safety"}],
            "latest_retrieval_quality": {
                "verdict": {"passed": True, "reason": "retrieval_quality_stable"},
            },
            "quality_governance": {
                "state": "allow",
                "blocked": False,
                "summary": {"evaluated_runs": 3, "pass_rate": 1.0},
            },
            "autonomy_settings": {
                "enabled": True,
                "interval_heartbeats": 12,
                "max_actions": 1,
            },
            "autonomy_governance": {
                "state": "cooldown_active",
                "blocked": True,
                "reasons": ["recent_memory_curation_run"],
                "filtered_candidate_count": 1,
                "cooldown_until": "2026-04-15T10:00:00",
            },
        },
    ):
        resp = client.get("/autonomy/memory_curation")

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"
    assert data["memory_curation"]["status"] == "ok"
    assert data["autonomy_settings"]["enabled"] is True
    assert data["autonomy_governance"]["state"] == "cooldown_active"
    assert data["current_metrics"]["summary_items"] == 2
    assert data["last_snapshots"][0]["snapshot_id"] == "snap-m1"
    assert data["pending_candidates"][0]["candidate_id"] == "mc:1"
    assert data["pending_retrieval_probes"][0]["probe_id"] == "probe-m1"
    assert data["latest_retrieval_quality"]["verdict"]["passed"] is True
    assert data["quality_governance"]["state"] == "allow"
    assert data["memory_curation_runtime"]["autonomy_completed_total"] == 3
    assert data["memory_curation"]["quality_governance"]["summary"]["evaluated_runs"] == 3


def test_operator_snapshot_endpoint_returns_unified_view(client):
    async def _fake_snapshot(limit: int = 5):
        return {
            "generated_at": "2026-04-16T00:40:00+02:00",
            "summary": {
                "blocked_lane_count": 1,
                "blocked_lanes": ["memory_curation"],
            },
            "system": {
                "state": "healthy",
            },
            "lanes": {
                "improvement": {"state": "allow", "blocked": False},
                "memory_curation": {"state": "cooldown_active", "blocked": True},
            },
        }

    with patch(
        "orchestration.phase_e_operator_snapshot.collect_phase_e_operator_snapshot",
        _fake_snapshot,
    ):
        resp = client.get("/autonomy/operator_snapshot?limit=4")

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"
    assert data["summary"]["blocked_lane_count"] == 1
    assert data["system"]["state"] == "healthy"
    assert data["lanes"]["improvement"]["state"] == "allow"
    assert data["lanes"]["memory_curation"]["blocked"] is True


def test_incident_trace_endpoint_returns_trace(client):
    with patch("orchestration.autonomy_observation.get_incident_trace", return_value=_fake_trace()):
        resp = client.get("/autonomy/incident/req-test")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"
    assert data["request_id"] == "req-test"
    assert data["event_count"] == 2
    assert len(data["trace"]) == 2


def test_incident_trace_endpoint_empty_trace(client):
    with patch("orchestration.autonomy_observation.get_incident_trace", return_value=[]):
        resp = client.get("/autonomy/incident/req-unknown")
    assert resp.status_code == 200
    data = resp.json()
    assert data["event_count"] == 0
    assert data["trace"] == []


def test_incident_trace_endpoint_error_returns_500(client):
    with patch("orchestration.autonomy_observation.get_incident_trace", side_effect=RuntimeError("boom")):
        resp = client.get("/autonomy/incident/req-x")
    assert resp.status_code == 500
    assert resp.json()["status"] == "error"


# ---------------------------------------------------------------------------
# CLI-Tests
# ---------------------------------------------------------------------------

def test_cli_normal_mode_prints_markdown(capsys):
    with (
        patch("orchestration.autonomy_observation.build_autonomy_observation_summary", return_value=_fake_summary()),
        patch("orchestration.autonomy_observation.render_autonomy_observation_markdown", return_value="# Observation\n"),
        patch("sys.argv", ["evaluate_autonomy_observation.py"]),
    ):
        from scripts.evaluate_autonomy_observation import main
        rc = main()
    assert rc == 0
    captured = capsys.readouterr()
    assert "Observation" in captured.out


def test_cli_request_id_mode_shows_trace(capsys):
    with (
        patch("scripts.evaluate_autonomy_observation.get_incident_trace", return_value=_fake_trace()),
        patch("sys.argv", ["evaluate_autonomy_observation.py", "--request-id", "req-test"]),
    ):
        from scripts.evaluate_autonomy_observation import main
        rc = main()
    assert rc == 0
    captured = capsys.readouterr()
    assert "req-test" in captured.out
    assert "chat_request_received" in captured.out
    assert "dispatcher_route_selected" in captured.out


def test_cli_request_id_empty_trace(capsys):
    with (
        patch("scripts.evaluate_autonomy_observation.get_incident_trace", return_value=[]),
        patch("sys.argv", ["evaluate_autonomy_observation.py", "--request-id", "req-none"]),
    ):
        from scripts.evaluate_autonomy_observation import main
        rc = main()
    assert rc == 0
    captured = capsys.readouterr()
    assert "Keine Events" in captured.out


def test_cli_output_writes_file(tmp_path, capsys):
    out_file = tmp_path / "trace.md"
    with (
        patch("scripts.evaluate_autonomy_observation.get_incident_trace", return_value=_fake_trace()),
        patch("sys.argv", ["evaluate_autonomy_observation.py", "--request-id", "req-test", "--output", str(out_file)]),
    ):
        from scripts.evaluate_autonomy_observation import main
        main()
    assert out_file.exists()
    content = out_file.read_text()
    assert "req-test" in content


def test_cli_trace_includes_all_correlation_fields(capsys):
    """Trace-Ausgabe enthält task_id, session_id, incident_key, route_source."""
    rich_trace = [
        {
            "id": "x",
            "observed_at": "2026-04-05T10:00:00",
            "event_type": "task_execution_started",
            "payload": {
                "request_id": "req-1",
                "task_id": "task-abc",
                "session_id": "sess-xyz",
                "incident_key": "inc-001",
                "route_source": "dispatcher",
                "agent": "research",
                "source": "autonomous_runner",
            },
        }
    ]
    with (
        patch("scripts.evaluate_autonomy_observation.get_incident_trace", return_value=rich_trace),
        patch("sys.argv", ["evaluate_autonomy_observation.py", "--request-id", "req-1"]),
    ):
        from scripts.evaluate_autonomy_observation import main
        main()
    captured = capsys.readouterr()
    assert "task_id" in captured.out
    assert "task-abc" in captured.out
    assert "session_id" in captured.out
    assert "incident_key" in captured.out
    assert "route_source" in captured.out


# ---------------------------------------------------------------------------
# build_incident_trace — Zeitordnung mit gemischten ISO-Formaten
# ---------------------------------------------------------------------------

def test_trace_offset_ahead_sorts_by_utc_not_wall_clock():
    """Echter Gegenbeispiel-Test: 10:00+02:00 (= 08:00 UTC) muss VOR 08:30Z (= 08:30 UTC) stehen.
    dt.replace(tzinfo=None) würde 10:00 > 08:30 liefern und die Reihenfolge umkehren.
    dt.astimezone(utc).replace(tzinfo=None) liefert korrekt 08:00 < 08:30.
    """
    from orchestration.autonomy_observation import build_incident_trace
    events = [
        # Wall clock 08:30, UTC 08:30 — soll an zweiter Stelle stehen
        {"id": "later", "observed_at": "2026-04-05T08:30:00Z", "event_type": "second",
         "payload": {"request_id": "req-1"}},
        # Wall clock 10:00, UTC 08:00 — soll an erster Stelle stehen
        {"id": "earlier", "observed_at": "2026-04-05T10:00:00+02:00", "event_type": "first",
         "payload": {"request_id": "req-1"}},
    ]
    trace = build_incident_trace(events, "req-1")
    assert [e["event_type"] for e in trace] == ["first", "second"], (
        "10:00+02:00 (= 08:00 UTC) muss vor 08:30Z (= 08:30 UTC) stehen"
    )


def test_trace_negative_offset_sorts_correctly():
    """Negativer Offset: 06:00-02:00 (= 08:00 UTC) muss VOR 09:00+00:00 (= 09:00 UTC) stehen."""
    from orchestration.autonomy_observation import build_incident_trace
    events = [
        {"id": "b", "observed_at": "2026-04-05T09:00:00+00:00", "event_type": "second",
         "payload": {"request_id": "req-x"}},
        {"id": "a", "observed_at": "2026-04-05T06:00:00-02:00", "event_type": "first",
         "payload": {"request_id": "req-x"}},
    ]
    trace = build_incident_trace(events, "req-x")
    assert [e["event_type"] for e in trace] == ["first", "second"], (
        "06:00-02:00 (= 08:00 UTC) muss vor 09:00+00:00 (= 09:00 UTC) stehen"
    )


def test_trace_same_utc_different_offsets_stable():
    """Zwei Timestamps die denselben UTC-Instant darstellen: keine Exception, stabile Ordnung."""
    from orchestration.autonomy_observation import build_incident_trace
    events = [
        {"id": "x", "observed_at": "2026-04-05T10:00:00+02:00", "event_type": "plus2",
         "payload": {"request_id": "req-y"}},
        {"id": "y", "observed_at": "2026-04-05T08:00:00Z", "event_type": "utc",
         "payload": {"request_id": "req-y"}},
    ]
    trace = build_incident_trace(events, "req-y")
    assert len(trace) == 2
    # Beide repräsentieren 08:00 UTC — Reihenfolge stabil (nicht crashen)


def test_trace_aware_before_naive_when_utc_earlier():
    """Aware 08:00+00:00 (= 08:00 UTC) soll vor naivem 09:00 kommen."""
    from orchestration.autonomy_observation import build_incident_trace
    events = [
        {"id": "b", "observed_at": "2026-04-05T09:00:00", "event_type": "naive_later",
         "payload": {"request_id": "req-z"}},
        {"id": "a", "observed_at": "2026-04-05T08:00:00+00:00", "event_type": "aware_earlier",
         "payload": {"request_id": "req-z"}},
    ]
    trace = build_incident_trace(events, "req-z")
    assert trace[0]["event_type"] == "aware_earlier"


def test_trace_unparseable_timestamp_sorts_first():
    from orchestration.autonomy_observation import build_incident_trace
    events = [
        {"id": "b", "observed_at": "2026-04-05T10:00:00", "event_type": "valid",
         "payload": {"request_id": "req-1"}},
        {"id": "a", "observed_at": "not-a-date", "event_type": "broken",
         "payload": {"request_id": "req-1"}},
    ]
    trace = build_incident_trace(events, "req-1")
    # kaputte Zeitstempel landen vorne (datetime.min Fallback), kein Crash
    assert len(trace) == 2
    assert trace[0]["event_type"] == "broken"


def test_trace_same_timestamp_stable_order():
    from orchestration.autonomy_observation import build_incident_trace
    ts = "2026-04-05T10:00:00"
    events = [
        {"id": str(i), "observed_at": ts, "event_type": f"e{i}",
         "payload": {"request_id": "req-1"}}
        for i in range(5)
    ]
    trace = build_incident_trace(events, "req-1")
    # Gleiche Zeitstempel: stabile Sortierung, alle Events vorhanden
    assert len(trace) == 5
