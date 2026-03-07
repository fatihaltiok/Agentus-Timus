"""
tests/test_communication_improvements.py — Phase-3: Communication Agent

Tests für:
  - MAX_DRAFT_REVISIONS Invariante (nutzt m14_retry_bound Th.28)
  - _draft_email_with_review: Telegram-Entwurf-Flow
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from unittest.mock import AsyncMock, patch
from hypothesis import given, settings
from hypothesis import strategies as st

from agent.agents.communication import CommunicationAgent
from agent.base_agent import AGENT_CAPABILITY_MAP


def _make_agent() -> CommunicationAgent:
    os.environ["TIMUS_VALIDATE_CONFIGURED_MODELS"] = "false"
    return CommunicationAgent(tools_description_string="")


# ──────────────────────────────────────────────────────────────────
# MAX_DRAFT_REVISIONS Invariante (Th.28 m14_retry_bound)
# ──────────────────────────────────────────────────────────────────

def test_max_draft_revisions_positive():
    assert CommunicationAgent.MAX_DRAFT_REVISIONS > 0


def test_communication_agent_has_email_capabilities():
    caps = AGENT_CAPABILITY_MAP["communication"]
    assert "email" in caps
    assert "communication" in caps


def test_max_draft_revisions_value():
    assert CommunicationAgent.MAX_DRAFT_REVISIONS == 3


@given(revision=st.integers(min_value=0, max_value=CommunicationAgent.MAX_DRAFT_REVISIONS))
@settings(max_examples=100)
def test_draft_revisions_bound(revision):
    """Th.28 (m14_retry_bound): revision ≤ MAX_DRAFT_REVISIONS → revision < MAX_DRAFT_REVISIONS + 1."""
    assert revision < CommunicationAgent.MAX_DRAFT_REVISIONS + 1


# ──────────────────────────────────────────────────────────────────
# _draft_email_with_review
# ──────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_draft_sends_telegram_preview():
    """Entwurf wird als Telegram-Nachricht gesendet."""
    agent = _make_agent()
    sent_messages = []

    async def mock_send(msg, parse_mode=None):
        sent_messages.append(msg)

    with patch("utils.telegram_notify.send_telegram", mock_send):
        result = await agent._draft_email_with_review(
            to="test@example.com",
            subject="Test-Betreff",
            body="Hallo, das ist ein Test.",
        )

    assert len(sent_messages) == 1
    assert "test@example.com" in sent_messages[0] or "Test-Betreff" in sent_messages[0]


@pytest.mark.asyncio
async def test_draft_result_contains_expected_keys():
    """Rückgabe-Dict hat status, revision, to, subject."""
    agent = _make_agent()

    async def mock_send(msg, parse_mode=None):
        pass

    with patch("utils.telegram_notify.send_telegram", mock_send):
        result = await agent._draft_email_with_review(
            to="user@test.com",
            subject="Betreff",
            body="Inhalt",
        )

    assert "status" in result
    assert "revision" in result
    assert result["status"] in ("pending", "sent", "cancelled", "error")


@pytest.mark.asyncio
async def test_draft_revision_within_bounds():
    """revision im Ergebnis ≤ MAX_DRAFT_REVISIONS."""
    agent = _make_agent()

    async def mock_send(msg, parse_mode=None):
        pass

    with patch("utils.telegram_notify.send_telegram", mock_send):
        result = await agent._draft_email_with_review(
            to="user@test.com",
            subject="Test",
            body="Body",
        )

    assert result["revision"] <= CommunicationAgent.MAX_DRAFT_REVISIONS


@pytest.mark.asyncio
async def test_draft_telegram_exception_returns_error():
    """Wenn Telegram nicht erreichbar → status='error', kein Crash."""
    agent = _make_agent()

    async def mock_send(msg, parse_mode=None):
        raise Exception("Telegram nicht erreichbar")

    with patch("utils.telegram_notify.send_telegram", mock_send):
        result = await agent._draft_email_with_review(
            to="user@test.com",
            subject="Test",
            body="Body",
        )

    assert result["status"] == "error"
    assert "error" in result


@pytest.mark.asyncio
async def test_draft_preview_contains_subject():
    """Telegram-Vorschau enthält den Betreff."""
    agent = _make_agent()
    sent = []

    async def mock_send(msg, parse_mode=None):
        sent.append(msg)

    with patch("utils.telegram_notify.send_telegram", mock_send):
        await agent._draft_email_with_review(
            to="user@test.com",
            subject="Wichtiger Betreff",
            body="Content",
        )

    assert "Wichtiger Betreff" in sent[0]


@pytest.mark.asyncio
async def test_draft_preview_contains_recipient():
    """Telegram-Vorschau enthält den Empfänger."""
    agent = _make_agent()
    sent = []

    async def mock_send(msg, parse_mode=None):
        sent.append(msg)

    with patch("utils.telegram_notify.send_telegram", mock_send):
        await agent._draft_email_with_review(
            to="empfaenger@example.com",
            subject="Test",
            body="Content",
        )

    assert "empfaenger@example.com" in sent[0]


@pytest.mark.asyncio
async def test_draft_long_body_truncated():
    """Langer Body wird auf 500 Zeichen gekürzt (kein Overflow)."""
    agent = _make_agent()
    sent = []

    async def mock_send(msg, parse_mode=None):
        sent.append(msg)

    long_body = "X" * 2000
    with patch("utils.telegram_notify.send_telegram", mock_send):
        await agent._draft_email_with_review(
            to="user@test.com",
            subject="Test",
            body=long_body,
        )

    # Gesamte Nachricht ist kürzer als 2000 + overhead
    assert len(sent[0]) < 1500


def test_email_send_requested_detection():
    assert CommunicationAgent._email_send_requested(
        "Sende eine E-Mail mit PDF-Anhang an fatihaltiok@outlook.com"
    ) is True
    assert CommunicationAgent._email_send_requested(
        "Schreibe einen LinkedIn-Post über KI-Agenten"
    ) is False


def test_verified_email_send_requires_real_tool_success():
    agent = _make_agent()
    agent._task_action_history = [
        {
            "method": "send_email",
            "observation": {
                "status": "success",
                "data": {"success": True, "message": "sent"},
            },
        }
    ]
    assert agent._has_verified_email_send() is True

    agent._task_action_history = [
        {
            "method": "send_email",
            "observation": {"skipped": True, "reason": "blocked"},
        }
    ]
    assert agent._has_verified_email_send() is False


def test_result_claims_email_success_marker():
    assert CommunicationAgent._result_claims_email_success(
        "**E-Mail erfolgreich versendet!**"
    ) is True
    assert CommunicationAgent._result_claims_email_success(
        "Entwurf erstellt, aber noch nicht gesendet."
    ) is False
