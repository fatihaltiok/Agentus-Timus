from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def test_build_auth_required_workflow_payload_normalizes_service_and_flags():
    from orchestration.approval_auth_contract import build_auth_required_workflow_payload

    payload = build_auth_required_workflow_payload(
        url="https://x.com/example/status/1",
        platform="twitter",
        message="X/Twitter verlangt Login.",
        user_action_required="Bitte bestaetige den Login-Zugriff.",
    )

    assert payload["status"] == "auth_required"
    assert payload["auth_required"] is True
    assert payload["workflow_id"].startswith("wf_")
    assert payload["service"] == "x"
    assert payload["platform"] == "twitter"
    assert payload["reason"] == "login_wall"
    assert payload["user_action_required"] == "Bitte bestaetige den Login-Zugriff."


def test_normalize_phase_d_workflow_payload_infers_awaiting_user_from_legacy_fields():
    from orchestration.approval_auth_contract import normalize_phase_d_workflow_payload

    payload = normalize_phase_d_workflow_payload(
        {
            "message": "Bitte Passwort selbst eingeben.",
            "user_action_required": "Bitte Passwort selbst eingeben.",
            "service": "linkedin",
        }
    )

    assert payload["status"] == "awaiting_user"
    assert payload["awaiting_user"] is True
    assert payload["service"] == "linkedin"
    assert payload["workflow_id"].startswith("wf_")


def test_derive_user_action_blocker_reason_maps_awaiting_user_to_legacy_blocker_name():
    from orchestration.approval_auth_contract import derive_user_action_blocker_reason

    assert (
        derive_user_action_blocker_reason(
            {
                "status": "awaiting_user",
                "user_action_required": "Bitte fortsetzen bestaetigen.",
            }
        )
        == "user_action_required"
    )


def test_build_user_mediated_login_workflow_payload_sets_resume_and_url():
    from orchestration.approval_auth_contract import build_user_mediated_login_workflow_payload

    payload = build_user_mediated_login_workflow_payload(
        service="github",
        url="https://github.com/login",
    )

    assert payload["status"] == "awaiting_user"
    assert payload["awaiting_user"] is True
    assert payload["service"] == "github"
    assert payload["url"] == "https://github.com/login"
    assert payload["reason"] == "user_mediated_login"
    assert payload["step"] == "login_form_ready"
    assert "weiter" in payload["resume_hint"].lower()
