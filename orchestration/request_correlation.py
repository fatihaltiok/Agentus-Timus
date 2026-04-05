"""Request-Korrelation fuer C2.

Stellt einen kleinen ContextVar-basierten Laufzeitkontext bereit, damit
nachgelagerte Task-Erzeuger dieselbe request_id wie der ausloesende Chat- oder
Task-Pfad uebernehmen koennen, ohne jede Call-Site manuell verdrahten zu
muessen.
"""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from typing import Iterator

_REQUEST_ID_VAR: ContextVar[str] = ContextVar("timus_request_id", default="")
_SESSION_ID_VAR: ContextVar[str] = ContextVar("timus_request_session_id", default="")


def get_current_request_id() -> str:
    return str(_REQUEST_ID_VAR.get("") or "").strip()


def get_current_session_id() -> str:
    return str(_SESSION_ID_VAR.get("") or "").strip()


def get_current_request_correlation() -> dict[str, str]:
    return {
        "request_id": get_current_request_id(),
        "session_id": get_current_session_id(),
    }


@contextmanager
def bind_request_correlation(
    *,
    request_id: str = "",
    session_id: str = "",
) -> Iterator[dict[str, str]]:
    """Bindet request-/session-Korrelation fuer den aktuellen asyncio-Task."""
    clean_request_id = str(request_id or "").strip()
    clean_session_id = str(session_id or "").strip()
    request_token = _REQUEST_ID_VAR.set(clean_request_id)
    session_token = _SESSION_ID_VAR.set(clean_session_id)
    try:
        yield {
            "request_id": clean_request_id,
            "session_id": clean_session_id,
        }
    finally:
        _REQUEST_ID_VAR.reset(request_token)
        _SESSION_ID_VAR.reset(session_token)
