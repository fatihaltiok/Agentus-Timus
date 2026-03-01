# tests/test_email_tool.py
"""
Pytest-Suite für tools/email_tool/tool.py.

Alle Netzwerkoperationen werden gemockt — kein echtes E-Mail-Konto nötig.
"""

from __future__ import annotations

import imaplib
import smtplib
from email import message_from_string
from unittest.mock import MagicMock, patch, PropertyMock
import pytest

# Wir importieren die Funktionen direkt (ohne laufenden MCP-Server)
import importlib
import sys
import os

# Sicherstellen dass Projektroot im Path
from pathlib import Path
_root = Path(__file__).resolve().parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def patch_env(monkeypatch):
    """Setzt Fake-Credentials für alle Tests."""
    monkeypatch.setenv("TIMUS_EMAIL", "timus.agent@outlook.com")
    monkeypatch.setenv("TIMUS_EMAIL_PASSWORD", "FakePassword123!")
    monkeypatch.setenv("TIMUS_EMAIL_DISPLAY_NAME", "Timus Agent")
    monkeypatch.setenv("TIMUS_EMAIL_IMAP_HOST", "outlook.office365.com")
    monkeypatch.setenv("TIMUS_EMAIL_IMAP_PORT", "993")
    monkeypatch.setenv("TIMUS_EMAIL_SMTP_HOST", "smtp-mail.outlook.com")
    monkeypatch.setenv("TIMUS_EMAIL_SMTP_PORT", "587")
    # Modul neu laden damit geänderte ENV-Vars wirken
    if "tools.email_tool.tool" in sys.modules:
        importlib.reload(sys.modules["tools.email_tool.tool"])
    yield


@pytest.fixture
def email_tool():
    """Importiert das Tool-Modul frisch."""
    import tools.email_tool.tool as m
    return m


# ── send_email Tests ──────────────────────────────────────────────────────────

class TestSendEmail:

    def test_send_success(self, email_tool):
        """Erfolgreicher Versand gibt success=True zurück."""
        mock_smtp = MagicMock(spec=smtplib.SMTP)
        with patch("tools.email_tool.tool.smtplib.SMTP", return_value=mock_smtp):
            mock_smtp.__enter__ = lambda s: s
            mock_smtp.__exit__ = MagicMock(return_value=False)
            mock_smtp.sendmail = MagicMock()
            mock_smtp.ehlo = MagicMock()
            mock_smtp.starttls = MagicMock()
            mock_smtp.login = MagicMock()
            mock_smtp.quit = MagicMock()

            result = email_tool.send_email(
                to="fatih@example.com",
                subject="Test Betreff",
                body="Hallo Welt",
            )

        assert result["success"] is True
        assert result["to"] == "fatih@example.com"
        assert result["subject"] == "Test Betreff"

    def test_send_missing_credentials(self, email_tool, monkeypatch):
        """Fehlende Credentials → success=False mit Fehlermeldung."""
        monkeypatch.setenv("TIMUS_EMAIL", "")
        importlib.reload(email_tool)

        result = email_tool.send_email(
            to="fatih@example.com",
            subject="Test",
            body="Body",
        )

        assert result["success"] is False
        assert "TIMUS_EMAIL" in result["error"]

    def test_send_smtp_auth_error(self, email_tool):
        """SMTP-Authentifizierungsfehler → success=False."""
        with patch("tools.email_tool.tool.smtplib.SMTP") as MockSMTP:
            # _smtp_connect() nutzt smtplib.SMTP() direkt (kein Kontext-Manager)
            # → der konstruierte Mock ist MockSMTP.return_value
            mock_instance = MockSMTP.return_value
            mock_instance.ehlo = MagicMock()
            mock_instance.starttls = MagicMock()
            mock_instance.login = MagicMock(
                side_effect=smtplib.SMTPAuthenticationError(535, b"Auth failed")
            )
            mock_instance.quit = MagicMock()

            result = email_tool.send_email(
                to="fatih@example.com",
                subject="Test",
                body="Body",
            )

        assert result["success"] is False
        assert "Authentifizierung" in result["error"]

    def test_send_with_cc_bcc(self, email_tool):
        """CC und BCC werden korrekt übergeben."""
        sent_recipients = []
        mock_smtp = MagicMock(spec=smtplib.SMTP)
        mock_smtp.sendmail.side_effect = lambda frm, to, msg: sent_recipients.extend(to)
        mock_smtp.ehlo = MagicMock()
        mock_smtp.starttls = MagicMock()
        mock_smtp.login = MagicMock()
        mock_smtp.quit = MagicMock()

        with patch("tools.email_tool.tool.smtplib.SMTP", return_value=mock_smtp):
            mock_smtp.__enter__ = lambda s: s
            mock_smtp.__exit__ = MagicMock(return_value=False)

            result = email_tool.send_email(
                to="main@example.com",
                subject="CC Test",
                body="Body",
                cc="copy@example.com",
                bcc="hidden@example.com",
            )

        assert result["success"] is True
        assert "copy@example.com" in sent_recipients
        assert "hidden@example.com" in sent_recipients

    def test_send_html_body(self, email_tool):
        """HTML-Body erzeugt multipart/alternative Nachricht."""
        captured = []
        mock_smtp = MagicMock(spec=smtplib.SMTP)
        mock_smtp.sendmail.side_effect = lambda frm, to, msg: captured.append(msg)
        mock_smtp.ehlo = MagicMock()
        mock_smtp.starttls = MagicMock()
        mock_smtp.login = MagicMock()
        mock_smtp.quit = MagicMock()

        with patch("tools.email_tool.tool.smtplib.SMTP", return_value=mock_smtp):
            mock_smtp.__enter__ = lambda s: s
            mock_smtp.__exit__ = MagicMock(return_value=False)

            email_tool.send_email(
                to="x@example.com",
                subject="HTML",
                body="Plaintext",
                html_body="<b>HTML</b>",
            )

        assert len(captured) == 1
        assert "multipart/alternative" in captured[0]


# ── read_emails Tests ─────────────────────────────────────────────────────────

class TestReadEmails:

    def _make_raw_email(self, subject: str, from_: str = "sender@example.com", body: str = "Hallo") -> bytes:
        """Erstellt eine minimale RFC-822-E-Mail."""
        return (
            f"From: {from_}\r\n"
            f"To: timus.agent@outlook.com\r\n"
            f"Subject: {subject}\r\n"
            f"Date: Mon, 01 Mar 2026 12:00:00 +0000\r\n"
            f"Content-Type: text/plain; charset=utf-8\r\n"
            f"\r\n"
            f"{body}\r\n"
        ).encode("utf-8")

    def _make_imap_mock(self, uid_list: list[str], emails: dict[str, bytes]) -> MagicMock:
        """Erstellt einen IMAP4_SSL-Mock mit vorgefertigten UIDs und E-Mails."""
        imap = MagicMock(spec=imaplib.IMAP4_SSL)
        imap.login = MagicMock(return_value=("OK", [b"Logged in"]))
        imap.select = MagicMock(return_value=("OK", [b"5"]))
        imap.logout = MagicMock()

        uid_bytes = [uid.encode() for uid in uid_list]
        imap.search = MagicMock(return_value=("OK", [b" ".join(uid_bytes)]))

        def fake_fetch(uid, spec):
            raw = emails.get(uid.decode() if isinstance(uid, bytes) else uid, b"")
            flags = b"(RFC822 {100})"
            return ("OK", [(flags, raw)])

        imap.fetch = MagicMock(side_effect=fake_fetch)
        return imap

    def test_read_success(self, email_tool):
        """Liest zwei E-Mails korrekt aus."""
        raw1 = self._make_raw_email("Erste Mail", body="Inhalt 1")
        raw2 = self._make_raw_email("Zweite Mail", body="Inhalt 2")
        imap_mock = self._make_imap_mock(["1", "2"], {"1": raw1, "2": raw2})

        with patch("tools.email_tool.tool.imaplib.IMAP4_SSL", return_value=imap_mock):
            imap_mock.__enter__ = lambda s: s
            imap_mock.__exit__ = MagicMock(return_value=False)

            result = email_tool.read_emails(limit=10)

        assert result["success"] is True
        assert result["count"] == 2
        subjects = [m["subject"] for m in result["emails"]]
        assert "Erste Mail" in subjects
        assert "Zweite Mail" in subjects

    def test_read_empty_inbox(self, email_tool):
        """Leerer Posteingang → count=0, leere Liste."""
        imap_mock = MagicMock(spec=imaplib.IMAP4_SSL)
        imap_mock.login = MagicMock(return_value=("OK", [b"OK"]))
        imap_mock.select = MagicMock(return_value=("OK", [b"0"]))
        imap_mock.search = MagicMock(return_value=("OK", [b""]))
        imap_mock.logout = MagicMock()

        with patch("tools.email_tool.tool.imaplib.IMAP4_SSL", return_value=imap_mock):
            imap_mock.__enter__ = lambda s: s
            imap_mock.__exit__ = MagicMock(return_value=False)

            result = email_tool.read_emails()

        assert result["success"] is True
        assert result["count"] == 0
        assert result["emails"] == []

    def test_read_limit_respected(self, email_tool):
        """limit=2 liefert maximal 2 E-Mails."""
        emails = {str(i): self._make_raw_email(f"Mail {i}") for i in range(1, 6)}
        imap_mock = self._make_imap_mock(list(emails.keys()), emails)

        with patch("tools.email_tool.tool.imaplib.IMAP4_SSL", return_value=imap_mock):
            imap_mock.__enter__ = lambda s: s
            imap_mock.__exit__ = MagicMock(return_value=False)

            result = email_tool.read_emails(limit=2)

        assert result["success"] is True
        assert result["count"] <= 2

    def test_read_unread_only(self, email_tool):
        """unread_only=True übergibt UNSEEN an IMAP-Suche."""
        imap_mock = MagicMock(spec=imaplib.IMAP4_SSL)
        imap_mock.login = MagicMock(return_value=("OK", [b"OK"]))
        imap_mock.select = MagicMock(return_value=("OK", [b"10"]))
        imap_mock.search = MagicMock(return_value=("OK", [b""]))
        imap_mock.logout = MagicMock()

        with patch("tools.email_tool.tool.imaplib.IMAP4_SSL", return_value=imap_mock):
            imap_mock.__enter__ = lambda s: s
            imap_mock.__exit__ = MagicMock(return_value=False)

            email_tool.read_emails(unread_only=True)

        call_args = imap_mock.search.call_args
        assert b"UNSEEN" in call_args[0]

    def test_read_missing_credentials(self, email_tool, monkeypatch):
        """Fehlende Credentials → success=False."""
        monkeypatch.setenv("TIMUS_EMAIL", "")
        importlib.reload(email_tool)

        result = email_tool.read_emails()

        assert result["success"] is False

    def test_read_invalid_mailbox(self, email_tool):
        """Ungültiges Postfach → success=False."""
        imap_mock = MagicMock(spec=imaplib.IMAP4_SSL)
        imap_mock.login = MagicMock(return_value=("OK", [b"OK"]))
        imap_mock.select = MagicMock(return_value=("NO", [b"Mailbox not found"]))
        imap_mock.logout = MagicMock()

        with patch("tools.email_tool.tool.imaplib.IMAP4_SSL", return_value=imap_mock):
            imap_mock.__enter__ = lambda s: s
            imap_mock.__exit__ = MagicMock(return_value=False)

            result = email_tool.read_emails(mailbox="NONEXISTENT")

        assert result["success"] is False
        assert "NONEXISTENT" in result["error"]


# ── get_email_status Tests ────────────────────────────────────────────────────

class TestGetEmailStatus:

    def test_status_both_ok(self, email_tool):
        """Beide Verbindungen erfolgreich → smtp_ok=True, imap_ok=True."""
        mock_smtp = MagicMock(spec=smtplib.SMTP)
        mock_smtp.ehlo = MagicMock()
        mock_smtp.starttls = MagicMock()
        mock_smtp.login = MagicMock()
        mock_smtp.quit = MagicMock()

        mock_imap = MagicMock(spec=imaplib.IMAP4_SSL)
        mock_imap.login = MagicMock(return_value=("OK", [b"OK"]))
        mock_imap.noop = MagicMock(return_value=("OK", [b"NOOP"]))
        mock_imap.logout = MagicMock()

        with patch("tools.email_tool.tool.smtplib.SMTP", return_value=mock_smtp), \
             patch("tools.email_tool.tool.imaplib.IMAP4_SSL", return_value=mock_imap):
            mock_smtp.__enter__ = lambda s: s
            mock_smtp.__exit__ = MagicMock(return_value=False)
            mock_imap.__enter__ = lambda s: s
            mock_imap.__exit__ = MagicMock(return_value=False)

            result = email_tool.get_email_status()

        assert result["smtp_ok"] is True
        assert result["imap_ok"] is True
        assert result["address"] == "timus.agent@outlook.com"

    def test_status_missing_credentials(self, email_tool, monkeypatch):
        """Keine Credentials → Frühzeitige Rückgabe mit Fehlermeldung."""
        monkeypatch.setenv("TIMUS_EMAIL", "")
        importlib.reload(email_tool)

        result = email_tool.get_email_status()

        assert result["smtp_ok"] is False
        assert result["imap_ok"] is False
        assert "error" in result

    def test_status_smtp_fail_imap_ok(self, email_tool):
        """SMTP schlägt fehl, IMAP OK → smtp_ok=False, imap_ok=True."""
        mock_smtp = MagicMock(spec=smtplib.SMTP)
        mock_smtp.ehlo = MagicMock(side_effect=smtplib.SMTPException("Connection refused"))

        mock_imap = MagicMock(spec=imaplib.IMAP4_SSL)
        mock_imap.login = MagicMock(return_value=("OK", [b"OK"]))
        mock_imap.noop = MagicMock(return_value=("OK", [b"NOOP"]))
        mock_imap.logout = MagicMock()

        with patch("tools.email_tool.tool.smtplib.SMTP", return_value=mock_smtp), \
             patch("tools.email_tool.tool.imaplib.IMAP4_SSL", return_value=mock_imap):
            mock_smtp.__enter__ = lambda s: s
            mock_smtp.__exit__ = MagicMock(return_value=False)
            mock_imap.__enter__ = lambda s: s
            mock_imap.__exit__ = MagicMock(return_value=False)

            result = email_tool.get_email_status()

        assert result["smtp_ok"] is False
        assert result["imap_ok"] is True
        assert "smtp_error" in result


# ── Hilfsfunktionen Tests ─────────────────────────────────────────────────────

class TestHelpers:

    def test_decode_header_plain(self, email_tool):
        result = email_tool._decode_header_value("Simple Header")
        assert result == "Simple Header"

    def test_decode_header_none(self, email_tool):
        result = email_tool._decode_header_value(None)
        assert result == ""

    def test_decode_header_encoded(self, email_tool):
        # RFC2047 encoded-word
        encoded = "=?utf-8?b?SGFsbG8gV2VsdA==?="
        result = email_tool._decode_header_value(encoded)
        assert "Hallo" in result

    def test_extract_body_plaintext(self, email_tool):
        raw = (
            "From: test@example.com\r\n"
            "Subject: Test\r\n"
            "Content-Type: text/plain; charset=utf-8\r\n"
            "\r\n"
            "Hallo Welt\r\n"
        )
        msg = message_from_string(raw)
        body = email_tool._extract_body(msg)
        assert "Hallo Welt" in body
