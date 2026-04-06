"""Contract tests for the C4 long-run transport event schema."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def test_progress_event_has_stable_envelope():
    from orchestration.longrunner_transport import SCHEMA_VERSION, make_progress_event

    event = make_progress_event(
        request_id="req-1",
        run_id="run-1",
        session_id="sess-1",
        agent="research",
        stage="searching_sources",
        seq=3,
        message="Suche Quellen.",
        progress_hint="started",
        next_expected_update_s=12,
    )

    payload = event.to_dict()
    assert payload["schema_version"] == SCHEMA_VERSION
    assert payload["type"] == "progress"
    assert payload["request_id"] == "req-1"
    assert payload["run_id"] == "run-1"
    assert payload["agent"] == "research"
    assert payload["stage"] == "searching_sources"
    assert payload["seq"] == 3
    assert payload["message"] == "Suche Quellen."
    assert payload["progress_hint"] == "started"
    assert payload["next_expected_update_s"] == 12
    assert payload["ts"].endswith("Z")


def test_validate_transport_event_rejects_unknown_type():
    from orchestration.longrunner_transport import validate_transport_event

    with pytest.raises(ValueError, match="unsupported_longrun_event_type"):
        validate_transport_event(
            {
                "type": "unknown",
                "request_id": "req-1",
                "run_id": "run-1",
                "session_id": "sess-1",
                "agent": "executor",
                "stage": "x",
                "seq": 1,
                "message": "Hallo",
            }
        )


def test_blocker_requires_reason_and_preserves_user_action():
    from orchestration.longrunner_transport import make_blocker_event

    event = make_blocker_event(
        request_id="req-2",
        run_id="run-2",
        session_id="sess-2",
        agent="executor",
        stage="auth_wall",
        seq=4,
        message="Login erforderlich.",
        blocker_reason="auth_required",
        user_action_required="Bitte bestaetige den Zugriff.",
    )

    payload = event.to_dict()
    assert payload["type"] == "blocker"
    assert payload["blocker_reason"] == "auth_required"
    assert payload["user_action_required"] == "Bitte bestaetige den Zugriff."


def test_partial_result_requires_preview_and_is_not_terminal():
    from orchestration.longrunner_transport import (
        is_terminal_event_type,
        make_partial_result_event,
    )

    event = make_partial_result_event(
        request_id="req-3",
        run_id="run-3",
        session_id="sess-3",
        agent="research",
        stage="first_findings",
        seq=5,
        message="Erste Ergebnisse liegen vor.",
        content_preview="Drei Quellen sind schon ausgewertet.",
    )

    assert event.is_final is False
    assert is_terminal_event_type(event.type) is False


def test_run_failed_requires_error_metadata():
    from orchestration.longrunner_transport import make_run_failed_event

    with pytest.raises(ValueError, match="run_failed_requires_error_metadata"):
        make_run_failed_event(
            request_id="req-4",
            run_id="run-4",
            session_id="sess-4",
            agent="research",
            stage="failed",
            seq=6,
            message="Lauf fehlgeschlagen.",
        )


def test_run_ids_use_stable_prefix():
    from orchestration.longrunner_transport import new_run_id

    run_id = new_run_id()
    assert run_id.startswith("run_")
    assert len(run_id) > 8
