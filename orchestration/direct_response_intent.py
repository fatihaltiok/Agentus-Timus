"""Direct-response intent detection for exact-output chat requests."""

from __future__ import annotations

import re
from typing import Any


_EXECUTION_PREFIX_RE = re.compile(
    r"^\s*[\"']?(?:f(?:ue|ü)hre\s+aus|mach\s+das|ausf(?:ue|ü)hren)\s*[:\-–,]?\s*",
    re.IGNORECASE,
)
_SYSTEM_OR_SHELL_HINTS = (
    "systemctl",
    "sudo ",
    "pip install",
    "apt install",
    "apt-get install",
    "bash ",
    "shell",
    "terminal",
    "konsole",
)
_BEHAVIOR_SCOPE_HINTS = (
    "ab jetzt",
    "in zukunft",
    "zukuenftig",
    "zukünftig",
    "immer",
    "bevorzuge",
    "weniger formal",
    "kurze antworten",
    "kurz antworten",
)
_DIRECT_RESPONSE_PATTERNS = (
    re.compile(
        r"^(?:bitte\s+)?(?:antworte|sag(?:e)?|gib|schreibe|reply|respond)"
        r"\s+(?:mir\s+)?(?:(?:exakt|genau|wortw(?:oe|ö)rtlich|ausschliesslich|ausschließlich)\s+)*"
        r"(?:nur\s+)?(?:mit|:)\s+(.+)$",
        re.IGNORECASE,
    ),
    re.compile(
        r"^(?:bitte\s+)?(?:gib|schreibe)\s+"
        r"(?:(?:exakt|genau|wortw(?:oe|ö)rtlich)\s+)+(.+?)\s+(?:aus|zur(?:ue|ü)ck)$",
        re.IGNORECASE,
    ),
)


def _clean_query(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    for marker in ("Benutzeranfrage:", "Nutzeranfrage:", "# CURRENT USER QUERY"):
        if marker in text:
            text = text.split(marker, 1)[1].strip()
    text = _EXECUTION_PREFIX_RE.sub("", text).strip()
    return text.strip("\"'“”„` ")


def extract_requested_direct_response(query: Any) -> str:
    """Return the requested exact response text, or an empty string."""

    text = _clean_query(query)
    if not text:
        return ""
    lowered = text.lower()
    if any(hint in lowered for hint in _SYSTEM_OR_SHELL_HINTS):
        return ""
    if any(hint in lowered for hint in _BEHAVIOR_SCOPE_HINTS):
        return ""
    for pattern in _DIRECT_RESPONSE_PATTERNS:
        match = pattern.search(text)
        if match:
            requested = str(match.group(1) or "").strip()
            return requested.strip("\"'“”„` ")
    return ""


def looks_like_direct_response_instruction(query: Any) -> bool:
    """True for exact/direct answer instructions that need no tool execution."""

    return bool(extract_requested_direct_response(query))
