"""Tests für den Telegram-Digest-Buffer in utils/telegram_notify.py."""
from __future__ import annotations

import asyncio
import sys
import time
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import utils.telegram_notify as tg


def _reset_buffer():
    tg._buf.clear()
    tg._last_flush = 0.0


# ── Buffer-Logik ─────────────────────────────────────────────────────────────

class TestDigestBuffer:

    def setup_method(self):
        _reset_buffer()

    def test_message_lands_in_buffer_when_interval_not_reached(self, monkeypatch):
        """Nachricht landet im Buffer wenn Flush-Intervall noch nicht abgelaufen."""
        monkeypatch.setenv("TELEGRAM_DIGEST_INTERVAL_MINUTES", "30")
        tg._last_flush = time.monotonic()  # gerade geflusht → kein Flush fällig

        sent_msgs = []

        async def fake_send_raw(msg, parse_mode="Markdown"):
            sent_msgs.append(msg)
            return True

        with patch.object(tg, "_send_raw", side_effect=fake_send_raw):
            asyncio.get_event_loop().run_until_complete(
                tg.send_telegram("Hallo Buffer")
            )

        assert "Hallo Buffer" in tg._buf
        assert sent_msgs == []  # noch nicht gesendet

    def test_urgent_bypasses_buffer(self, monkeypatch):
        """urgent=True sendet sofort ohne Buffer."""
        monkeypatch.setenv("TELEGRAM_DIGEST_INTERVAL_MINUTES", "30")
        tg._last_flush = time.monotonic()

        sent_msgs = []

        async def fake_send_raw(msg, parse_mode="Markdown"):
            sent_msgs.append(msg)
            return True

        with patch.object(tg, "_send_raw", side_effect=fake_send_raw):
            asyncio.get_event_loop().run_until_complete(
                tg.send_telegram("KRITISCH!", urgent=True)
            )

        assert sent_msgs == ["KRITISCH!"]
        assert tg._buf == []  # Buffer unberührt

    def test_flush_when_interval_elapsed(self, monkeypatch):
        """Buffer wird geleert wenn Intervall abgelaufen ist."""
        monkeypatch.setenv("TELEGRAM_DIGEST_INTERVAL_MINUTES", "30")
        tg._last_flush = time.monotonic() - 1900  # ~31 Minuten her

        sent_msgs = []

        async def fake_send_raw(msg, parse_mode="Markdown"):
            sent_msgs.append(msg)
            return True

        with patch.object(tg, "_send_raw", side_effect=fake_send_raw):
            asyncio.get_event_loop().run_until_complete(
                tg.send_telegram("Neue Meldung")
            )

        # Buffer muss geleert worden sein
        assert tg._buf == []
        # Digest wurde gesendet
        assert len(sent_msgs) == 1
        assert "Neue Meldung" in sent_msgs[0]

    def test_digest_contains_all_buffered_messages(self, monkeypatch):
        """Digest enthält alle gepufferten Nachrichten."""
        monkeypatch.setenv("TELEGRAM_DIGEST_INTERVAL_MINUTES", "30")
        tg._last_flush = time.monotonic() - 1900

        tg._buf = ["Meldung 1", "Meldung 2"]
        sent_msgs = []

        async def fake_send_raw(msg, parse_mode="Markdown"):
            sent_msgs.append(msg)
            return True

        with patch.object(tg, "_send_raw", side_effect=fake_send_raw):
            asyncio.get_event_loop().run_until_complete(
                tg.send_telegram("Meldung 3")
            )

        digest = sent_msgs[0]
        assert "Meldung 1" in digest
        assert "Meldung 2" in digest
        assert "Meldung 3" in digest
        assert "3 Meldungen" in digest

    def test_digest_header_singular(self, monkeypatch):
        """Singular 'Meldung' bei genau 1 Nachricht."""
        monkeypatch.setenv("TELEGRAM_DIGEST_INTERVAL_MINUTES", "30")
        tg._last_flush = time.monotonic() - 1900

        sent_msgs = []

        async def fake_send_raw(msg, parse_mode="Markdown"):
            sent_msgs.append(msg)
            return True

        with patch.object(tg, "_send_raw", side_effect=fake_send_raw):
            asyncio.get_event_loop().run_until_complete(
                tg.send_telegram("Einzige Meldung")
            )

        assert "1 Meldung" in sent_msgs[0]
        assert "1 Meldungen" not in sent_msgs[0]

    def test_flush_clears_buffer(self, monkeypatch):
        """Nach flush_telegram_digest ist der Buffer leer."""
        tg._buf = ["A", "B", "C"]
        tg._last_flush = 0.0

        async def fake_send_raw(msg, parse_mode="Markdown"):
            return True

        with patch.object(tg, "_send_raw", side_effect=fake_send_raw):
            asyncio.get_event_loop().run_until_complete(tg.flush_telegram_digest())

        assert tg._buf == []

    def test_flush_empty_buffer_no_send(self, monkeypatch):
        """Flush bei leerem Buffer schickt keine Nachricht."""
        tg._buf = []
        sent_msgs = []

        async def fake_send_raw(msg, parse_mode="Markdown"):
            sent_msgs.append(msg)
            return True

        with patch.object(tg, "_send_raw", side_effect=fake_send_raw):
            result = asyncio.get_event_loop().run_until_complete(
                tg.flush_telegram_digest()
            )

        assert result is False
        assert sent_msgs == []

    def test_digest_interval_env_respected(self, monkeypatch):
        """TELEGRAM_DIGEST_INTERVAL_MINUTES aus .env wird gelesen."""
        monkeypatch.setenv("TELEGRAM_DIGEST_INTERVAL_MINUTES", "10")
        assert tg._digest_interval_seconds() == 600.0

        monkeypatch.setenv("TELEGRAM_DIGEST_INTERVAL_MINUTES", "30")
        assert tg._digest_interval_seconds() == 1800.0

    def test_should_flush_false_when_recent(self, monkeypatch):
        monkeypatch.setenv("TELEGRAM_DIGEST_INTERVAL_MINUTES", "30")
        tg._last_flush = time.monotonic()  # gerade eben
        assert tg._should_flush() is False

    def test_should_flush_true_when_overdue(self, monkeypatch):
        monkeypatch.setenv("TELEGRAM_DIGEST_INTERVAL_MINUTES", "30")
        tg._last_flush = time.monotonic() - 2000
        assert tg._should_flush() is True
