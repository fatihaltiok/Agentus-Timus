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
    default_wait_for_selector,
    detect_platform,
    fetch_page_text_via_scrapingant,
)

from tools.tool_registry_v2 import tool, ToolParameter as P, ToolCategory as C

logger = logging.getLogger("social_media_tool")

def _detect_platform(url: str) -> str:
    """Rueckwaertskompatibler Wrapper fuer Plattform-Erkennung."""
    return detect_platform(url)


async def _scrape_with_scrapingant(
    url: str,
    render_js: bool = True,
    wait_for_selector: str | None = None,
) -> dict:
    """Fuehrt den gemeinsamen ScrapingAnt-Adapter aus."""
    selector = str(wait_for_selector or "").strip() or default_wait_for_selector(url)
    return await fetch_page_text_via_scrapingant(
        url,
        render_js=render_js,
        max_chars=15000,
        wait_for_selector=selector,
    )


@tool(
    name="fetch_social_media",
    description=(
        "Ruft Inhalte von Social-Media-Seiten ab: Twitter/X Posts und Profile, "
        "LinkedIn Artikel und Profile, Instagram Posts, TikTok Videos (Text), "
        "YouTube Kanalseiten, Reddit-Threads und mehr. "
        "Nutzt JS-Rendering und Residential Proxies um Anti-Bot-Schutz zu umgehen. "
        "Versucht bei JS-Seiten zusaetzlich auf relevante DOM-Elemente zu warten. "
        "Wenn die Plattform lesbare Inhalte nur nach Login freigibt, liefert das Tool "
        "ein auth_required-Signal und Timus soll den Nutzer nach Login-Zugang fragen. "
        "Gibt den extrahierten Text der Seite zurück. "
        "Benötigt SCRAPINGANT_API_KEY in der .env."
    ),
    parameters=[
        P("url", "string", "Die vollständige URL der Social-Media-Seite oder des Posts", required=True),
        P("render_js", "boolean", "JS-Rendering aktivieren (empfohlen für dynamische Seiten, default: true)", required=False, default=True),
        P("wait_for_selector", "string", "Optionaler CSS-Selector auf den gewartet wird, bevor der Inhalt gelesen wird", required=False),
    ],
    capabilities=["social_media", "web", "fetch"],
    category=C.RESEARCH,
    examples=[
        'fetch_social_media(url="https://twitter.com/elonmusk")',
        'fetch_social_media(url="https://www.linkedin.com/in/username")',
        'fetch_social_media(url="https://www.instagram.com/p/POST_ID")',
    ],
    returns="dict mit status, platform, url, content (Text), char_count; bei Login-Wand ggf. auth_required + user_action_required",
    parallel_allowed=True,
    timeout=50.0,
)
async def fetch_social_media(
    url: str,
    render_js: bool = True,
    wait_for_selector: str | None = None,
) -> dict:
    """Ruft Social-Media-Inhalte via ScrapingAnt ab."""
    return await _scrape_with_scrapingant(url, render_js=render_js, wait_for_selector=wait_for_selector)


@tool(
    name="fetch_page_with_js",
    description=(
        "Ruft beliebige Webseiten mit vollständigem JS-Rendering ab — nützlich für "
        "Single-Page-Apps (React/Vue/Angular), passwortgeschützte Bereiche mit "
        "Session-Cookies oder Seiten mit starkem Anti-Bot-Schutz (403/429). "
        "Schneller Fallback wenn normales HTTP-Scraping fehlschlägt. "
        "Wenn lesbare Inhalte einen Login erfordern, liefert das Tool "
        "ein auth_required-Signal und Timus soll den Nutzer nach Zugang fragen. "
        "Benötigt SCRAPINGANT_API_KEY in der .env."
    ),
    parameters=[
        P("url", "string", "Die abzurufende URL", required=True),
        P("render_js", "boolean", "JS-Rendering (default: true)", required=False, default=True),
        P("wait_for_selector", "string", "Optionaler CSS-Selector auf den gewartet wird, bevor der Inhalt gelesen wird", required=False),
    ],
    capabilities=["social_media", "web", "fetch", "browser"],
    category=C.RESEARCH,
    examples=[
        'fetch_page_with_js(url="https://app.example.com/dashboard")',
        'fetch_page_with_js(url="https://www.reuters.com/article/...")',
    ],
    returns="dict mit status, platform, url, content (Text), char_count; bei Login-Wand ggf. auth_required + user_action_required",
    parallel_allowed=True,
    timeout=50.0,
)
async def fetch_page_with_js(
    url: str,
    render_js: bool = True,
    wait_for_selector: str | None = None,
) -> dict:
    """Ruft Webseiten mit JS-Rendering via ScrapingAnt ab."""
    return await _scrape_with_scrapingant(url, render_js=render_js, wait_for_selector=wait_for_selector)
