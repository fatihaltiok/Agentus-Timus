"""Gemeinsamer ScrapingAnt-Adapter fuer Social-Media- und JS-Fetches."""

from __future__ import annotations

import logging
import os
import re
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

DEFAULT_WAIT_SELECTORS = {
    "twitter": "article, main",
    "linkedin": "main",
    "instagram": "main",
    "tiktok": "main",
    "reddit": "main",
    "threads": "main",
    "bluesky": "main",
    "mastodon": "main",
}

AUTH_WALL_MARKERS = {
    "twitter": (
        "sign in to x",
        "log in to x",
        "join x today",
        "create account",
        "/i/flow/login",
        "happening now",
    ),
    "linkedin": (
        "sign in to linkedin",
        "join linkedin",
        "sign in to see",
        "linkedin login",
    ),
    "instagram": (
        "log in to instagram",
        "sign up for instagram",
        "see instagram photos and videos",
    ),
    "tiktok": (
        "log in to tiktok",
        "sign up for tiktok",
        "open app",
    ),
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


def default_wait_for_selector(url: str, *, platform: str = "") -> str:
    normalized_platform = str(platform or "").strip().lower() or detect_platform(url)
    if normalized_platform == "twitter" and "/status/" in str(url or "").lower():
        return 'article, [data-testid="tweet"], main article'
    return DEFAULT_WAIT_SELECTORS.get(normalized_platform, "main")


def detect_auth_wall(url: str, text: str, html: str, *, platform: str = "") -> bool:
    normalized_platform = str(platform or "").strip().lower() or detect_platform(url)
    markers = AUTH_WALL_MARKERS.get(normalized_platform)
    if not markers:
        return False
    combined = " ".join(
        part for part in (str(text or "").lower(), str(html or "").lower()) if part
    )
    marker_hits = sum(1 for marker in markers if marker in combined)
    normalized_text = re.sub(r"\s+", " ", str(text or "").strip().lower())
    return marker_hits >= 2 and len(normalized_text) < 1200


def build_auth_required_payload(url: str, *, platform: str = "") -> dict:
    normalized_platform = str(platform or "").strip().lower() or detect_platform(url)
    platform_label = {
        "twitter": "X/Twitter",
        "linkedin": "LinkedIn",
        "instagram": "Instagram",
        "tiktok": "TikTok",
    }.get(normalized_platform, normalized_platform or "die Plattform")
    return {
        "status": "auth_required",
        "platform": normalized_platform or "unknown",
        "url": url,
        "content": "",
        "char_count": 0,
        "auth_required": True,
        "error": f"{platform_label} verlangt fuer lesbare Inhalte einen angemeldeten Zugriff.",
        "user_action_required": (
            f"Bitte frage den Nutzer, ob Timus seinen Login-Zugang fuer {platform_label} "
            "verwenden darf, damit die Inhalte mit seinem Account gelesen werden koennen."
        ),
    }


async def fetch_page_text_via_scrapingant(
    url: str,
    *,
    render_js: bool = True,
    timeout_seconds: float = 45.0,
    max_chars: int = 15000,
    wait_for_selector: str | None = None,
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
    effective_wait_selector = (
        str(wait_for_selector or "").strip() or default_wait_for_selector(url, platform=platform)
    )
    if render_js and effective_wait_selector:
        params["wait_for_selector"] = effective_wait_selector

    try:
        async with httpx.AsyncClient(timeout=timeout_seconds) as client:
            resp = await client.get(SCRAPINGANT_BASE_URL, params=params)
            resp.raise_for_status()

        html = str(resp.text or "")
        text = html_to_text(html)
        if detect_auth_wall(url, text, html, platform=platform):
            logger.info("ScrapingAnt auth wall erkannt: %s @ %s", platform, url[:80])
            return build_auth_required_payload(url, platform=platform)
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
