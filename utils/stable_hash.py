"""Stable non-security fingerprints for Timus runtime state tracking."""

from __future__ import annotations

import hashlib


def stable_hex_digest(data: bytes, hex_chars: int = 16) -> str:
    """Return a short stable hex digest for non-security use cases."""
    if hex_chars < 1:
        raise ValueError("hex_chars must be >= 1")

    digest_size = min(64, max(1, (hex_chars + 1) // 2))
    return hashlib.blake2b(data, digest_size=digest_size).hexdigest()[:hex_chars]


def stable_text_digest(text: str, hex_chars: int = 16) -> str:
    """Return a stable hex digest for text fingerprints."""
    return stable_hex_digest(text.encode("utf-8", errors="ignore"), hex_chars=hex_chars)
