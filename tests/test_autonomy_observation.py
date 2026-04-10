from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

import orchestration.autonomy_observation as autonomy_observation
from orchestration.autonomy_observation import AutonomyObservationStore, render_autonomy_observation_markdown


def test_autonomy_observation_store_records_and_summarizes_week_window(tmp_path: Path) -> None:
    base = datetime.now().astimezone().replace(microsecond=0)
    started_at = (base - timedelta(days=1)).isoformat()
    event_one = (base - timedelta(hours=23, minutes=55)).isoformat()
    event_two = (base - timedelta(hours=23, minutes=54, seconds=59)).isoformat()
    event_three = (base - timedelta(hours=23)).isoformat()
    event_four = (base - timedelta(hours=22, minutes=55)).isoformat()
    event_five = (base - timedelta(hours=22, minutes=54, seconds=50)).isoformat()
    event_six = (base - timedelta(hours=22, minutes=54, seconds=40)).isoformat()
    event_seven = (base - timedelta(hours=22, minutes=54, seconds=39)).isoformat()
    event_eight = (base - timedelta(hours=22, minutes=54, seconds=38)).isoformat()
    event_nine = (base - timedelta(hours=22, minutes=54, seconds=37)).isoformat()
    event_ten = (base - timedelta(hours=22, minutes=54, seconds=36)).isoformat()
    event_eleven = (base - timedelta(hours=22, minutes=54, seconds=35)).isoformat()
    event_twelve = (base - timedelta(hours=22, minutes=54, seconds=34)).isoformat()

    store = AutonomyObservationStore(
        log_path=tmp_path / "autonomy_observation.jsonl",
        state_path=tmp_path / "autonomy_observation_state.json",
    )
    state = store.start_session(label="week-1", duration_days=7, started_at=started_at)

    assert state["label"] == "week-1"
    assert state["active"] is True

    assert store.record_event(
        "meta_recipe_outcome",
        {
            "goal_signature": "pricing|live|light|table|none|loc=0|deliver=0",
            "task_type": "simple_live_lookup_document",
            "recipe_id": "simple_live_lookup_document",
            "success": True,
            "duration_ms": 1800,
            "planner_resolution_state": "adopted",
            "runtime_gap_insertions": ["runtime_goal_gap_document"],
        },
        observed_at=event_one,
    )
    assert store.record_event(
        "runtime_goal_gap_inserted",
        {
            "goal_signature": "pricing|live|light|table|none|loc=0|deliver=0",
            "adaptive_reason": "runtime_goal_gap_document",
            "agent": "document",
            "stage_id": "document_output",
        },
        observed_at=event_two,
    )
    assert store.record_event(
        "self_hardening_runtime_event",
        {
            "stage": "self_modify_finished",
            "status": "success",
            "pattern_name": "lookup_followup_context_loss",
            "route_target": "self_modify",
            "verification_status": "verified",
        },
        observed_at=event_three,
    )
    assert store.record_event(
        "dispatcher_meta_fallback",
        {
            "reason": "uncertain_decision",
            "query_preview": "welches land passt zu meinen faehigkeiten",
        },
        observed_at=event_four,
    )
    assert store.record_event(
        "meta_direct_tool_call",
        {
            "method": "search_web",
            "status": "error",
            "has_error": True,
            "error": "Timeout",
        },
        observed_at=event_five,
    )
    assert store.record_event(
        "lead_diagnosis_selected",
        {
            "source_agent": "system",
            "evidence_level": "verified",
            "verified_paths_count": 1,
            "verified_functions_count": 1,
        },
        observed_at=event_six,
    )
    assert store.record_event(
        "diagnosis_conflict_detected",
        {
            "supporting_count": 1,
            "lead_source_agent": "system",
        },
        observed_at=event_seven,
    )
    assert store.record_event(
        "developer_task_compiled",
        {
            "verified_paths_count": 1,
            "verified_functions_count": 1,
            "suppressed_claims_count": 1,
        },
        observed_at=event_eight,
    )
    assert store.record_event(
        "unverified_claim_suppressed",
        {
            "suppressed_claims_count": 2,
        },
        observed_at=event_nine,
    )
    assert store.record_event(
        "primary_fix_task_emitted",
        {
            "change_type": "type_normalization",
            "verified_paths_count": 1,
        },
        observed_at=event_ten,
    )
    assert store.record_event(
        "followup_task_deferred",
        {
            "followup_tasks_count": 2,
        },
        observed_at=event_eleven,
    )
    assert store.record_event(
        "root_cause_gate_blocked",
        {
            "gate_reason": "missing_verified_paths",
        },
        observed_at=event_twelve,
    )
    assert store.record_event(
        "task_mix_suppressed",
        {
            "task_mix_suppressed_count": 1,
        },
        observed_at=(base - timedelta(hours=22, minutes=54, seconds=33)).isoformat(),
    )

    summary = store.build_summary()

    assert summary["total_events"] == 14
    assert summary["event_counts"]["observation_started"] == 1
    assert summary["event_counts"]["meta_recipe_outcome"] == 1
    assert summary["recipe_outcomes"]["success_total"] == 1
    assert summary["recipe_outcomes"]["planner_adopted_total"] == 1
    assert summary["runtime_gaps"]["by_reason"]["runtime_goal_gap_document"] == 1
    assert summary["self_hardening"]["self_modify_success_total"] == 1
    assert summary["meta_diagnostics"]["dispatcher_meta_fallback_total"] == 1
    assert summary["meta_diagnostics"]["direct_tool_calls_total"] == 1
    assert summary["meta_diagnostics"]["direct_tool_errors_total"] == 1
    assert summary["meta_diagnostics"]["lead_diagnosis_selected_total"] == 1
    assert summary["meta_diagnostics"]["diagnosis_conflicts_total"] == 1
    assert summary["meta_diagnostics"]["developer_tasks_compiled_total"] == 1
    assert summary["meta_diagnostics"]["unverified_claims_suppressed_total"] == 2
    assert summary["meta_diagnostics"]["primary_fix_tasks_total"] == 1
    assert summary["meta_diagnostics"]["followup_tasks_deferred_total"] == 2
    assert summary["meta_diagnostics"]["root_cause_gate_blocked_total"] == 1
    assert summary["meta_diagnostics"]["task_mix_suppressed_total"] == 1
    assert summary["top_goal_signatures"][0]["goal_signature"] == "pricing|live|light|table|none|loc=0|deliver=0"

    markdown = render_autonomy_observation_markdown(summary)
    assert "# Timus Autonomy Observation" in markdown
    assert "runtime_goal_gap_document" in markdown
    assert "Dispatcher -> Meta Fallbacks" in markdown
    assert "Lead-Diagnosen gewaehlt" in markdown
    assert "Primary-Fix-Tasks emittiert" in markdown


def test_record_autonomy_observation_skips_default_pytest_writes(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("AUTONOMY_OBSERVATION_ENABLED", "true")
    monkeypatch.setenv("PYTEST_CURRENT_TEST", "tests/test_autonomy_observation.py::test_record_autonomy_observation_skips_default_pytest_writes")
    monkeypatch.delenv("AUTONOMY_OBSERVATION_ALLOW_TEST_WRITES", raising=False)
    monkeypatch.delenv("AUTONOMY_OBSERVATION_LOG_PATH", raising=False)
    monkeypatch.delenv("AUTONOMY_OBSERVATION_STATE_PATH", raising=False)
    monkeypatch.setattr(autonomy_observation, "_AUTONOMY_OBSERVATION_STORE", None)

    result = autonomy_observation.record_autonomy_observation(
        "dispatcher_meta_fallback",
        {"reason": "empty_decision", "query_preview": "test"},
    )

    assert result is False
    assert not (tmp_path / "autonomy_observation.jsonl").exists()


def test_record_autonomy_observation_allows_test_writes_with_explicit_tmp_paths(monkeypatch, tmp_path: Path) -> None:
    log_path = tmp_path / "autonomy_observation.jsonl"
    state_path = tmp_path / "autonomy_observation_state.json"
    monkeypatch.setenv("AUTONOMY_OBSERVATION_ENABLED", "true")
    monkeypatch.setenv("PYTEST_CURRENT_TEST", "tests/test_autonomy_observation.py::test_record_autonomy_observation_allows_test_writes_with_explicit_tmp_paths")
    monkeypatch.delenv("AUTONOMY_OBSERVATION_ALLOW_TEST_WRITES", raising=False)
    monkeypatch.setenv("AUTONOMY_OBSERVATION_LOG_PATH", str(log_path))
    monkeypatch.setenv("AUTONOMY_OBSERVATION_STATE_PATH", str(state_path))
    monkeypatch.setattr(autonomy_observation, "_AUTONOMY_OBSERVATION_STORE", None)
    autonomy_observation.start_autonomy_observation(label="pytest-observation", duration_days=1)

    result = autonomy_observation.record_autonomy_observation(
        "dispatcher_meta_fallback",
        {"reason": "empty_decision", "query_preview": "test"},
    )

    assert result is True
    assert log_path.exists()


def test_open_ended_autonomy_observation_session_stays_active(tmp_path: Path) -> None:
    observed_at = datetime.now().astimezone().replace(microsecond=0).isoformat()

    store = AutonomyObservationStore(
        log_path=tmp_path / "autonomy_observation.jsonl",
        state_path=tmp_path / "autonomy_observation_state.json",
    )

    state = store.start_session(
        label="open-ended",
        duration_days=0,
        started_at="2026-04-03T21:44:45+02:00",
    )

    assert state["active"] is True
    assert state["ends_at"] == ""
    assert state["duration_days"] == 0

    loaded = store.load_state()
    assert loaded["active"] is True
    assert loaded["ends_at"] == ""
    assert loaded["duration_days"] == 0

    assert store.record_event(
        "dispatcher_meta_fallback",
        {"reason": "empty_decision", "query_preview": "raeum auf"},
        observed_at=observed_at,
    )

    summary = store.build_summary()
    assert summary["event_counts"]["observation_started"] == 1
    assert summary["event_counts"]["dispatcher_meta_fallback"] == 1


def test_autonomy_observation_summarizes_request_and_task_correlation(tmp_path: Path) -> None:
    base = datetime.now().astimezone().replace(microsecond=0)
    store = AutonomyObservationStore(
        log_path=tmp_path / "autonomy_observation.jsonl",
        state_path=tmp_path / "autonomy_observation_state.json",
    )
    store.start_session(label="c2-correlation", duration_days=1, started_at=(base - timedelta(minutes=5)).isoformat())

    assert store.record_event(
        "chat_request_received",
        {
            "request_id": "req-1",
            "session_id": "canvas_demo",
            "source": "canvas_chat",
            "query_preview": "pruefe das video",
        },
        observed_at=(base - timedelta(minutes=4, seconds=50)).isoformat(),
    )
    assert store.record_event(
        "dispatcher_route_selected",
        {
            "session_id": "canvas_demo",
            "source": "dispatcher",
            "agent": "meta",
            "decision_source": "llm_exact",
            "query_preview": "pruefe das video",
        },
        observed_at=(base - timedelta(minutes=4, seconds=49)).isoformat(),
    )
    assert store.record_event(
        "request_route_selected",
        {
            "request_id": "req-1",
            "session_id": "canvas_demo",
            "source": "canvas_chat",
            "agent": "meta",
            "route_source": "dispatcher",
        },
        observed_at=(base - timedelta(minutes=4, seconds=48)).isoformat(),
    )
    assert store.record_event(
        "chat_request_failed",
        {
            "request_id": "req-1",
            "session_id": "canvas_demo",
            "source": "canvas_chat",
            "agent": "meta",
            "error_class": "canvas_chat_exception",
            "error": "provider down",
            "query_preview": "pruefe das video",
        },
        observed_at=(base - timedelta(minutes=4, seconds=47)).isoformat(),
    )
    assert store.record_event(
        "task_execution_started",
        {
            "task_id": "task-1",
            "session_id": "auto_1234",
            "source": "autonomous_runner",
            "agent": "",
            "description_preview": "bearbeite den incident task",
        },
        observed_at=(base - timedelta(minutes=3)).isoformat(),
    )
    assert store.record_event(
        "task_route_selected",
        {
            "task_id": "task-1",
            "session_id": "auto_1234",
            "source": "autonomous_runner",
            "agent": "research",
            "route_source": "dispatcher",
            "incident_key": "m3_mcp_health_unavailable",
        },
        observed_at=(base - timedelta(minutes=2, seconds=58)).isoformat(),
    )
    assert store.record_event(
        "task_execution_failed",
        {
            "task_id": "task-1",
            "session_id": "auto_1234",
            "source": "autonomous_runner",
            "agent": "research",
            "incident_key": "m3_mcp_health_unavailable",
            "error_class": "task_exception",
            "error": "timeout",
            "description_preview": "bearbeite den incident task",
        },
        observed_at=(base - timedelta(minutes=2, seconds=57)).isoformat(),
    )
    assert store.record_event(
        "communication_task_started",
        {
            "request_id": "req-2",
            "session_id": "tg_demo",
            "source": "telegram_chat",
            "agent": "communication",
            "channel": "email",
            "backend": "resend",
            "recipient": "fatihaltiok@outlook.com",
        },
        observed_at=(base - timedelta(minutes=1, seconds=30)).isoformat(),
    )
    assert store.record_event(
        "send_email_succeeded",
        {
            "request_id": "req-2",
            "session_id": "tg_demo",
            "source": "telegram_chat",
            "agent": "communication",
            "channel": "email",
            "backend": "resend",
            "recipient": "fatihaltiok@outlook.com",
        },
        observed_at=(base - timedelta(minutes=1, seconds=28)).isoformat(),
    )
    assert store.record_event(
        "send_email_failed",
        {
            "request_id": "req-3",
            "session_id": "canvas_demo",
            "source": "canvas_chat",
            "agent": "communication",
            "channel": "email",
            "backend": "smtp",
            "recipient": "fatihaltiok@outlook.com",
            "error": "smtp down",
        },
        observed_at=(base - timedelta(minutes=1, seconds=25)).isoformat(),
    )

    summary = store.build_summary()

    correlation = summary["request_correlation"]
    communication = summary["communication_runtime"]
    assert correlation["chat_requests_total"] == 1
    assert correlation["chat_failed_total"] == 1
    assert correlation["dispatcher_routes_total"] == 1
    assert correlation["request_routes_total"] == 1
    assert correlation["task_routes_total"] == 1
    assert correlation["task_started_total"] == 1
    assert correlation["task_failed_total"] == 1
    assert correlation["user_visible_failures_total"] == 1
    assert correlation["by_agent"]["meta"] >= 1
    assert correlation["by_agent"]["research"] >= 1
    assert correlation["by_source"]["canvas_chat"] >= 1
    assert correlation["by_source"]["autonomous_runner"] >= 1
    assert correlation["by_error_class"]["canvas_chat_exception"] == 1
    assert correlation["by_error_class"]["task_exception"] == 1
    assert correlation["recent_requests"][0]["request_id"] == "req-1"
    assert correlation["recent_requests"][0]["source"] == "canvas_chat"
    assert correlation["recent_routes"][0]["event_type"] == "task_route_selected"
    assert correlation["recent_routes"][0]["agent"] == "research"
    assert correlation["recent_outcomes"][0]["event_type"] == "task_execution_failed"
    assert correlation["recent_outcomes"][1]["event_type"] == "chat_request_failed"
    assert correlation["recent_failures"][0]["event_type"] == "task_execution_failed"
    assert correlation["recent_failures"][1]["event_type"] == "chat_request_failed"
    assert communication["tasks_started_total"] == 1
    assert communication["email_send_success_total"] == 1
    assert communication["email_send_failed_total"] == 1
    assert communication["by_backend"]["resend"] == 2
    assert communication["by_backend"]["smtp"] == 1
    assert communication["by_channel"]["email"] == 3

    markdown = render_autonomy_observation_markdown(summary)
    assert "## Communication Runtime" in markdown
    assert "E-Mail-Versand Erfolg" in markdown
    assert "Mail-Backend `resend`" in markdown
    assert "## Request-Korrelation" in markdown
    assert "## Letzte korrelierte Fehler" in markdown
    assert "canvas_chat_exception" in markdown


def test_autonomy_observation_summarizes_challenge_runtime(tmp_path: Path) -> None:
    base = datetime.now().astimezone().replace(microsecond=0)
    store = AutonomyObservationStore(
        log_path=tmp_path / "autonomy_observation.jsonl",
        state_path=tmp_path / "autonomy_observation_state.json",
    )
    store.start_session(label="d5-challenge", duration_days=1, started_at=(base - timedelta(minutes=5)).isoformat())

    assert store.record_event(
        "challenge_required",
        {
            "request_id": "req_c1",
            "session_id": "sess_c",
            "service": "github",
            "challenge_type": "2fa",
        },
        observed_at=(base - timedelta(minutes=4)).isoformat(),
    )
    assert store.record_event(
        "challenge_resume",
        {
            "request_id": "req_c2",
            "session_id": "sess_c",
            "service": "github",
            "challenge_type": "2fa",
            "reply_kind": "challenge_resolved",
        },
        observed_at=(base - timedelta(minutes=3)).isoformat(),
    )
    assert store.record_event(
        "challenge_reblocked",
        {
            "request_id": "req_c3",
            "session_id": "sess_c",
            "service": "github",
            "challenge_type": "2fa",
            "reply_kind": "challenge_resolved",
        },
        observed_at=(base - timedelta(minutes=2)).isoformat(),
    )
    assert store.record_event(
        "challenge_resolved",
        {
            "request_id": "req_c4",
            "session_id": "sess_c",
            "service": "github",
            "challenge_type": "2fa",
            "reply_kind": "challenge_resolved",
        },
        observed_at=(base - timedelta(minutes=1)).isoformat(),
    )

    summary = store.build_summary()

    challenge = summary["challenge_runtime"]
    assert challenge["challenge_required_total"] == 1
    assert challenge["challenge_resume_total"] == 1
    assert challenge["challenge_resolved_total"] == 1
    assert challenge["challenge_reblocked_total"] == 1
    assert challenge["resolution_rate"] == 1.0
    assert challenge["reblock_rate"] == 1.0
    assert challenge["by_service"]["github"] == 4
    assert challenge["by_challenge_type"]["2fa"] == 4
    assert challenge["by_reply_kind"]["challenge_resolved"] == 3

    markdown = render_autonomy_observation_markdown(summary)
    assert "## Challenge Runtime" in markdown
    assert "Challenge aufgeloest" in markdown
    assert "Challenge-Typ `2fa`" in markdown
