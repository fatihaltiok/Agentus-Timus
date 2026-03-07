# tests/test_email_tool.py
"""
Pytest-Suite für tools/email_tool/tool.py.

Alle Netzwerkoperationen werden gemockt — kein echtes E-Mail-Konto nötig.
Deckt alle 3 Backends ab: resend (Standard), smtp, msgraph.
"""

from __future__ import annotations

import importlib
import json
import os
import sys
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

_root = Path(__file__).resolve().parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def patch_env(monkeypatch, tmp_path):
    """Fake-Credentials + gültiger Token-Cache für alle Tests."""
    cache_file = tmp_path / "token_cache.bin"
    cache_file.write_text(json.dumps({
        "access_token":  "fake_access_token",
        "refresh_token": "fake_refresh_token",
        "expires_at":    time.time() + 3600,
        "token_type":    "Bearer",
    }))
    monkeypatch.setenv("TIMUS_EMAIL",              "timus@test.com")
    monkeypatch.setenv("TIMUS_EMAIL_DISPLAY_NAME", "Timus Test")
    monkeypatch.setenv("TIMUS_GRAPH_CLIENT_ID",    "fake-client-id")
    monkeypatch.setenv("TIMUS_GRAPH_AUTHORITY",    "https://login.microsoftonline.com/consumers")
    monkeypatch.setenv("TIMUS_GRAPH_TOKEN_CACHE",  str(cache_file))


@pytest.fixture
def tool():
    """Lädt das Tool-Modul frisch (nimmt ENV-Änderungen des autouse-Fixtures auf)."""
    import tools.email_tool.tool as m
    importlib.reload(m)
    return m


# ── send_email — Resend Backend (Standard) ────────────────────────────────────

class TestSendEmailResend:

    def test_resend_success(self, tool, monkeypatch):
        """Erfolgreicher Resend-Versand → success=True, Backend im message-Text."""
        monkeypatch.setenv("EMAIL_BACKEND", "resend")
        with patch("utils.resend_email.send_email_resend", new_callable=AsyncMock, return_value=True):
            result = tool.send_email(to="x@example.com", subject="Test", body="Hallo")
        assert result["success"] is True
        assert result["to"] == "x@example.com"
        assert "resend" in result["message"]

    def test_resend_failure(self, tool, monkeypatch):
        """Resend gibt False zurück → success=False mit Fehlermeldung."""
        monkeypatch.setenv("EMAIL_BACKEND", "resend")
        with patch("utils.resend_email.send_email_resend", new_callable=AsyncMock, return_value=False):
            result = tool.send_email(to="x@example.com", subject="Test", body="Hallo")
        assert result["success"] is False
        assert "error" in result

    def test_resend_with_pdf_attachment(self, tool, monkeypatch, tmp_path):
        """PDF-Anhang → artifacts enthält Eintrag mit type=pdf."""
        monkeypatch.setenv("EMAIL_BACKEND", "resend")
        att = tmp_path / "report.pdf"
        att.write_bytes(b"%PDF-1.4 fake")
        with patch("utils.resend_email.send_email_resend", new_callable=AsyncMock, return_value=True):
            result = tool.send_email(
                to="x@example.com", subject="Report", body="Anhang",
                attachment_path=str(att),
            )
        assert result["success"] is True
        assert len(result["artifacts"]) == 1
        assert result["artifacts"][0]["type"] == "pdf"
        assert result["artifacts"][0]["source"] == "email_tool"

    def test_resend_exception_propagated(self, tool, monkeypatch):
        """Exception in Resend → success=False, Fehlertext weitergegeben."""
        monkeypatch.setenv("EMAIL_BACKEND", "resend")
        with patch("utils.resend_email.send_email_resend",
                   new_callable=AsyncMock, side_effect=Exception("connection timeout")):
            result = tool.send_email(to="x@example.com", subject="Test", body="Body")
        assert result["success"] is False
        assert "connection timeout" in result["error"]


# ── send_email — SMTP Backend ─────────────────────────────────────────────────

class TestSendEmailSmtp:

    def test_smtp_success(self, tool, monkeypatch):
        """SMTP-Versand erfolgreich → success=True, 'smtp' im message-Text."""
        monkeypatch.setenv("EMAIL_BACKEND", "smtp")
        with patch("utils.smtp_email.send_email_smtp", new_callable=AsyncMock, return_value=True):
            result = tool.send_email(to="y@example.com", subject="SMTP Test", body="Body")
        assert result["success"] is True
        assert "smtp" in result["message"]

    def test_smtp_failure(self, tool, monkeypatch):
        """SMTP gibt False zurück → success=False."""
        monkeypatch.setenv("EMAIL_BACKEND", "smtp")
        with patch("utils.smtp_email.send_email_smtp", new_callable=AsyncMock, return_value=False):
            result = tool.send_email(to="y@example.com", subject="Fail", body="Body")
        assert result["success"] is False


# ── send_email — Microsoft Graph Backend ─────────────────────────────────────

class TestSendEmailMsgraph:

    def test_msgraph_success_202(self, tool, monkeypatch):
        """Graph /me/sendMail → HTTP 202 → success=True."""
        monkeypatch.setenv("EMAIL_BACKEND", "msgraph")
        mock_resp = MagicMock(status_code=202)
        with patch("requests.post", return_value=mock_resp):
            result = tool.send_email(to="z@example.com", subject="Graph Test", body="Body")
        assert result["success"] is True
        assert "msgraph" in result["message"]

    def test_msgraph_http_400(self, tool, monkeypatch):
        """Graph gibt HTTP 400 zurück → success=False mit HTTP-Code im error."""
        monkeypatch.setenv("EMAIL_BACKEND", "msgraph")
        mock_resp = MagicMock(status_code=400)
        mock_resp.json.return_value = {"error": {"message": "Bad Request"}}
        with patch("requests.post", return_value=mock_resp):
            result = tool.send_email(to="z@example.com", subject="Fail", body="Body")
        assert result["success"] is False
        assert "400" in result["error"]

    def test_msgraph_no_token_raises(self, tool, monkeypatch):
        """Kein OAuth2-Token → RuntimeError wird zu success=False."""
        monkeypatch.setenv("EMAIL_BACKEND", "msgraph")
        with patch.object(tool, "_get_access_token",
                          side_effect=RuntimeError("Kein OAuth2-Token vorhanden.")):
            result = tool.send_email(to="z@example.com", subject="Test", body="Body")
        assert result["success"] is False
        assert "Token" in result["error"] or "oauth" in result["error"].lower()


# ── read_emails ───────────────────────────────────────────────────────────────

class TestReadEmails:

    def test_read_smtp_success(self, tool, monkeypatch):
        """SMTP-Backend: 2 E-Mails gelesen → count=2, Subjects korrekt."""
        monkeypatch.setenv("EMAIL_BACKEND", "smtp")
        fake = [
            {"from": "a@example.com", "subject": "Erste Mail", "date": "2026-03-07", "body_preview": "..."},
            {"from": "b@example.com", "subject": "Zweite Mail", "date": "2026-03-07", "body_preview": "..."},
        ]
        with patch("utils.smtp_email.read_emails_smtp", new_callable=AsyncMock, return_value=fake):
            result = tool.read_emails(limit=10)
        assert result["success"] is True
        assert result["count"] == 2
        subjects = [m["subject"] for m in result["emails"]]
        assert "Erste Mail" in subjects
        assert "Zweite Mail" in subjects

    def test_read_smtp_empty_inbox(self, tool, monkeypatch):
        """Leerer Posteingang → count=0, leere Liste."""
        monkeypatch.setenv("EMAIL_BACKEND", "smtp")
        with patch("utils.smtp_email.read_emails_smtp", new_callable=AsyncMock, return_value=[]):
            result = tool.read_emails()
        assert result["success"] is True
        assert result["count"] == 0
        assert result["emails"] == []

    def test_read_smtp_exception(self, tool, monkeypatch):
        """IMAP-Fehler → success=False mit Fehlermeldung."""
        monkeypatch.setenv("EMAIL_BACKEND", "smtp")
        with patch("utils.smtp_email.read_emails_smtp",
                   new_callable=AsyncMock, side_effect=Exception("IMAP connection refused")):
            result = tool.read_emails()
        assert result["success"] is False
        assert "IMAP connection refused" in result["error"]

    def test_read_msgraph_success(self, tool, monkeypatch):
        """Graph-Backend: 1 Nachricht → Felder korrekt geparst."""
        monkeypatch.setenv("EMAIL_BACKEND", "msgraph")
        mock_resp = MagicMock(status_code=200)
        mock_resp.json.return_value = {"value": [{
            "id": "abc123",
            "subject": "Graph Mail",
            "from": {"emailAddress": {"name": "Sender", "address": "s@example.com"}},
            "toRecipients": [{"emailAddress": {"address": "timus@test.com"}}],
            "receivedDateTime": "2026-03-07T10:00:00Z",
            "body": {"contentType": "text", "content": "Body content"},
            "bodyPreview": "Body content",
            "isRead": False,
        }]}
        with patch("requests.get", return_value=mock_resp):
            result = tool.read_emails(limit=5)
        assert result["success"] is True
        assert result["count"] == 1
        assert result["emails"][0]["subject"] == "Graph Mail"
        assert result["emails"][0]["is_read"] is False


# ── get_email_status ──────────────────────────────────────────────────────────

class TestGetEmailStatus:

    def test_status_resend_ok(self, tool, monkeypatch):
        monkeypatch.setenv("EMAIL_BACKEND", "resend")
        monkeypatch.setenv("RESEND_API_KEY", "re_test")
        monkeypatch.setenv("RESEND_FROM", "Timus <timus@example.com>")
        result = tool.get_email_status()
        assert result["success"] is True
        assert result["authenticated"] is True
        assert result["backend"] == "resend"
        assert "timus@example.com" in result["address"]

    def test_status_smtp_ok(self, tool, monkeypatch):
        monkeypatch.setenv("EMAIL_BACKEND", "smtp")
        monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
        monkeypatch.setenv("SMTP_PORT", "465")
        monkeypatch.setenv("SMTP_USER", "timus@example.com")
        monkeypatch.setenv("SMTP_PASSWORD", "secret")
        result = tool.get_email_status()
        assert result["success"] is True
        assert result["authenticated"] is True
        assert result["backend"] == "smtp"
        assert result["address"] == "timus@example.com"

    def test_status_graph_ok(self, tool):
        """Graph /me antwortet 200 → graph_ok=True, token_ok=True, Adresse korrekt."""
        os.environ["EMAIL_BACKEND"] = "msgraph"
        mock_resp = MagicMock(status_code=200)
        mock_resp.json.return_value = {
            "mail": "timus@test.com",
            "displayName": "Timus Test",
        }
        with patch("requests.get", return_value=mock_resp):
            result = tool.get_email_status()
        assert result["success"] is True
        assert result["authenticated"] is True
        assert result["graph_ok"] is True
        assert result["token_ok"] is True
        assert result["address"] == "timus@test.com"

    def test_status_graph_401(self, tool):
        """Graph gibt 401 zurück → graph_ok=False, aber token_ok=True (Token war vorhanden)."""
        os.environ["EMAIL_BACKEND"] = "msgraph"
        mock_resp = MagicMock(status_code=401)
        mock_resp.text = "Unauthorized"
        with patch("requests.get", return_value=mock_resp):
            result = tool.get_email_status()
        assert result["success"] is False
        assert result["graph_ok"] is False
        assert result["token_ok"] is True

    def test_status_no_token(self, tool):
        """RuntimeError aus _get_access_token → token_ok=False."""
        os.environ["EMAIL_BACKEND"] = "msgraph"
        with patch.object(tool, "_get_access_token",
                          side_effect=RuntimeError("Kein OAuth2-Token vorhanden.")):
            result = tool.get_email_status()
        assert result["success"] is False
        assert result["token_ok"] is False

    def test_status_missing_client_id(self, tool):
        """Fehlende Client-ID → RuntimeError → success=False."""
        os.environ["EMAIL_BACKEND"] = "msgraph"
        with patch.object(tool, "_get_access_token",
                          side_effect=RuntimeError("TIMUS_GRAPH_CLIENT_ID fehlt in .env")):
            result = tool.get_email_status()
        assert result["success"] is False
        assert "CLIENT_ID" in result["error"] or "error" in result


# ── _attachment_artifact ──────────────────────────────────────────────────────

class TestAttachmentArtifact:

    def test_pdf_type_and_mime(self, tool, tmp_path):
        """PDF → type='pdf', mime='application/pdf', source='email_tool'."""
        f = tmp_path / "report.pdf"
        f.write_bytes(b"%PDF-1.4 fake")
        a = tool._attachment_artifact(str(f))
        assert a["type"] == "pdf"
        assert a["mime"] == "application/pdf"
        assert a["source"] == "email_tool"
        assert a["origin"] == "tool"

    def test_image_png(self, tool, tmp_path):
        """PNG → type='image'."""
        f = tmp_path / "screenshot.png"
        f.write_bytes(b"\x89PNG fake")
        a = tool._attachment_artifact(str(f))
        assert a["type"] == "image"
        assert "png" in a["mime"]

    def test_markdown_document(self, tool, tmp_path):
        """Markdown → type='document'."""
        f = tmp_path / "notes.md"
        f.write_text("# Notes")
        a = tool._attachment_artifact(str(f))
        assert a["type"] == "document"

    def test_csv_generic_file(self, tool, tmp_path):
        """CSV → type='file', label enthält Dateinamen."""
        f = tmp_path / "data.csv"
        f.write_text("a,b,c\n1,2,3")
        a = tool._attachment_artifact(str(f))
        assert a["type"] == "file"
        assert a["label"] == "data.csv"
