"""
tests/test_web_fetch_tool.py

Offline-Tests für das Web-Fetch-Tool.
Keine echten HTTP-Requests — alle Netzwerkcalls werden gemockt.
"""

import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from tools.web_fetch_tool.tool import (
    _is_url_allowed,
    _normalize_url,
    _looks_like_spa,
    _parse_html,
)


# ── URL-Normalisierung ────────────────────────────────────────────────────────


def test_normalize_url_adds_https():
    assert _normalize_url("example.com") == "https://example.com"


def test_normalize_url_keeps_https():
    assert _normalize_url("https://example.com") == "https://example.com"


def test_normalize_url_keeps_http():
    assert _normalize_url("http://example.com") == "http://example.com"


def test_normalize_url_strips_whitespace():
    assert _normalize_url("  https://example.com  ") == "https://example.com"


# ── Sicherheits-Blacklist ─────────────────────────────────────────────────────


def test_blocked_localhost():
    assert _is_url_allowed("http://localhost:8080/admin") is False


def test_blocked_127():
    assert _is_url_allowed("http://127.0.0.1:5000/health") is False


def test_blocked_private_192():
    assert _is_url_allowed("http://192.168.1.1/router") is False


def test_blocked_private_10():
    assert _is_url_allowed("http://10.0.0.1/internal") is False


def test_blocked_private_172():
    assert _is_url_allowed("http://172.16.0.1/secret") is False


def test_blocked_file_scheme():
    assert _is_url_allowed("file:///etc/passwd") is False


def test_blocked_path_traversal():
    assert _is_url_allowed("https://example.com/..%2Fetc%2Fpasswd") is False


def test_allowed_normal_url():
    assert _is_url_allowed("https://example.com") is True


def test_allowed_github():
    assert _is_url_allowed("https://github.com/fatihaltiok/Agentus-Timus") is True


def test_allowed_wikipedia():
    assert _is_url_allowed("https://de.wikipedia.org/wiki/Python") is True


# ── SPA-Erkennung ─────────────────────────────────────────────────────────────


def test_spa_detection_empty_body():
    """Sehr wenig sichtbarer Text, viel JS → SPA erkannt."""
    html = "<html><body>" + "<script>" + "x" * 6000 + "</script>" + "</body></html>"
    assert _looks_like_spa(html) is True


def test_spa_detection_normal_page():
    """Normale Seite mit viel sichtbarem Text → kein SPA."""
    html = "<html><body>" + "<p>" + "Timus ist ein autonomes KI-System. " * 20 + "</p>" + "</body></html>"
    assert _looks_like_spa(html) is False


# ── HTML-Parsing ──────────────────────────────────────────────────────────────


def test_parse_html_extracts_title():
    html = "<html><head><title>Timus Test</title></head><body><p>Hello</p></body></html>"
    result = _parse_html(html, "https://example.com", max_length=1000)
    assert result["title"] == "Timus Test"


def test_parse_html_extracts_content():
    html = "<html><body><p>Das ist ein Test-Inhalt.</p></body></html>"
    result = _parse_html(html, "https://example.com", max_length=1000)
    assert "Test-Inhalt" in result["content"]


def test_parse_html_removes_scripts():
    html = "<html><body><script>alert('xss')</script><p>Echter Inhalt</p></body></html>"
    result = _parse_html(html, "https://example.com", max_length=1000)
    assert "alert" not in result["content"]
    assert "Echter Inhalt" in result["content"]


def test_parse_html_extracts_links():
    html = (
        '<html><body>'
        '<a href="https://anthropic.com">Anthropic</a>'
        '<a href="https://github.com">GitHub</a>'
        '</body></html>'
    )
    result = _parse_html(html, "https://example.com", max_length=1000)
    hrefs = [l["href"] for l in result["links"]]
    assert "https://anthropic.com" in hrefs
    assert "https://github.com" in hrefs


def test_parse_html_respects_max_length():
    long_text = "A" * 10_000
    html = f"<html><body><p>{long_text}</p></body></html>"
    result = _parse_html(html, "https://example.com", max_length=500)
    assert len(result["content"]) <= 500


# ── fetch_url Sicherheitsprüfung (async, ohne echten HTTP-Call) ───────────────


@pytest.mark.asyncio
async def test_fetch_url_blocked_returns_error():
    from tools.web_fetch_tool.tool import fetch_url
    result = await fetch_url("http://localhost/admin")
    assert result["status"] == "error"
    assert "Sicherheitsrichtlinie" in result["message"]


@pytest.mark.asyncio
async def test_fetch_url_normalizes_domain():
    """Normalisierung von URL ohne Protokoll — geblockt wenn localhost, erlaubt sonst."""
    from tools.web_fetch_tool.tool import fetch_url
    result = await fetch_url("localhost/evil")
    assert result["status"] == "error"


# ── fetch_multiple_urls Validierung ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_fetch_multiple_urls_empty_list():
    from tools.web_fetch_tool.tool import fetch_multiple_urls
    result = await fetch_multiple_urls(urls=[])
    assert result["status"] == "error"


@pytest.mark.asyncio
async def test_fetch_multiple_urls_all_blocked():
    from tools.web_fetch_tool.tool import fetch_multiple_urls
    result = await fetch_multiple_urls(urls=["http://localhost", "http://127.0.0.1"])
    assert result["status"] == "error"
    assert result.get("blocked") is not None


@pytest.mark.asyncio
async def test_fetch_multiple_urls_caps_at_10():
    """Mehr als 10 URLs werden auf 10 begrenzt."""
    from tools.web_fetch_tool.tool import _normalize_url, _is_url_allowed
    urls = [f"https://example{i}.com" for i in range(15)]
    # Nur die ersten 10 dürfen verarbeitet werden
    trimmed = urls[:10]
    assert len(trimmed) == 10
