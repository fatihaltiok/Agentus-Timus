# tools/email_tool/tool.py
"""
Timus E-Mail-Tool — Microsoft Graph API (OAuth2, kein SMTP/IMAP Basic Auth).

Drei MCP-Tools:
  - send_email       — E-Mail versenden via Graph /me/sendMail
  - read_emails      — Posteingang lesen via Graph /me/mailFolders/.../messages
  - get_email_status — OAuth2-Token + Graph-Verbindung prüfen

Auth-Flow:
  1. Einmalig: python utils/timus_mail_oauth.py  → Browser-Login → Token-Cache
  2. Danach: MSAL liest Cache und erneuert Token automatisch (Refresh Token)

Konfiguration (.env):
  TIMUS_EMAIL              = timus.assistent@outlook.com
  TIMUS_GRAPH_CLIENT_ID    = <Azure App Client-ID>
  TIMUS_GRAPH_AUTHORITY    = https://login.microsoftonline.com/consumers
  TIMUS_GRAPH_TOKEN_CACHE  = data/timus_token_cache.bin
"""

from __future__ import annotations

import logging
import mimetypes
import os
import textwrap
from pathlib import Path
from typing import Any, Dict, List, Optional

import json
import time as _time
import requests
from dotenv import load_dotenv
from tools.tool_registry_v2 import tool, ToolParameter as P, ToolCategory as C

load_dotenv()
log = logging.getLogger("email_tool")

# ── Konfiguration ─────────────────────────────────────────────────────────────
_EMAIL       = os.getenv("TIMUS_EMAIL", "")
_DISPLAY     = os.getenv("TIMUS_EMAIL_DISPLAY_NAME", "Timus Agent")
_CLIENT_ID   = os.getenv("TIMUS_GRAPH_CLIENT_ID", "")
_AUTHORITY   = os.getenv("TIMUS_GRAPH_AUTHORITY", "https://login.microsoftonline.com/consumers")
_CACHE_PATH  = Path(os.getenv("TIMUS_GRAPH_TOKEN_CACHE", "data/timus_token_cache.bin"))
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

_GRAPH_BASE  = "https://graph.microsoft.com/v1.0"
_SCOPES      = "https://graph.microsoft.com/Mail.Read https://graph.microsoft.com/Mail.Send https://graph.microsoft.com/User.Read offline_access"
_TENANTS     = ["80a8117b-bc12-49e6-a362-4e172f0f4e37", "consumers", "common"]


# ── Token-Verwaltung (raw HTTP, kein MSAL) ────────────────────────────────────

def _load_cache() -> dict:
    cache_file = _PROJECT_ROOT / _CACHE_PATH
    if cache_file.exists():
        try:
            return json.loads(cache_file.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def _save_cache(token_data: dict) -> None:
    cache_file = _PROJECT_ROOT / _CACHE_PATH
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    cache = {
        "access_token":  token_data.get("access_token", ""),
        "refresh_token": token_data.get("refresh_token", ""),
        "expires_at":    _time.time() + int(token_data.get("expires_in", 3600)),
        "token_type":    token_data.get("token_type", "Bearer"),
    }
    cache_file.write_text(json.dumps(cache, indent=2), encoding="utf-8")


def _refresh_access_token(refresh_token: str) -> str | None:
    """Erneuert Access-Token via Refresh-Token. Gibt neuen Access-Token zurück."""
    for tenant in _TENANTS:
        try:
            resp = requests.post(
                f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token",
                data={
                    "client_id":     _CLIENT_ID,
                    "grant_type":    "refresh_token",
                    "refresh_token": refresh_token,
                    "scope":         _SCOPES,
                },
                timeout=15,
            )
            data = resp.json()
            if "access_token" in data:
                _save_cache(data)
                return data["access_token"]
        except Exception:
            continue
    return None


def _get_access_token() -> str:
    """
    Gibt einen gültigen Access-Token zurück.
    Liest Token-Cache; erneuert via Refresh-Token automatisch.
    Wirft RuntimeError wenn kein Token vorhanden (→ Autorisierung nötig).
    """
    if not _CLIENT_ID:
        raise RuntimeError("TIMUS_GRAPH_CLIENT_ID fehlt in .env")

    cache = _load_cache()
    if not cache.get("access_token"):
        raise RuntimeError(
            "Kein OAuth2-Token vorhanden. Bitte einmalig ausführen:\n"
            "  python utils/timus_mail_oauth.py"
        )

    # Access-Token noch gültig?
    if _time.time() < cache.get("expires_at", 0) - 60:
        return cache["access_token"]

    # Abgelaufen → via Refresh-Token erneuern
    refresh_token = cache.get("refresh_token")
    if refresh_token:
        new_token = _refresh_access_token(refresh_token)
        if new_token:
            return new_token

    raise RuntimeError(
        "Token abgelaufen und Erneuerung fehlgeschlagen.\n"
        "Bitte erneut autorisieren: python utils/timus_mail_oauth.py"
    )


def _graph_headers() -> Dict[str, str]:
    return {
        "Authorization": f"Bearer {_get_access_token()}",
        "Content-Type": "application/json",
    }


def _attachment_artifact(path: str) -> Dict[str, Any]:
    attachment_path = Path(path).resolve()
    mime_type = mimetypes.guess_type(str(attachment_path))[0] or "application/octet-stream"
    suffix = attachment_path.suffix.lower()
    if suffix == ".pdf":
        artifact_type = "pdf"
    elif suffix in {".png", ".jpg", ".jpeg", ".webp", ".gif"}:
        artifact_type = "image"
    elif suffix in {".doc", ".docx", ".md", ".txt"}:
        artifact_type = "document"
    else:
        artifact_type = "file"
    return {
        "type": artifact_type,
        "path": str(attachment_path),
        "label": attachment_path.name,
        "mime": mime_type,
        "source": "email_tool",
        "origin": "tool",
    }


def _resolve_attachment_path(attachment_path: Optional[str]) -> tuple[Optional[str], Optional[str]]:
    """Löst einen optionalen Anhangspfad auf.

    Returns:
        (resolved_path, error_message)
    """
    if not attachment_path:
        return None, None

    from pathlib import Path as _Path

    path = _Path(attachment_path)
    if not path.is_absolute():
        path = _PROJECT_ROOT / attachment_path
    if not path.exists():
        return None, f"Anhang nicht gefunden: {attachment_path}"
    return str(path), None


# ── MCP-Tools ─────────────────────────────────────────────────────────────────

@tool(
    name="send_email",
    description=(
        "Sendet eine E-Mail im Namen von Timus. "
        "Backend wird via EMAIL_BACKEND gesteuert: resend (Standard), smtp oder msgraph. "
        "Unterstützt optionalen Datei-Anhang (z.B. PDF-Report)."
    ),
    parameters=[
        P("to",              "string", "Empfänger-Adresse (eine oder kommagetrennt)",                   True),
        P("subject",         "string", "Betreff der E-Mail",                                            True),
        P("body",            "string", "Plaintext-Body der E-Mail",                                     True),
        P("cc",              "string", "CC-Adresse(n), kommagetrennt",                                  False),
        P("bcc",             "string", "BCC-Adresse(n), kommagetrennt",                                 False),
        P("html_body",       "string", "HTML-Alternativtext (optional)",                                False),
        P("reply_to",        "string", "Reply-To Header (optional)",                                    False),
        P("attachment_path", "string", "Pfad zur Anhang-Datei (absolut oder relativ zu /timus/results/)", False),
    ],
    capabilities=["email", "communication", "send_email"],
    category=C.DOCUMENT,
)
def send_email(
    to: str,
    subject: str,
    body: str,
    cc: Optional[str] = None,
    bcc: Optional[str] = None,
    html_body: Optional[str] = None,
    reply_to: Optional[str] = None,
    attachment_path: Optional[str] = None,
) -> Dict[str, Any]:
    """Versendet eine E-Mail — Backend via EMAIL_BACKEND (resend/smtp/msgraph)."""
    import base64

    backend = os.getenv("EMAIL_BACKEND", "resend").lower()

    # Anhang-Pfad auflösen (relativ → absolut ab Projektroot)
    resolved_attachment, attachment_error = _resolve_attachment_path(attachment_path)
    if attachment_error:
        log.error("send_email: %s — Versand wird abgebrochen", attachment_error)
        return {
            "success": False,
            "error": attachment_error,
            "attachment_required": True,
            "artifacts": [],
        }
    if resolved_attachment:
        attachment_file = Path(resolved_attachment)
        log.info(
            "send_email: Anhang gefunden: %s (%d Bytes)",
            attachment_file.name,
            attachment_file.stat().st_size,
        )

    # ── Resend oder SMTP (async → sync wrapper) ───────────────────────────────
    if backend in ("resend", "smtp"):
        import asyncio
        try:
            if backend == "resend":
                from utils.resend_email import send_email_resend
                ok = asyncio.run(send_email_resend(
                    to=to, subject=subject, body=body,
                    cc=cc, bcc=bcc,
                    html_body=html_body, reply_to=reply_to,
                    attachment_path=resolved_attachment,
                ))
            else:
                from utils.smtp_email import send_email_smtp
                ok = asyncio.run(send_email_smtp(
                    to=to, subject=subject, body=body,
                    cc=cc, bcc=bcc,
                    html_body=html_body, reply_to=reply_to,
                    attachment_path=resolved_attachment,
                ))
            if ok:
                log.info(f"E-Mail gesendet an {to} via {backend} | Betreff: {subject!r}")
                result = {"success": True, "to": to, "subject": subject,
                          "message": f"E-Mail erfolgreich an {to} gesendet ({backend}).",
                          "artifacts": []}
                if resolved_attachment:
                    from pathlib import Path as _Path
                    result["attachment"] = _Path(resolved_attachment).name
                    result["artifacts"] = [_attachment_artifact(resolved_attachment)]
                return result
            else:
                return {"success": False, "error": f"{backend}: Sendefehler — Logs prüfen", "artifacts": []}
        except Exception as e:
            log.error(f"{backend} send_email Fehler: {e}", exc_info=True)
            return {"success": False, "error": str(e), "artifacts": []}

    # ── Microsoft Graph ───────────────────────────────────────────────────────
    try:
        content_type = "HTML" if html_body else "Text"
        content      = html_body if html_body else body

        payload: Dict[str, Any] = {
            "message": {
                "subject": subject,
                "body": {"contentType": content_type, "content": content},
                "toRecipients": _addr_list(to),
            },
            "saveToSentItems": True,
        }

        if cc:
            payload["message"]["ccRecipients"] = _addr_list(cc)
        if bcc:
            payload["message"]["bccRecipients"] = _addr_list(bcc)
        if reply_to:
            payload["message"]["replyTo"] = _addr_list(reply_to)

        # Anhang für Graph API (fileAttachment)
        if resolved_attachment:
            from pathlib import Path as _Path
            import mimetypes
            att_path = _Path(resolved_attachment)
            mime_type = mimetypes.guess_type(str(att_path))[0] or "application/octet-stream"
            content_bytes = base64.b64encode(att_path.read_bytes()).decode("utf-8")
            payload["message"]["attachments"] = [{
                "@odata.type": "#microsoft.graph.fileAttachment",
                "name": att_path.name,
                "contentType": mime_type,
                "contentBytes": content_bytes,
            }]

        resp = requests.post(
            f"{_GRAPH_BASE}/me/sendMail",
            headers=_graph_headers(),
            json=payload,
            timeout=30,
        )

        if resp.status_code in (202, 204):
            log.info(f"E-Mail gesendet an {to} via msgraph | Betreff: {subject!r}")
            result = {"success": True, "to": to, "subject": subject,
                      "message": f"E-Mail erfolgreich an {to} gesendet (msgraph).",
                      "artifacts": []}
            if resolved_attachment:
                from pathlib import Path as _Path
                result["attachment"] = _Path(resolved_attachment).name
                result["artifacts"] = [_attachment_artifact(resolved_attachment)]
            return result
        else:
            try:
                err_msg = resp.json().get("error", {}).get("message", resp.text[:300])
            except Exception:
                err_msg = resp.text[:300] or f"HTTP {resp.status_code}"
            log.error(f"Graph sendMail Fehler {resp.status_code}: {err_msg}")
            return {"success": False, "error": f"HTTP {resp.status_code} — {err_msg}", "artifacts": []}

    except RuntimeError as e:
        return {"success": False, "error": str(e), "artifacts": []}
    except requests.RequestException as e:
        log.error(f"Netzwerkfehler beim E-Mail-Versand: {e}")
        return {"success": False, "error": f"Netzwerkfehler: {e}", "artifacts": []}
    except Exception as e:
        log.error(f"Unerwarteter Fehler: {e}", exc_info=True)
        return {"success": False, "error": str(e), "artifacts": []}


@tool(
    name="read_emails",
    description=(
        "Liest E-Mails aus dem Postfach von Timus. "
        "Backend via EMAIL_BACKEND: resend/smtp nutzen IMAP, msgraph nutzt Graph API."
    ),
    parameters=[
        P("mailbox",     "string",  "Postfach (Standard: inbox)",                                          False, "inbox"),
        P("limit",       "integer", "Maximale Anzahl zurückgegebener E-Mails (Standard: 10)",              False, 10),
        P("unread_only", "boolean", "Nur ungelesene E-Mails zurückgeben",                                  False, False),
        P("search",      "string",  "Suchbegriff (z.B. 'fatih' oder 'subject:Test')",                     False, ""),
    ],
    capabilities=["email", "communication", "read_emails"],
    category=C.DOCUMENT,
)
def read_emails(
    mailbox: str = "inbox",
    limit: int = 10,
    unread_only: bool = False,
    search: str = "",
) -> Dict[str, Any]:
    """Liest E-Mails — Backend via EMAIL_BACKEND (resend/smtp → IMAP, msgraph → Graph)."""
    backend = os.getenv("EMAIL_BACKEND", "resend").lower()

    # ── IMAP (resend oder smtp) ───────────────────────────────────────────────
    if backend in ("resend", "smtp"):
        import asyncio
        try:
            from utils.smtp_email import read_emails_smtp
            raw = asyncio.run(read_emails_smtp(limit=limit, unread_only=unread_only))
            log.info(f"read_emails: {len(raw)} E-Mail(s) via IMAP gelesen")
            return {"success": True, "mailbox": "inbox", "count": len(raw), "emails": raw}
        except Exception as e:
            log.error(f"IMAP read_emails Fehler: {e}", exc_info=True)
            return {"success": False, "error": str(e)}

    # ── Microsoft Graph ───────────────────────────────────────────────────────
    try:
        params: Dict[str, Any] = {
            "$top":     min(limit, 50),
            "$orderby": "receivedDateTime desc",
            "$select":  "id,subject,from,toRecipients,receivedDateTime,bodyPreview,isRead,body",
        }
        filters = []
        if unread_only:
            filters.append("isRead eq false")
        if filters:
            params["$filter"] = " and ".join(filters)
        if search:
            params["$search"] = f'"{search}"'

        resp = requests.get(
            f"{_GRAPH_BASE}/me/mailFolders/{mailbox}/messages",
            headers=_graph_headers(),
            params=params,
            timeout=20,
        )
        if resp.status_code != 200:
            err = resp.json().get("error", {})
            return {"success": False, "error": f"{resp.status_code} — {err.get('message', resp.text)}"}

        raw    = resp.json().get("value", [])
        emails = [_parse_graph_message(m) for m in raw]
        log.info(f"read_emails: {len(emails)} E-Mail(s) via Graph gelesen")
        return {"success": True, "mailbox": mailbox, "count": len(emails), "emails": emails}

    except RuntimeError as e:
        return {"success": False, "error": str(e)}
    except requests.RequestException as e:
        log.error(f"Netzwerkfehler beim E-Mail-Lesen: {e}")
        return {"success": False, "error": f"Netzwerkfehler: {e}"}
    except Exception as e:
        log.error(f"Unerwarteter Fehler: {e}", exc_info=True)
        return {"success": False, "error": str(e)}


@tool(
    name="get_email_status",
    description=(
        "Prüft ob der OAuth2-Token gültig und Microsoft Graph erreichbar ist. "
        "Zeigt die konfigurierte E-Mail-Adresse und Token-Status."
    ),
    parameters=[],
    capabilities=["email", "communication", "status"],
    category=C.SYSTEM,
)
def get_email_status() -> Dict[str, Any]:
    """Prüft Backend-spezifischen E-Mail-Status."""
    backend = os.getenv("EMAIL_BACKEND", "resend").lower()

    if backend == "resend":
        api_key = os.getenv("RESEND_API_KEY", "")
        from_address = os.getenv("RESEND_FROM", "")
        ok = bool(api_key and from_address)
        return {
            "success": ok,
            "authenticated": ok,
            "backend": "resend",
            "address": from_address or _EMAIL or _DISPLAY,
            "display_name": _DISPLAY,
            "backend_ok": ok,
            "graph_ok": False,
            "token_ok": False,
            "error": "" if ok else "RESEND_API_KEY oder RESEND_FROM fehlt",
        }

    if backend == "smtp":
        smtp_user = os.getenv("SMTP_USER", "")
        smtp_password = os.getenv("SMTP_PASSWORD", "")
        smtp_host = os.getenv("SMTP_HOST", "")
        smtp_port = os.getenv("SMTP_PORT", "")
        ok = bool(smtp_user and smtp_password and smtp_host and smtp_port)
        return {
            "success": ok,
            "authenticated": ok,
            "backend": "smtp",
            "address": smtp_user or _EMAIL or _DISPLAY,
            "display_name": _DISPLAY,
            "backend_ok": ok,
            "graph_ok": False,
            "token_ok": False,
            "error": "" if ok else "SMTP_HOST/SMTP_PORT/SMTP_USER/SMTP_PASSWORD unvollständig",
        }

    try:
        token = _get_access_token()
        resp = requests.get(
            f"{_GRAPH_BASE}/me",
            headers={"Authorization": f"Bearer {token}"},
            timeout=10,
        )
        if resp.status_code == 200:
            me = resp.json()
            return {
                "success":      True,
                "authenticated": True,
                "backend":      "msgraph",
                "address":      me.get("mail") or me.get("userPrincipalName", _EMAIL),
                "display_name": me.get("displayName", _DISPLAY),
                "backend_ok":   True,
                "graph_ok":     True,
                "token_ok":     True,
            }
        else:
            return {
                "success":  False,
                "authenticated": False,
                "backend":  "msgraph",
                "backend_ok": False,
                "graph_ok": False,
                "token_ok": True,
                "error":    f"Graph /me: {resp.status_code} — {resp.text[:200]}",
            }
    except RuntimeError as e:
        return {
            "success":  False,
            "authenticated": False,
            "backend":  "msgraph",
            "backend_ok": False,
            "graph_ok": False,
            "token_ok": False,
            "error":    str(e),
        }
    except Exception as e:
        return {
            "success": False,
            "authenticated": False,
            "backend": "msgraph",
            "backend_ok": False,
            "graph_ok": False,
            "token_ok": False,
            "error": str(e),
        }


# ── Hilfsfunktionen ───────────────────────────────────────────────────────────

def _addr_list(addrs: str) -> List[Dict]:
    """Wandelt kommagetrennte Adressen in Graph-Format um."""
    return [
        {"emailAddress": {"address": a.strip()}}
        for a in addrs.split(",")
        if a.strip()
    ]


def _parse_graph_message(m: Dict) -> Dict[str, Any]:
    """Konvertiert eine Graph-API-Nachricht in ein kompaktes Dict."""
    sender = m.get("from", {}).get("emailAddress", {})
    body   = m.get("body", {}).get("content", m.get("bodyPreview", ""))
    # HTML-Tags entfernen wenn vorhanden
    if m.get("body", {}).get("contentType") == "html":
        import re
        body = re.sub(r"<[^>]+>", " ", body)
        body = re.sub(r"\s+", " ", body).strip()
    return {
        "uid":       m.get("id", ""),
        "from":      f"{sender.get('name', '')} <{sender.get('address', '')}>".strip(),
        "to":        ", ".join(
            r["emailAddress"]["address"]
            for r in m.get("toRecipients", [])
        ),
        "subject":   m.get("subject", "(kein Betreff)"),
        "date":      m.get("receivedDateTime", ""),
        "body":      textwrap.shorten(body, width=2000, placeholder=" [...]"),
        "is_read":   m.get("isRead", False),
    }
