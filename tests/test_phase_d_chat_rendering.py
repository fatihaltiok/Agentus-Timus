from __future__ import annotations

from server.mcp_server import _render_chat_reply


def test_render_chat_reply_formats_phase_d_awaiting_user_workflow_naturally():
    reply, workflow = _render_chat_reply(
        {
            "status": "awaiting_user",
            "workflow_id": "wf_123",
            "service": "github",
            "url": "https://github.com/login",
            "reason": "user_mediated_login",
            "message": "Die Login-Maske ist bereit. Bitte fuehre den Login jetzt selbst im Browser aus; Timus stoppt hier bewusst vor Benutzername, Passwort und 2FA.",
            "user_action_required": "Bitte gib Benutzername, Passwort und ggf. 2FA selbst bei github ein.",
            "resume_hint": "Sage danach 'weiter' oder 'ich bin eingeloggt'.",
            "awaiting_user": True,
        }
    )

    assert "Die Login-Maske ist bereit." in reply
    assert "Naechster Schritt: Bitte gib Benutzername, Passwort und ggf. 2FA selbst bei github ein." in reply
    assert "Danach: Sage danach 'weiter' oder 'ich bin eingeloggt'." in reply
    assert "Seite: github -> https://github.com/login" in reply
    assert workflow is not None
    assert workflow["status"] == "awaiting_user"
    assert workflow["workflow_id"] == "wf_123"


def test_render_chat_reply_keeps_plain_strings_unchanged():
    reply, workflow = _render_chat_reply("GitHub-Loginmaske ist geoeffnet und bereit zur Eingabe.")

    assert reply == "GitHub-Loginmaske ist geoeffnet und bereit zur Eingabe."
    assert workflow is None
