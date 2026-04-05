# tools/social_media_tool/tool.py
"""
Social Media Tool — Inhalte von sozialen Netzwerken abrufen.

Nutzt ScrapingAnt (JS-Rendering + Residential Proxies) um Inhalte von
Twitter/X, LinkedIn, Instagram, TikTok, YouTube und anderen Plattformen
zu lesen, die direktes HTTP-Scraping blockieren.

Capabilities: social_media, web, fetch
"""

import logging
from tools.social_media_tool.client import (
    detect_platform,
    fetch_page_text_via_scrapingant,
)

from tools.tool_registry_v2 import tool, ToolParameter as P, ToolCategory as C

logger = logging.getLogger("social_media_tool")

def _detect_platform(url: str) -> str:
    """Rueckwaertskompatibler Wrapper fuer Plattform-Erkennung."""
    return detect_platform(url)


async def _scrape_with_scrapingant(url: str, render_js: bool = True) -> dict:
    """Fuehrt den gemeinsamen ScrapingAnt-Adapter aus."""
    return await fetch_page_text_via_scrapingant(url, render_js=render_js, max_chars=15000)


@tool(
    name="fetch_social_media",
    description=(
        "Ruft Inhalte von Social-Media-Seiten ab: Twitter/X Posts und Profile, "
        "LinkedIn Artikel und Profile, Instagram Posts, TikTok Videos (Text), "
        "YouTube Kanalseiten, Reddit-Threads und mehr. "
        "Nutzt JS-Rendering und Residential Proxies um Anti-Bot-Schutz zu umgehen. "
        "Gibt den extrahierten Text der Seite zurück. "
        "Benötigt SCRAPINGANT_API_KEY in der .env."
    ),
    parameters=[
        P("url", "string", "Die vollständige URL der Social-Media-Seite oder des Posts", required=True),
        P("render_js", "boolean", "JS-Rendering aktivieren (empfohlen für dynamische Seiten, default: true)", required=False, default=True),
    ],
    capabilities=["social_media", "web", "fetch"],
    category=C.RESEARCH,
    examples=[
        'fetch_social_media(url="https://twitter.com/elonmusk")',
        'fetch_social_media(url="https://www.linkedin.com/in/username")',
        'fetch_social_media(url="https://www.instagram.com/p/POST_ID")',
    ],
    returns="dict mit status, platform, url, content (Text), char_count",
    parallel_allowed=True,
    timeout=50.0,
)
async def fetch_social_media(url: str, render_js: bool = True) -> dict:
    """Ruft Social-Media-Inhalte via ScrapingAnt ab."""
    return await _scrape_with_scrapingant(url, render_js=render_js)


@tool(
    name="fetch_page_with_js",
    description=(
        "Ruft beliebige Webseiten mit vollständigem JS-Rendering ab — nützlich für "
        "Single-Page-Apps (React/Vue/Angular), passwortgeschützte Bereiche mit "
        "Session-Cookies oder Seiten mit starkem Anti-Bot-Schutz (403/429). "
        "Schneller Fallback wenn normales HTTP-Scraping fehlschlägt. "
        "Benötigt SCRAPINGANT_API_KEY in der .env."
    ),
    parameters=[
        P("url", "string", "Die abzurufende URL", required=True),
        P("render_js", "boolean", "JS-Rendering (default: true)", required=False, default=True),
    ],
    capabilities=["social_media", "web", "fetch", "browser"],
    category=C.RESEARCH,
    examples=[
        'fetch_page_with_js(url="https://app.example.com/dashboard")',
        'fetch_page_with_js(url="https://www.reuters.com/article/...")',
    ],
    returns="dict mit status, platform, url, content (Text), char_count",
    parallel_allowed=True,
    timeout=50.0,
)
async def fetch_page_with_js(url: str, render_js: bool = True) -> dict:
    """Ruft Webseiten mit JS-Rendering via ScrapingAnt ab."""
    return await _scrape_with_scrapingant(url, render_js=render_js)
