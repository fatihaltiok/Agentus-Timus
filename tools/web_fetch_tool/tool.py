"""
tools/web_fetch_tool/tool.py

Hybrid-Web-Fetch: URL-Inhalte abrufen und für LLM aufbereiten.

Methode 1: requests + BeautifulSoup (schnell, ~1s, 90% der Seiten)
Methode 2: Playwright Chromium (JavaScript-SPAs, Google-Redirects, ~5s)

Fallback-Chain (auto): requests → Playwright bei 401/403/SPA-Erkennung

MCP-Tools:
  fetch_url            — eine URL abrufen
  fetch_multiple_urls  — mehrere URLs parallel abrufen (max 10)
"""

from __future__ import annotations

import asyncio
import logging
import re
from typing import Any, Dict, List
from urllib.parse import urlparse

from tools.tool_registry_v2 import ToolCategory as C
from tools.tool_registry_v2 import ToolParameter as P
from tools.tool_registry_v2 import tool

log = logging.getLogger("WebFetchTool")

# ── Sicherheits-Blacklist ─────────────────────────────────────────────────────

_BLOCKED_PATTERNS = [
    "file://",
    "ftp://",
    "127.0.0.1",
    "localhost",
    "192.168.",
    "10.",
    "172.16.",
    "::1",          # IPv6 loopback
    "/etc/passwd",  # Path Injection
    "..%2f",        # Encoded Path Traversal
    "..%2F",
]

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36 Timus/3.3"
    ),
    "Accept-Language": "de-DE,de;q=0.9,en-US;q=0.8",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

# ── Hilfsfunktionen ───────────────────────────────────────────────────────────


def _is_url_allowed(url: str) -> bool:
    url_lower = url.lower()
    return not any(p in url_lower for p in _BLOCKED_PATTERNS)


def _normalize_url(url: str) -> str:
    url = url.strip()
    if not url.startswith(("http://", "https://")):
        url = f"https://{url}"
    return url


def _has_lxml() -> bool:
    try:
        import lxml  # noqa: F401
        return True
    except ImportError:
        return False


def _to_markdown(html: str, soup: Any) -> str:
    """HTML → Markdown, Fallback auf get_text wenn html2text fehlt."""
    try:
        import html2text as h2t
        converter = h2t.HTML2Text()
        converter.ignore_links = False
        converter.ignore_images = True
        converter.body_width = 0
        return converter.handle(html)
    except ImportError:
        return soup.get_text(separator="\n", strip=True)


def _parse_html(html: str, url: str, max_length: int) -> Dict[str, Any]:
    """HTML → strukturierter Content-Dict mit Titel, Text, Markdown, Links."""
    from bs4 import BeautifulSoup

    parser = "lxml" if _has_lxml() else "html.parser"
    soup = BeautifulSoup(html, parser)

    # Titel
    title_tag = soup.find("title")
    title = title_tag.get_text(strip=True) if title_tag else ""

    # Rauschen entfernen
    for tag in soup(["script", "style", "nav", "footer", "header", "aside", "noscript", "svg"]):
        tag.decompose()

    # Links sammeln (max 20, nur externe)
    links: List[Dict[str, str]] = []
    for a in soup.find_all("a", href=True)[:30]:
        href = str(a["href"]).strip()
        if href.startswith("http") and len(links) < 20:
            links.append({"text": a.get_text(strip=True)[:80], "href": href})

    # Fließtext
    text = soup.get_text(separator="\n", strip=True)
    text = re.sub(r"\n{3,}", "\n\n", text)

    # Markdown
    markdown = _to_markdown(html, soup)

    return {
        "title": title,
        "content": text[:max_length],
        "markdown": markdown[: max(1000, max_length // 2)],
        "links": links,
        "content_length": len(text),
    }


def _looks_like_spa(html: str) -> bool:
    """Erkennt JavaScript-SPAs (wenig sichtbarer Text, viel JS-Code)."""
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style"]):
        tag.decompose()
    text = soup.get_text(strip=True)
    return len(text) < 200 and len(html) > 5000


# ── Fetch-Engines ─────────────────────────────────────────────────────────────


def _fetch_with_requests(url: str, max_length: int, timeout: int) -> Dict[str, Any]:
    """Schneller HTTP-Fetch via requests. Kein JavaScript-Rendering."""
    import requests as req

    try:
        resp = req.get(url, headers=_HEADERS, timeout=timeout, allow_redirects=True)
        final_url = resp.url

        if resp.status_code == 429:
            return {"status": "error", "message": "Rate limited (429)", "retry_with_playwright": False}
        if resp.status_code in (401, 403):
            return {
                "status": "error",
                "message": f"Zugriff verweigert ({resp.status_code})",
                "retry_with_playwright": True,
            }
        if resp.status_code != 200:
            return {"status": "error", "message": f"HTTP {resp.status_code}", "retry_with_playwright": False}

        content_type = resp.headers.get("content-type", "")

        # JSON direkt zurückgeben
        if "application/json" in content_type:
            return {
                "status": "success",
                "url": final_url,
                "title": "",
                "content": resp.text[:max_length],
                "markdown": resp.text[:max_length],
                "links": [],
                "method": "requests",
                "content_type": content_type,
                "content_length": len(resp.text),
            }

        if "text/html" not in content_type and "application/xhtml" not in content_type:
            return {
                "status": "error",
                "message": f"Kein HTML-Inhalt ({content_type})",
                "retry_with_playwright": False,
            }

        # JavaScript-SPA erkennen → Playwright-Fallback empfehlen
        if _looks_like_spa(resp.text):
            return {"status": "error", "message": "JavaScript-SPA erkannt", "retry_with_playwright": True}

        parsed = _parse_html(resp.text, final_url, max_length)
        return {"status": "success", "url": final_url, "method": "requests", **parsed}

    except req.Timeout:
        return {"status": "error", "message": f"Timeout nach {timeout}s", "retry_with_playwright": False}
    except req.ConnectionError as e:
        return {"status": "error", "message": f"Verbindungsfehler: {e}", "retry_with_playwright": False}
    except Exception as e:
        return {"status": "error", "message": str(e), "retry_with_playwright": True}


async def _fetch_with_playwright(url: str, max_length: int, timeout_ms: int) -> Dict[str, Any]:
    """Browser-Fetch via Playwright — rendert JavaScript, folgt Redirects."""
    try:
        from playwright.async_api import async_playwright

        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True)
            ctx = await browser.new_context(
                user_agent=_HEADERS["User-Agent"],
                locale="de-DE",
            )
            page = await ctx.new_page()
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
                await page.wait_for_timeout(1500)  # Lazy-Load abwarten
                title = await page.title()
                html = await page.content()
                final_url = page.url
            finally:
                await browser.close()

        parsed = _parse_html(html, final_url, max_length)
        parsed["title"] = parsed["title"] or title
        return {"status": "success", "url": final_url, "method": "playwright", **parsed}

    except asyncio.TimeoutError:
        return {"status": "error", "message": f"Playwright Timeout ({timeout_ms // 1000}s)"}
    except Exception as e:
        return {"status": "error", "message": f"Playwright: {e}"}


async def _fetch_hybrid(url: str, method: str, max_length: int, timeout: int) -> Dict[str, Any]:
    """Fallback-Chain: requests → Playwright (nur wenn nötig)."""
    if method == "playwright":
        return await _fetch_with_playwright(url, max_length, timeout * 1000)

    if method == "requests":
        result = _fetch_with_requests(url, max_length, timeout)
        result.pop("retry_with_playwright", None)
        return result

    # auto: requests zuerst
    result = _fetch_with_requests(url, max_length, timeout)
    if result.get("status") == "success":
        return result

    if result.get("retry_with_playwright"):
        log.info("🌐 Playwright-Fallback für %s (Grund: %s)", url, result.get("message"))
        pw = await _fetch_with_playwright(url, max_length, timeout * 2 * 1000)
        if pw.get("status") == "success":
            return pw

    result.pop("retry_with_playwright", None)
    return result


# ── MCP Tools ─────────────────────────────────────────────────────────────────


@tool(
    name="fetch_url",
    description=(
        "Lädt eine URL und gibt den aufbereiteten Seiteninhalt zurück. "
        "Automatischer Fallback auf Playwright für JavaScript-Seiten und geschützte Inhalte. "
        "Gibt Titel, Text-Content, Markdown und extrahierte Links zurück."
    ),
    parameters=[
        P("url", "string", "Vollständige URL (https://...) oder Domain ohne Protokoll", required=True),
        P(
            "method",
            "string",
            "Fetch-Methode: auto (requests → Playwright-Fallback) | requests (schnell) | playwright (immer Browser)",
            required=False,
            default="auto",
        ),
        P(
            "max_content_length",
            "integer",
            "Maximale Zeichenlänge des extrahierten Text-Contents (default 8000, max 50000)",
            required=False,
            default=8000,
        ),
        P(
            "timeout",
            "integer",
            "Timeout in Sekunden für requests (Playwright nutzt doppelten Wert, default 15)",
            required=False,
            default=15,
        ),
    ],
    capabilities=["fetch", "web", "http"],
    category=C.BROWSER,
)
async def fetch_url(
    url: str,
    method: str = "auto",
    max_content_length: int = 8000,
    timeout: int = 15,
) -> Dict[str, Any]:
    url = _normalize_url(url)

    if not _is_url_allowed(url):
        return {"status": "error", "message": "URL nicht erlaubt (Sicherheitsrichtlinie)", "url": url}

    method = method if method in ("auto", "requests", "playwright") else "auto"
    max_content_length = max(500, min(int(max_content_length), 50_000))
    timeout = max(5, min(int(timeout), 60))

    try:
        return await _fetch_hybrid(url, method, max_content_length, timeout)
    except Exception as e:
        log.warning("fetch_url Fehler (%s): %s", url, e)
        return {"status": "error", "url": url, "message": str(e)}


@tool(
    name="fetch_multiple_urls",
    description=(
        "Lädt mehrere URLs parallel und gibt alle Inhalte gebündelt zurück. "
        "Ideal für Recherche-Workflows mit mehreren Quellen gleichzeitig (max 10 URLs)."
    ),
    parameters=[
        P("urls", "array", "Liste von URLs (max. 10)", required=True),
        P(
            "method",
            "string",
            "Fetch-Methode für alle URLs: auto | requests | playwright",
            required=False,
            default="auto",
        ),
        P(
            "max_content_length",
            "integer",
            "Maximale Zeichenlänge pro URL (default 4000)",
            required=False,
            default=4000,
        ),
        P(
            "timeout",
            "integer",
            "Timeout in Sekunden pro URL (default 15)",
            required=False,
            default=15,
        ),
    ],
    capabilities=["fetch", "web", "http"],
    category=C.BROWSER,
)
async def fetch_multiple_urls(
    urls: list,
    method: str = "auto",
    max_content_length: int = 4000,
    timeout: int = 15,
) -> Dict[str, Any]:
    if not isinstance(urls, list) or not urls:
        return {"status": "error", "message": "urls muss eine nicht-leere Liste sein"}

    normalized = [_normalize_url(str(u)) for u in urls[:10]]
    allowed = [u for u in normalized if _is_url_allowed(u)]
    blocked = [u for u in normalized if not _is_url_allowed(u)]

    if not allowed:
        return {
            "status": "error",
            "message": "Alle URLs durch Sicherheitsrichtlinie blockiert",
            "blocked": blocked,
        }

    method = method if method in ("auto", "requests", "playwright") else "auto"
    max_content_length = max(500, min(int(max_content_length), 20_000))
    timeout = max(5, min(int(timeout), 60))

    tasks = [_fetch_hybrid(u, method, max_content_length, timeout) for u in allowed]
    raw_results = await asyncio.gather(*tasks, return_exceptions=True)

    results = []
    success_count = 0
    error_count = 0
    for url, r in zip(allowed, raw_results):
        if isinstance(r, Exception):
            results.append({"url": url, "status": "error", "message": str(r)})
            error_count += 1
        elif isinstance(r, dict) and r.get("status") == "success":
            results.append(r)
            success_count += 1
        else:
            results.append(r if isinstance(r, dict) else {"url": url, "status": "error", "message": str(r)})
            error_count += 1

    return {
        "status": "ok",
        "results": results,
        "success_count": success_count,
        "error_count": error_count,
        "blocked_count": len(blocked),
        "total": len(normalized),
    }
