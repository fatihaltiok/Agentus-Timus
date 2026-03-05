"""
utils/smtp_email.py

SMTP/IMAP-Backend für M14 E-Mail-Autonomie.
Konfiguration via ENV: SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD, IMAP_HOST
"""

import email as email_lib
import imaplib
import logging
import os
import smtplib
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import List, Optional

log = logging.getLogger("SmtpEmail")


def _smtp_config() -> dict:
    return {
        "host": os.getenv("SMTP_HOST", "smtp.gmail.com"),
        "port": int(os.getenv("SMTP_PORT", "465")),
        "user": os.getenv("SMTP_USER", ""),
        "password": os.getenv("SMTP_PASSWORD", ""),
    }


def _imap_config() -> dict:
    return {
        "host": os.getenv("IMAP_HOST", "imap.gmail.com"),
        "port": int(os.getenv("IMAP_PORT", "993")),
        "user": os.getenv("SMTP_USER", ""),
        "password": os.getenv("SMTP_PASSWORD", ""),
    }


async def send_email_smtp(
    to: str,
    subject: str,
    body: str,
    html_body: Optional[str] = None,
) -> bool:
    """
    Sendet eine E-Mail via SMTP_SSL.

    Args:
        to: Empfänger-Adresse
        subject: Betreff
        body: Plaintext-Body
        html_body: Optional HTML-Body

    Returns:
        True wenn erfolgreich
    """
    cfg = _smtp_config()
    if not cfg["user"] or not cfg["password"]:
        log.warning("SMTP: SMTP_USER oder SMTP_PASSWORD fehlt")
        return False

    msg = MIMEMultipart("alternative") if html_body else MIMEMultipart()
    msg["From"] = cfg["user"]
    msg["To"] = to
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain", "utf-8"))
    if html_body:
        msg.attach(MIMEText(html_body, "html", "utf-8"))

    try:
        context = ssl.create_default_context()
        with smtplib.SMTP_SSL(cfg["host"], cfg["port"], context=context) as server:
            server.login(cfg["user"], cfg["password"])
            server.sendmail(cfg["user"], to, msg.as_string())
        log.info("SMTP: E-Mail an %s gesendet (Betreff: %s)", to, subject)
        return True
    except smtplib.SMTPAuthenticationError as e:
        log.error("SMTP: Authentifizierungsfehler: %s", e)
        return False
    except smtplib.SMTPException as e:
        log.error("SMTP: Sendefehler: %s", e)
        return False
    except Exception as e:
        log.error("SMTP: Unbekannter Fehler: %s", e)
        return False


async def read_emails_smtp(limit: int = 10, unread_only: bool = False) -> List[dict]:
    """
    Liest E-Mails via IMAP_SSL.

    Args:
        limit: Maximale Anzahl E-Mails
        unread_only: Nur ungelesene E-Mails

    Returns:
        Liste von E-Mail-Dicts (from, subject, date, body_preview)
    """
    cfg = _imap_config()
    if not cfg["user"] or not cfg["password"]:
        log.warning("IMAP: SMTP_USER oder SMTP_PASSWORD fehlt")
        return []

    results = []
    try:
        with imaplib.IMAP4_SSL(cfg["host"], cfg["port"]) as mail:
            mail.login(cfg["user"], cfg["password"])
            mail.select("INBOX")

            search_criteria = "(UNSEEN)" if unread_only else "ALL"
            _, data = mail.search(None, search_criteria)
            ids = data[0].split()
            ids = ids[-limit:] if len(ids) > limit else ids
            ids = list(reversed(ids))  # Neueste zuerst

            for num in ids:
                _, msg_data = mail.fetch(num, "(RFC822)")
                if not msg_data or not msg_data[0]:
                    continue
                raw = msg_data[0][1]
                if not isinstance(raw, bytes):
                    continue
                parsed = email_lib.message_from_bytes(raw)

                body_preview = ""
                if parsed.is_multipart():
                    for part in parsed.walk():
                        if part.get_content_type() == "text/plain":
                            payload = part.get_payload(decode=True)
                            if payload:
                                body_preview = payload.decode("utf-8", errors="replace")[:300]
                            break
                else:
                    payload = parsed.get_payload(decode=True)
                    if payload:
                        body_preview = payload.decode("utf-8", errors="replace")[:300]

                results.append({
                    "from": parsed.get("From", ""),
                    "subject": parsed.get("Subject", ""),
                    "date": parsed.get("Date", ""),
                    "body_preview": body_preview,
                    "message_id": parsed.get("Message-ID", ""),
                })

    except imaplib.IMAP4.error as e:
        log.error("IMAP: Fehler: %s", e)
    except Exception as e:
        log.error("IMAP: Unbekannter Fehler: %s", e)

    return results
