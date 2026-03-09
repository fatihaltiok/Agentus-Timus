from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock

import pytest

from orchestration.ambient_context_engine import AmbientContextEngine
from orchestration.replanning_engine import ReplanningEngine
from tools.application_launcher.tool import _split_launch_command
from tools.visual_browser_tool.tool import (
    _build_windows_browser_command,
    _get_windows_taskkill_command,
)
from utils.stable_hash import stable_text_digest


def test_split_launch_command_preserves_quoted_segments() -> None:
    parts = _split_launch_command('open -a "Google Chrome" --args --new-window')
    assert parts == ["open", "-a", "Google Chrome", "--args", "--new-window"]


def test_windows_browser_command_avoids_shell_builtin_dependency() -> None:
    cmd = _build_windows_browser_command("chrome", "https://booking.com")
    assert cmd[:6] == ["cmd.exe", "/c", "start", "", "chrome", "--new-window"]
    assert cmd[-1] == "https://booking.com"
    assert _get_windows_taskkill_command(1234) == ["taskkill", "/PID", "1234", "/T", "/F"]


def test_replanning_event_key_is_stable_and_short() -> None:
    engine = ReplanningEngine(queue=MagicMock(), now_provider=lambda: datetime(2026, 3, 9, 12, 0, 0))
    commitment = {"id": "c1", "goal_id": "g1", "deadline": "2026-03-09T18:00:00"}
    details = {"reason": "deadline_timeout"}
    now = datetime(2026, 3, 9, 12, 0, 0)

    first = engine._event_key(commitment, "deadline_timeout", details, now)
    second = engine._event_key(commitment, "deadline_timeout", details, now)

    assert first == second
    assert first.endswith(stable_text_digest("c1|deadline_timeout|2026-03-09|g1|2026-03-09T18:00:00|deadline_timeout", hex_chars=16))


@pytest.mark.asyncio
async def test_ambient_email_signal_falls_back_to_stable_subject_fingerprint(monkeypatch) -> None:
    from tools.email_tool import tool as email_tool

    monkeypatch.setattr(email_tool, "get_email_status", lambda: {"authenticated": True})
    monkeypatch.setattr(
        email_tool,
        "read_emails",
        lambda *_args, **_kwargs: {
            "emails": [
                {
                    "from": {"emailAddress": {"address": "kunde@example.com"}},
                    "subject": "Booking Anfrage",
                    "bodyPreview": "Bitte antworte schnell.",
                    "id": "",
                }
            ]
        },
    )

    engine = AmbientContextEngine()
    signals = await engine._check_emails()

    assert len(signals) == 1
    assert signals[0].dedup_key == f"email:{stable_text_digest('Booking Anfrage', hex_chars=8)}"
    assert len(signals[0].signal_id) == 12
