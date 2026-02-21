"""
utils/error_classifier.py

Klassifiziert Exceptions in handhabbare Fehler-Typen.
Bestimmt ob ein Fehler retriable ist und welche Strategie angewendet wird.
"""

from __future__ import annotations

import re
from enum import Enum
from typing import Optional


class ErrorType(str, Enum):
    API_ERROR      = "api_error"       # HTTP 5xx, Netzwerkfehler
    RATE_LIMIT     = "rate_limit"      # HTTP 429
    AUTH_ERROR     = "auth_error"      # HTTP 401/403 → anderer Key/Provider
    CONTENT_FILTER = "content_filter"  # Policy-Violation
    TIMEOUT        = "timeout"         # Request-Timeout
    TOOL_FAIL      = "tool_fail"       # Tool-Ausführung fehlgeschlagen
    MODEL_ERROR    = "model_error"     # Modell-spezifischer Fehler
    UNKNOWN        = "unknown"         # Nicht klassifizierbar


class ClassifiedError:
    def __init__(
        self,
        error_type: ErrorType,
        original: Exception,
        retriable: bool,
        should_failover: bool,
        backoff_seconds: float = 0.0,
        message: str = "",
    ):
        self.error_type = error_type
        self.original = original
        self.retriable = retriable
        self.should_failover = should_failover
        self.backoff_seconds = backoff_seconds
        self.message = message or str(original)

    def __repr__(self) -> str:
        return (
            f"ClassifiedError(type={self.error_type}, "
            f"retriable={self.retriable}, failover={self.should_failover})"
        )


def classify(exc: Exception) -> ClassifiedError:
    """
    Klassifiziert eine Exception und bestimmt die Behandlungsstrategie.

    Retriable:       Gleiches Model nochmal versuchen (nach Backoff)
    Should_failover: Anderes Model/Agent versuchen
    """
    msg = str(exc).lower()
    exc_type = type(exc).__name__.lower()

    # ── Rate Limit ───────────────────────────────────────────────
    if _matches(msg, ["rate limit", "rate_limit", "429", "too many requests"]):
        return ClassifiedError(
            ErrorType.RATE_LIMIT, exc,
            retriable=True, should_failover=False,
            backoff_seconds=30.0,
            message="Rate-Limit — 30s warten, dann retry",
        )

    # ── Auth-Fehler ───────────────────────────────────────────────
    if _matches(msg, ["401", "403", "invalid api key", "incorrect api key",
                      "authentication", "unauthorized", "forbidden"]):
        return ClassifiedError(
            ErrorType.AUTH_ERROR, exc,
            retriable=False, should_failover=True,
            backoff_seconds=0.0,
            message="Auth-Fehler — Failover auf nächsten Provider",
        )

    # ── Content Filter ────────────────────────────────────────────
    if _matches(msg, ["content_filter", "content filter", "policy violation",
                      "safety", "harmful", "inappropriate"]):
        return ClassifiedError(
            ErrorType.CONTENT_FILTER, exc,
            retriable=False, should_failover=True,
            backoff_seconds=0.0,
            message="Content-Filter — Failover auf anderen Provider",
        )

    # ── Timeout ───────────────────────────────────────────────────
    if _matches(msg, ["timeout", "timed out", "read timeout", "connect timeout"]) \
            or _matches(exc_type, ["timeouterror", "asynciotimeouterror"]):
        return ClassifiedError(
            ErrorType.TIMEOUT, exc,
            retriable=True, should_failover=True,
            backoff_seconds=5.0,
            message="Timeout — retry mit Backoff, dann Failover",
        )

    # ── Server-Fehler (5xx) ───────────────────────────────────────
    if _matches(msg, ["500", "502", "503", "504", "internal server error",
                      "bad gateway", "service unavailable", "connection error",
                      "connection refused", "connectionerror"]):
        return ClassifiedError(
            ErrorType.API_ERROR, exc,
            retriable=True, should_failover=True,
            backoff_seconds=10.0,
            message="Server-Fehler — retry mit Backoff, dann Failover",
        )

    # ── Tool-Fehler ───────────────────────────────────────────────
    if _matches(msg, ["tool", "mcp", "registry", "tool_fail", "no tool"]):
        return ClassifiedError(
            ErrorType.TOOL_FAIL, exc,
            retriable=False, should_failover=True,
            backoff_seconds=0.0,
            message="Tool-Fehler — Failover auf robusteren Agent",
        )

    # ── Modell-Fehler ─────────────────────────────────────────────
    if _matches(msg, ["model", "context length", "max token", "token limit",
                      "overloaded", "capacity"]):
        return ClassifiedError(
            ErrorType.MODEL_ERROR, exc,
            retriable=False, should_failover=True,
            backoff_seconds=5.0,
            message="Modell-Fehler — Failover",
        )

    # ── Unbekannt ─────────────────────────────────────────────────
    return ClassifiedError(
        ErrorType.UNKNOWN, exc,
        retriable=False, should_failover=True,
        backoff_seconds=2.0,
        message=f"Unbekannter Fehler ({exc_type})",
    )


def _matches(text: str, patterns: list[str]) -> bool:
    return any(p in text for p in patterns)
