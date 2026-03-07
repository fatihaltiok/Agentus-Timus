"""
utils/resend_email.py

Resend-Backend für M14 E-Mail-Autonomie.
Kein Microsoft-Konto, kein Bot-Blocking.

Konfiguration via ENV:
    RESEND_API_KEY      = re_xxxxxxxxxxxx  (von resend.com)
    RESEND_FROM         = Timus <timus@deinedomain.com>
                          Fallback: onboarding@resend.dev (nur für Tests)

IMAP-Empfang: Resend ist reiner Versanddienst — Empfang läuft weiter
über IMAP_HOST/IMAP_PORT/SMTP_USER/SMTP_PASSWORD (z.B. Gmail IMAP).
"""

import base64
import logging
import os
from pathlib import Path
from typing import List, Optional

import httpx

log = logging.getLogger("ResendEmail")

_RESEND_API = "https://api.resend.com/emails"


def _api_key() -> str:
    return os.getenv("RESEND_API_KEY", "")


def _from_address() -> str:
    return os.getenv("RESEND_FROM", "Timus <onboarding@resend.dev>")


async def send_email_resend(
    to: str,
    subject: str,
    body: str,
    html_body: Optional[str] = None,
    attachment_path: Optional[str] = None,
) -> bool:
    """
    Sendet eine E-Mail via Resend REST-API.

    Args:
        to:              Empfänger-Adresse
        subject:         Betreff
        body:            Plaintext-Body
        html_body:       Optional HTML-Body (Priorität über Plaintext)
        attachment_path: Optionaler Pfad zu einer Anhang-Datei (absolut oder relativ)

    Returns:
        True wenn erfolgreich (HTTP 200/201)
    """
    api_key = _api_key()
    if not api_key:
        log.warning("Resend: RESEND_API_KEY fehlt in .env")
        return False

    payload: dict = {
        "from": _from_address(),
        "to": [to],
        "subject": subject,
    }
    if html_body:
        payload["html"] = html_body
    else:
        payload["text"] = body

    if attachment_path:
        path = Path(attachment_path)
        if not path.is_absolute():
            path = Path(__file__).resolve().parent.parent / attachment_path
        if path.exists():
            content_b64 = base64.b64encode(path.read_bytes()).decode("utf-8")
            payload["attachments"] = [{"filename": path.name, "content": content_b64}]
            log.info("Resend: Anhang '%s' (%d Bytes) wird mitgesendet", path.name, path.stat().st_size)
        else:
            log.warning("Resend: Anhang-Datei nicht gefunden: %s — wird ohne Anhang gesendet", attachment_path)

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                _RESEND_API,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
        if resp.status_code in (200, 201):
            data = resp.json()
            log.info("Resend: E-Mail an %s gesendet (id=%s)", to, data.get("id"))
            return True
        else:
            log.error("Resend: API-Fehler %s — %s", resp.status_code, resp.text)
            return False
    except httpx.TimeoutException:
        log.error("Resend: Timeout beim API-Aufruf")
        return False
    except Exception as e:
        log.error("Resend: Unbekannter Fehler: %s", e)
        return False


async def read_emails_resend(limit: int = 10, unread_only: bool = False) -> List[dict]:
    """
    Resend ist ein reiner Versanddienst — kein IMAP.
    Empfang läuft über das konfigurierte IMAP-Backend (smtp_email.py).
    Diese Funktion delegiert transparent an read_emails_smtp().
    """
    from utils.smtp_email import read_emails_smtp
    return await read_emails_smtp(limit=limit, unread_only=unread_only)
