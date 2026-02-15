import logging
import re
import urllib.parse
from typing import Any, Dict, Optional

from tools.tool_registry_v2 import tool, ToolParameter as P, ToolCategory as C

# Logger für dieses spezifische Tool
log = logging.getLogger(__name__)

# Regex für die E-Mail-Validierung (RFC-5322 vereinfacht)
EMAIL_REGEX = re.compile(
    r"^(?P<local>[A-Za-z0-9]+(?:[._%+-][A-Za-z0-9]+)*)@"
    r"(?P<domain>(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)+"
    r"(?P<tld>[A-Za-z]{2,63}))$"
)


def _normalize_email(email: str) -> Optional[str]:
    """
    Normalisiert eine E-Mail-Adresse.
    Entfernt führende/trailing Whitespace und setzt den Domain-Teil in Kleinbuchstaben.
    """
    email = email.strip()
    parts = email.split("@", 1)
    if len(parts) != 2:
        return None
    local, domain = parts
    return f"{local}@{domain.lower()}"


def _validate_email_regex(email: str) -> bool:
    """
    Führt die Regex-Validierung für die E-Mail-Adresse durch.
    """
    return bool(EMAIL_REGEX.match(email))


def _validate_email_lengths(email: str) -> bool:
    """
    Prüft die Länge der E-Mail-Adresse.
    - Gesamt <= 254 Zeichen
    - Local-Part <= 64 Zeichen
    """
    if len(email) > 254:
        return False
    local_part = email.split("@", 1)[0]
    return len(local_part) <= 64


@tool(
    name="validate_email",
    description="Validiert eine E-Mail-Adresse auf korrektes Format und Laenge.",
    parameters=[
        P("email", "string", "E-Mail-Adresse zur Validierung", required=True),
    ],
    capabilities=["validation"],
    category=C.SYSTEM
)
async def validate_email(email: str) -> dict:
    """
    Validiert eine E-Mail-Adresse.
    """
    log.info(f"Validating email: '{email}'")
    try:
        # Schritt 1: Grundlegende Syntax prüfen
        if not _validate_email_regex(email):
            reason = "E-Mail-Adresse entspricht nicht dem erwarteten Format."
            log.debug(reason)
            return {
                "valid": False,
                "normalized": None,
                "reason": reason,
            }

        # Schritt 2: Längen prüfen
        if not _validate_email_lengths(email):
            reason = "E-Mail-Adresse überschreitet zulässige Längenbeschränkungen."
            log.debug(reason)
            return {
                "valid": False,
                "normalized": None,
                "reason": reason,
            }

        # Schritt 3: Normalisierung
        normalized = _normalize_email(email)
        log.debug(f"Normalized email: '{normalized}'")
        return {
            "valid": True,
            "normalized": normalized,
            "reason": "Valid",
        }
    except Exception as exc:
        log.error(f"Unexpected error while validating email: {exc}", exc_info=True)
        raise Exception(f"E-Mail-Validierung fehlgeschlagen: {exc}")


def _normalize_url(url: str) -> str:
    """
    Normalisiert eine URL:
    - Scheme und Hostname in Kleinbuchstaben
    - IPv6-Adressen in eckige Klammern
    - Re-Konstruktion des netloc (inkl. optionaler Auth-Info und Port)
    """
    parsed = urllib.parse.urlparse(url)
    scheme = parsed.scheme.lower()
    hostname = parsed.hostname.lower() if parsed.hostname else ""
    if parsed.port:
        netloc = f"{hostname}:{parsed.port}"
    else:
        netloc = hostname

    # Auth-Info (username:password) falls vorhanden
    if parsed.username:
        auth = parsed.username
        if parsed.password:
            auth += f":{parsed.password}"
        netloc = f"{auth}@{netloc}"

    # IPv6-Adressen müssen in Klammern gesetzt werden
    if ":" in hostname and not hostname.startswith("["):
        netloc = f"[{hostname}]"

    normalized = urllib.parse.urlunparse(
        (
            scheme,
            netloc,
            parsed.path,
            parsed.params,
            parsed.query,
            parsed.fragment,
        )
    )
    return normalized


@tool(
    name="validate_url",
    description="Validiert eine URL auf korrektes Format und Schema.",
    parameters=[
        P("url", "string", "URL zur Validierung", required=True),
    ],
    capabilities=["validation"],
    category=C.SYSTEM
)
async def validate_url(url: str) -> dict:
    """
    Validiert eine URL.
    """
    log.info(f"Validating URL: '{url}'")
    try:
        parsed = urllib.parse.urlparse(url)

        # Schritt 1: Grundlegende Checks
        if parsed.scheme.lower() not in {"http", "https"}:
            reason = "Nur 'http' und 'https' Schemes sind erlaubt."
            log.debug(reason)
            return {
                "valid": False,
                "normalized": None,
                "reason": reason,
            }

        if not parsed.netloc:
            reason = "URL muss einen Netloc (Domain) enthalten."
            log.debug(reason)
            return {
                "valid": False,
                "normalized": None,
                "reason": reason,
            }

        if " " in url or "\t" in url:
            reason = "URL darf keine Leerzeichen enthalten."
            log.debug(reason)
            return {
                "valid": False,
                "normalized": None,
                "reason": reason,
            }

        # Schritt 2: Normalisierung
        normalized = _normalize_url(url)
        log.debug(f"Normalized URL: '{normalized}'")
        return {
            "valid": True,
            "normalized": normalized,
            "reason": "Valid",
        }
    except Exception as exc:
        log.error(f"Unexpected error while validating URL: {exc}", exc_info=True)
        raise Exception(f"URL-Validierung fehlgeschlagen: {exc}")


# Optionaler Testblock für isolierte Ausführung
if __name__ == "__main__":
    import json
    import asyncio

    async def main_test():
        test_emails = [
            "User.Name+tag@example-domain.com",
            "invalid-email@",
        ]

        test_urls = [
            "https://Example.com:8080/path?query=1",
            "ftp://example.com/resource",
            "http://invalid url.com",
        ]

        for email in test_emails:
            result = await validate_email(email)
            print(f"Email: {email}")
            print(json.dumps(result, indent=2))

        for url in test_urls:
            result = await validate_url(url)
            print(f"URL: {url}")
            print(json.dumps(result, indent=2))

    asyncio.run(main_test())
