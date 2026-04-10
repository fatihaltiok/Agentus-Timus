from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def test_pending_workflow_state_normalizes_auth_required_payload():
    from orchestration.pending_workflow_state import normalize_pending_workflow_state

    state = normalize_pending_workflow_state(
        {
            "status": "auth_required",
            "platform": "twitter",
            "message": "X/Twitter verlangt Login.",
            "user_action_required": "Bitte bestaetige den Login.",
        },
        updated_at="2026-04-09T10:00:00Z",
        source_agent="executor",
        source_stage="user_action_required",
    )

    assert state is not None
    assert state.status == "auth_required"
    assert state.service == "x"
    assert state.source_agent == "executor"
    assert state.source_stage == "user_action_required"
    assert state.workflow_id.startswith("wf_")


def test_pending_workflow_state_rejects_non_pending_status():
    from orchestration.pending_workflow_state import normalize_pending_workflow_state

    assert normalize_pending_workflow_state({"status": "completed"}) is None


def test_classify_pending_workflow_reply_detects_login_resume():
    from orchestration.pending_workflow_state import classify_pending_workflow_reply

    result = classify_pending_workflow_reply(
        "ich bin eingeloggt",
        {
            "status": "awaiting_user",
            "reason": "user_mediated_login",
            "source_agent": "visual",
        },
    )

    assert result["reply_kind"] == "resume_requested"
    assert result["status"] == "awaiting_user"
    assert result["source_agent"] == "visual"


def test_classify_pending_workflow_reply_detects_challenge_update():
    from orchestration.pending_workflow_state import classify_pending_workflow_reply

    result = classify_pending_workflow_reply(
        "ich sehe jetzt eine 2fa challenge",
        {
            "status": "awaiting_user",
            "reason": "user_mediated_login",
            "source_agent": "visual",
        },
    )

    assert result["reply_kind"] == "challenge_present"


def test_classify_pending_workflow_reply_detects_challenge_resolved():
    from orchestration.pending_workflow_state import classify_pending_workflow_reply

    result = classify_pending_workflow_reply(
        "2fa erledigt, ich bin weiter",
        {
            "status": "challenge_required",
            "reason": "security_challenge",
            "challenge_type": "2fa",
            "service": "github",
            "source_agent": "visual",
        },
    )

    assert result["reply_kind"] == "challenge_resolved"
    assert result["challenge_type"] == "2fa"
    assert result["service"] == "github"
