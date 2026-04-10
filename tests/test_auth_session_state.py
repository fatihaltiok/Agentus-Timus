from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def test_normalize_auth_session_entry_sets_scope_and_expiry():
    from orchestration.auth_session_state import normalize_auth_session_entry

    state = normalize_auth_session_entry(
        {
            "status": "authenticated",
            "service": "github",
            "url": "https://github.com/login",
            "workflow_id": "wf_auth_1",
        },
        session_id="chat_1",
        updated_at="2026-04-09T15:00:00Z",
    )

    assert state is not None
    assert state.service == "github"
    assert state.scope == "session"
    assert state.browser_session_id == "chat_1"
    assert state.confirmed_at == "2026-04-09T15:00:00Z"
    assert state.expires_at == "2026-04-10T15:00:00Z"


def test_upsert_auth_session_index_replaces_same_service_and_keeps_others():
    from orchestration.auth_session_state import upsert_auth_session_index

    existing = {
        "github": {
            "status": "authenticated",
            "service": "github",
            "url": "https://github.com/login",
            "confirmed_at": "2026-04-09T10:00:00Z",
        },
        "x": {
            "status": "authenticated",
            "service": "x",
            "url": "https://x.com/i/flow/login",
            "confirmed_at": "2026-04-09T09:00:00Z",
        },
    }

    updated = upsert_auth_session_index(
        existing,
        {
            "status": "authenticated",
            "service": "github",
            "url": "https://github.com/settings/profile",
            "workflow_id": "wf_new",
        },
        session_id="chat_2",
        updated_at="2026-04-09T16:00:00Z",
    )

    assert sorted(updated.keys()) == ["github", "x"]
    assert updated["github"]["url"] == "https://github.com/settings/profile"
    assert updated["github"]["browser_session_id"] == "chat_2"
    assert updated["x"]["service"] == "x"


def test_latest_auth_session_from_index_prefers_newest_entry():
    from orchestration.auth_session_state import latest_auth_session_from_index

    latest = latest_auth_session_from_index(
        {
            "github": {
                "status": "authenticated",
                "service": "github",
                "confirmed_at": "2026-04-09T11:00:00Z",
            },
            "x": {
                "status": "authenticated",
                "service": "x",
                "confirmed_at": "2026-04-09T12:00:00Z",
            },
        }
    )

    assert latest["service"] == "x"


def test_normalize_auth_session_entry_preserves_session_reused_status():
    from orchestration.auth_session_state import normalize_auth_session_entry

    state = normalize_auth_session_entry(
        {
            "status": "session_reused",
            "service": "github",
            "url": "https://github.com/settings/profile",
        },
        updated_at="2026-04-09T18:00:00Z",
    )

    assert state is not None
    assert state.status == "session_reused"


def test_is_auth_session_reusable_rejects_expired_entry():
    from orchestration.auth_session_state import is_auth_session_reusable

    reusable = is_auth_session_reusable(
        {
            "status": "authenticated",
            "service": "github",
            "url": "https://github.com/settings/profile",
            "expires_at": "2026-04-09T17:59:59Z",
        },
        service="github",
        now="2026-04-09T18:00:00Z",
    )

    assert reusable is False
