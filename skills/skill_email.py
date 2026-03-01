# skills/skill_email.py
"""
Timus E-Mail-Skill — dünner Wrapper um das email_tool MCP-Modul.

Alle Logik (SMTP/IMAP) liegt in tools/email_tool/tool.py.
Dieser Skill delegiert direkt über registry_v2 und vermeidet Codeduplikation.
"""

from typing import Any, Dict, List, Optional

from tools.tool_registry_v2 import registry_v2


def send_email(
    to: str,
    subject: str,
    body: str,
    cc: Optional[str] = None,
    bcc: Optional[str] = None,
    html_body: Optional[str] = None,
    reply_to: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Sendet eine E-Mail über das Timus-Outlook-Konto.

    Parameters
    ----------
    to         : Empfänger-Adresse (eine oder kommagetrennt)
    subject    : Betreff
    body       : Plaintext-Body
    cc         : CC-Adresse(n), kommagetrennt (optional)
    bcc        : BCC-Adresse(n), kommagetrennt (optional)
    html_body  : HTML-Alternativtext (optional)
    reply_to   : Reply-To Header (optional)

    Returns
    -------
    Dict mit {success, to, subject, message} oder {success, error}
    """
    params: Dict[str, Any] = {"to": to, "subject": subject, "body": body}
    if cc:
        params["cc"] = cc
    if bcc:
        params["bcc"] = bcc
    if html_body:
        params["html_body"] = html_body
    if reply_to:
        params["reply_to"] = reply_to
    return registry_v2.execute("send_email", **params)


def read_emails(
    mailbox: str = "INBOX",
    limit: int = 10,
    unread_only: bool = False,
    search: str = "",
) -> Dict[str, Any]:
    """
    Liest E-Mails aus dem Postfach.

    Parameters
    ----------
    mailbox     : Postfach (Standard: INBOX)
    limit       : Maximale Anzahl E-Mails (Standard: 10)
    unread_only : Nur ungelesene zurückgeben
    search      : IMAP-Suchbegriff (z.B. 'FROM fatih')

    Returns
    -------
    Dict mit {success, mailbox, count, emails} oder {success, error}
    """
    return registry_v2.execute(
        "read_emails",
        mailbox=mailbox,
        limit=limit,
        unread_only=unread_only,
        search=search,
    )


def get_email_status() -> Dict[str, Any]:
    """
    Prüft ob SMTP und IMAP erreichbar sind.

    Returns
    -------
    Dict mit {smtp_ok, imap_ok, address, display_name, ...}
    """
    return registry_v2.execute("get_email_status")
