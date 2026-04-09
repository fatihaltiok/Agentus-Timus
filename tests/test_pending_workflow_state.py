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
