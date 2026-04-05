"""Gemeinsamer ScrapingAnt-Adapter fuer Social-Media- und JS-Fetches."""

from __future__ import annotations

import logging
import os
from typing import Optional
from urllib.parse import urlparse

import httpx
from dotenv import load_dotenv

load_dotenv(override=True)

logger = logging.getLogger("scrapingant_client")

SCRAPINGANT_BASE_URL = "https://api.scrapingant.com/v2/general"

PLATFORM_MAP = {
    "twitter.com": "twitter",
    "x.com": "twitter",
    "linkedin.com": "linkedin",
    "instagram.com": "instagram",
    "tiktok.com": "tiktok",
    "youtube.com": "youtube",
    "youtu.be": "youtube",
    "facebook.com": "facebook",
    "reddit.com": "reddit",
    "threads.net": "threads",
    "mastodon.social": "mastodon",
    "bsky.app": "bluesky",
}

SCRAPINGANT_DOMAINS = {
    "twitter.com",
    "x.com",
    "linkedin.com",
    "instagram.com",
    "tiktok.com",
    "facebook.com",
    "reddit.com",
}


def get_scrapingant_api_key() -> str:
    return str(os.getenv("SCRAPINGANT_API_KEY") or "").strip()


def detect_platform(url: str) -> str:
    try:
        host = urlparse(url).netloc.lower().lstrip("www.")
        for domain, platform in PLATFORM_MAP.items():
            if host == domain or host.endswith("." + domain):
                return platform
    except Exception:
        pass
    return "unknown"


def needs_scrapingant(url: str) -> bool:
    try:
        host = urlparse(url).netloc.lower().lstrip("www.")
        return any(host == domain or host.endswith("." + domain) for domain in SCRAPINGANT_DOMAINS)
    except Exception:
        return False


def html_to_text(html: str) -> str:
    try:
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html, "html.parser")
        for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
            tag.decompose()
        return " ".join(soup.get_text(separator=" ").split())
    except ImportError:
        import html as html_module
        import re

        text = re.sub(r"<[^>]+>", " ", html)
        text = html_module.unescape(text)
        return " ".join(text.split())


def _clamp_scrapingant_timeout(timeout_seconds: float) -> int:
    """ScrapingAnt v2 akzeptiert laut Docs nur 5-60 Sekunden Request-Timeout."""
    try:
        value = int(round(float(timeout_seconds)))
    except Exception:
        value = 45
    return max(5, min(60, value))


async def fetch_page_text_via_scrapingant(
    url: str,
    *,
    render_js: bool = True,
    timeout_seconds: float = 45.0,
    max_chars: int = 15000,
) -> dict:
    """Holt Seiteninhalt via ScrapingAnt und liefert ein standardisiertes Payload."""
    api_key = get_scrapingant_api_key()
    platform = detect_platform(url)
    if not api_key:
        return {
            "status": "error",
            "error": "SCRAPINGANT_API_KEY nicht konfiguriert. Bitte in .env setzen.",
            "content": "",
            "platform": platform,
            "url": url,
        }

    params = {
        "url": url,
        "x-api-key": api_key,
        # ScrapingAnt v2 dokumentiert `browser`, nicht `render_js`.
        "browser": "true" if render_js else "false",
        "proxy_type": "residential",
        "timeout": str(_clamp_scrapingant_timeout(timeout_seconds)),
    }

    try:
        async with httpx.AsyncClient(timeout=timeout_seconds) as client:
            resp = await client.get(SCRAPINGANT_BASE_URL, params=params)
            resp.raise_for_status()

        text = html_to_text(resp.text)
        logger.info("ScrapingAnt: %s @ %s (%s Zeichen)", platform, url[:80], len(text))
        return {
            "status": "success",
            "platform": platform,
            "url": url,
            "content": text[:max_chars],
            "char_count": len(text),
        }
    except httpx.HTTPStatusError as e:
        logger.warning("ScrapingAnt HTTP %s fuer %s", e.response.status_code, url)
        return {
            "status": "error",
            "error": f"HTTP {e.response.status_code}",
            "content": "",
            "platform": platform,
            "url": url,
        }
    except httpx.TimeoutException:
        logger.warning("ScrapingAnt Timeout fuer %s", url)
        return {
            "status": "error",
            "error": f"Timeout ({int(timeout_seconds)}s)",
            "content": "",
            "platform": platform,
            "url": url,
        }
    except Exception as e:
        logger.error("ScrapingAnt Fehler fuer %s: %s", url, e)
        return {
            "status": "error",
            "error": str(e),
            "content": "",
            "platform": platform,
            "url": url,
        }
