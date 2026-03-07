"""
tests/test_send_email_attachment.py

Tests für attachment_path-Unterstützung in send_email (alle 3 Backends).
"""
import base64
import os
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ── 1. Resend-Backend ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_resend_sends_attachment_base64():
    """Resend-Payload enthält 'attachments' mit korrektem base64-Inhalt."""
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
        f.write(b"%PDF-1.4 test")
        tmp = f.name

    try:
        expected_b64 = base64.b64encode(b"%PDF-1.4 test").decode("utf-8")

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"id": "abc123"}

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client_cls.return_value.__aenter__.return_value = mock_client
            mock_client.post.return_value = mock_resp

            with patch.dict(os.environ, {"RESEND_API_KEY": "re_test123"}):
                from utils.resend_email import send_email_resend
                ok = await send_email_resend(
                    to="test@example.com",
                    subject="Test",
                    body="Hallo",
                    attachment_path=tmp,
                )

        assert ok is True
        call_kwargs = mock_client.post.call_args
        payload = call_kwargs.kwargs.get("json") or call_kwargs.args[1] if len(call_kwargs.args) > 1 else call_kwargs.kwargs["json"]
        assert "attachments" in payload
        assert payload["attachments"][0]["content"] == expected_b64
        assert payload["attachments"][0]["filename"] == Path(tmp).name
    finally:
        os.unlink(tmp)


@pytest.mark.asyncio
async def test_resend_no_attachment_key_when_none():
    """Ohne attachment_path enthält Resend-Payload kein 'attachments'-Key."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"id": "xyz"}

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client_cls.return_value.__aenter__.return_value = mock_client
        mock_client.post.return_value = mock_resp

        with patch.dict(os.environ, {"RESEND_API_KEY": "re_test123"}):
            from utils.resend_email import send_email_resend
            ok = await send_email_resend(
                to="test@example.com",
                subject="Test",
                body="Hallo",
            )

    assert ok is True
    call_kwargs = mock_client.post.call_args
    payload = call_kwargs.kwargs.get("json") or call_kwargs.kwargs["json"]
    assert "attachments" not in payload


@pytest.mark.asyncio
async def test_resend_missing_file_sends_without_attachment(caplog):
    """Nicht existierende Anhang-Datei → E-Mail wird trotzdem gesendet (kein 'attachments')."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"id": "xyz"}

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client_cls.return_value.__aenter__.return_value = mock_client
        mock_client.post.return_value = mock_resp

        with patch.dict(os.environ, {"RESEND_API_KEY": "re_test123"}):
            import logging
            with caplog.at_level(logging.WARNING, logger="ResendEmail"):
                from utils.resend_email import send_email_resend
                ok = await send_email_resend(
                    to="test@example.com",
                    subject="Test",
                    body="Hallo",
                    attachment_path="/nichtexistent/datei.pdf",
                )

    assert ok is True
    call_kwargs = mock_client.post.call_args
    payload = call_kwargs.kwargs.get("json") or call_kwargs.kwargs["json"]
    assert "attachments" not in payload
    assert "nicht gefunden" in caplog.text.lower() or "not found" in caplog.text.lower() or caplog.text != ""


# ── 2. SMTP-Backend ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_smtp_uses_mixed_multipart_with_attachment():
    """SMTP-Nachricht nutzt MIMEMultipart('mixed') wenn Anhang vorhanden."""
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
        f.write(b"%PDF-1.4 test content")
        tmp = f.name

    try:
        sent_messages = []

        class FakeSMTP:
            def __init__(self, *args, **kwargs): pass
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def login(self, user, pw): pass
            def sendmail(self, from_, to, msg_str):
                sent_messages.append(msg_str)

        with patch("smtplib.SMTP_SSL", FakeSMTP):
            with patch("ssl.create_default_context", return_value=MagicMock()):
                with patch.dict(os.environ, {"SMTP_USER": "test@gmail.com", "SMTP_PASSWORD": "secret"}):
                    from utils.smtp_email import send_email_smtp
                    ok = await send_email_smtp(
                        to="empf@example.com",
                        subject="SMTP Test",
                        body="Plaintext",
                        attachment_path=tmp,
                    )

        assert ok is True
        assert len(sent_messages) == 1
        msg_str = sent_messages[0]
        # MIMEMultipart("mixed") → Content-Type: multipart/mixed
        assert "multipart/mixed" in msg_str
        # Anhang vorhanden → Content-Disposition: attachment
        assert "Content-Disposition: attachment" in msg_str
    finally:
        os.unlink(tmp)


@pytest.mark.asyncio
async def test_smtp_attachment_filename_in_message():
    """SMTP-Nachricht enthält den korrekten Dateinamen im Content-Disposition Header."""
    with tempfile.NamedTemporaryFile(suffix=".pdf", prefix="bericht_", delete=False) as f:
        f.write(b"fake pdf data")
        tmp = f.name

    try:
        sent_messages = []

        class FakeSMTP:
            def __init__(self, *args, **kwargs): pass
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def login(self, user, pw): pass
            def sendmail(self, from_, to, msg_str):
                sent_messages.append(msg_str)

        with patch("smtplib.SMTP_SSL", FakeSMTP):
            with patch("ssl.create_default_context", return_value=MagicMock()):
                with patch.dict(os.environ, {"SMTP_USER": "u@x.com", "SMTP_PASSWORD": "pw"}):
                    from utils.smtp_email import send_email_smtp
                    await send_email_smtp(
                        to="x@y.com",
                        subject="S",
                        body="B",
                        attachment_path=tmp,
                    )

        filename = Path(tmp).name
        assert filename in sent_messages[0]
    finally:
        os.unlink(tmp)


@pytest.mark.asyncio
async def test_smtp_no_attachment_uses_alternative_only():
    """Ohne Anhang: SMTP nutzt nur multipart/alternative (kein 'mixed' nötig)."""
    sent_messages = []

    class FakeSMTP:
        def __init__(self, *args, **kwargs): pass
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def login(self, user, pw): pass
        def sendmail(self, from_, to, msg_str):
            sent_messages.append(msg_str)

    with patch("smtplib.SMTP_SSL", FakeSMTP):
        with patch("ssl.create_default_context", return_value=MagicMock()):
            with patch.dict(os.environ, {"SMTP_USER": "u@x.com", "SMTP_PASSWORD": "pw"}):
                from utils.smtp_email import send_email_smtp
                ok = await send_email_smtp(
                    to="x@y.com",
                    subject="S",
                    body="B",
                )

    assert ok is True
    assert "Content-Disposition: attachment" not in sent_messages[0]


# ── 3. Microsoft Graph Backend ────────────────────────────────────────────────

def test_graph_attachment_payload_structure():
    """Graph-API Payload enthält fileAttachment mit korrektem odata.type."""
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
        f.write(b"mock pdf bytes")
        tmp = f.name

    try:
        expected_b64 = base64.b64encode(b"mock pdf bytes").decode("utf-8")
        captured_payloads = []

        def fake_post(url, headers, json, timeout):
            captured_payloads.append(json)
            mock_resp = MagicMock()
            mock_resp.status_code = 202
            return mock_resp

        with patch("requests.post", side_effect=fake_post):
            with patch("tools.email_tool.tool._get_access_token", return_value="fake_token"):
                with patch.dict(os.environ, {"EMAIL_BACKEND": "msgraph"}):
                    from tools.email_tool.tool import send_email
                    result = send_email(
                        to="test@example.com",
                        subject="Graph Test",
                        body="Hallo",
                        attachment_path=tmp,
                    )

        assert result["success"] is True
        payload = captured_payloads[0]
        attachments = payload["message"]["attachments"]
        assert len(attachments) == 1
        att = attachments[0]
        assert att["@odata.type"] == "#microsoft.graph.fileAttachment"
        assert att["name"] == Path(tmp).name
        assert att["contentBytes"] == expected_b64
    finally:
        os.unlink(tmp)


def test_graph_no_attachment_key_without_file():
    """Graph-Payload ohne attachment_path enthält kein 'attachments'-Key."""
    captured_payloads = []

    def fake_post(url, headers, json, timeout):
        captured_payloads.append(json)
        mock_resp = MagicMock()
        mock_resp.status_code = 202
        return mock_resp

    with patch("requests.post", side_effect=fake_post):
        with patch("tools.email_tool.tool._get_access_token", return_value="fake_token"):
            with patch.dict(os.environ, {"EMAIL_BACKEND": "msgraph"}):
                from tools.email_tool.tool import send_email
                result = send_email(
                    to="test@example.com",
                    subject="Kein Anhang",
                    body="Text",
                )

    assert result["success"] is True
    assert "attachments" not in captured_payloads[0]["message"]


def test_graph_result_contains_attachment_filename():
    """Erfolgreicher Versand mit Anhang → result['attachment'] enthält Dateinamen."""
    with tempfile.NamedTemporaryFile(suffix=".pdf", prefix="report_", delete=False) as f:
        f.write(b"data")
        tmp = f.name

    try:
        def fake_post(url, headers, json, timeout):
            mock_resp = MagicMock()
            mock_resp.status_code = 202
            return mock_resp

        with patch("requests.post", side_effect=fake_post):
            with patch("tools.email_tool.tool._get_access_token", return_value="fake_token"):
                with patch.dict(os.environ, {"EMAIL_BACKEND": "msgraph"}):
                    from tools.email_tool.tool import send_email
                    result = send_email(
                        to="x@y.com",
                        subject="S",
                        body="B",
                        attachment_path=tmp,
                    )

        assert result["success"] is True
        assert "attachment" in result
        assert result["attachment"] == Path(tmp).name
    finally:
        os.unlink(tmp)


# ── 4. Tool-Layer: Pfad-Auflösung ─────────────────────────────────────────────

def test_tool_resolves_relative_path():
    """Relativer Pfad wird gegen PROJECT_ROOT aufgelöst."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Simuliere results/ Ordner unter _PROJECT_ROOT
        results_dir = Path(tmpdir) / "results"
        results_dir.mkdir()
        pdf = results_dir / "test.pdf"
        pdf.write_bytes(b"pdf")

        def fake_post(url, headers, json, timeout):
            mock_resp = MagicMock()
            mock_resp.status_code = 202
            return mock_resp

        with patch("requests.post", side_effect=fake_post):
            with patch("tools.email_tool.tool._get_access_token", return_value="fake_token"):
                with patch("tools.email_tool.tool._PROJECT_ROOT", Path(tmpdir)):
                    with patch.dict(os.environ, {"EMAIL_BACKEND": "msgraph"}):
                        from tools.email_tool import tool as email_module
                        # _PROJECT_ROOT patchen
                        original_root = email_module._PROJECT_ROOT
                        email_module._PROJECT_ROOT = Path(tmpdir)
                        try:
                            result = email_module.send_email(
                                to="x@y.com",
                                subject="S",
                                body="B",
                                attachment_path="results/test.pdf",
                            )
                        finally:
                            email_module._PROJECT_ROOT = original_root

        assert result["success"] is True
        assert result.get("attachment") == "test.pdf"


def test_tool_missing_attachment_graceful():
    """Nicht vorhandener Anhang → E-Mail wird trotzdem versendet (success=True)."""
    def fake_post(url, headers, json, timeout):
        mock_resp = MagicMock()
        mock_resp.status_code = 202
        return mock_resp

    with patch("requests.post", side_effect=fake_post):
        with patch("tools.email_tool.tool._get_access_token", return_value="fake_token"):
            with patch.dict(os.environ, {"EMAIL_BACKEND": "msgraph"}):
                from tools.email_tool.tool import send_email
                result = send_email(
                    to="x@y.com",
                    subject="S",
                    body="B",
                    attachment_path="/tmp/existiert_nicht_xyz_abc.pdf",
                )

    assert result["success"] is True
    assert "attachment" not in result
