"""Small sync HTTP health probes with explicit scheme restrictions."""

from __future__ import annotations

import http.client
from typing import Any, Dict
from urllib.parse import urlparse


def fetch_http_text(url: str, timeout: float = 2.0) -> Dict[str, Any]:
    """Fetch a small HTTP/HTTPS response body with a strict scheme whitelist."""
    parsed = urlparse(str(url or "").strip())
    if parsed.scheme not in {"http", "https"}:
        raise ValueError(f"Unsupported health-check scheme: {parsed.scheme or 'missing'}")
    if not parsed.hostname:
        raise ValueError("Health-check URL is missing a hostname")

    path = parsed.path or "/"
    if parsed.query:
        path = f"{path}?{parsed.query}"

    connection_cls = http.client.HTTPSConnection if parsed.scheme == "https" else http.client.HTTPConnection
    conn = connection_cls(parsed.hostname, parsed.port, timeout=timeout)
    try:
        conn.request("GET", path)
        response = conn.getresponse()
        body = response.read().decode("utf-8", errors="ignore")
        return {"status_code": int(response.status or 0), "body": body, "url": url}
    finally:
        conn.close()
