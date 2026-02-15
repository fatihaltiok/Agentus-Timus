# tools/cookie_banner_tool/tool.py
"""
Cookie Banner Handler - Automatische Erkennung und Annahme/Ablehnung von Cookie-Bannern.

Features:
- Automatische Erkennung gängiger Cookie-Banner (OneTrust, Cookiebot, Usercentrics, etc.)
- Auto-Accept oder Auto-Reject basierend auf Konfiguration
- Keine Unterbrechung des Workflows
- Integration mit Qwen-VL für unbekannte Banner

Note: This module exposes utility functions (not RPC methods).
      No V1 @method decorators or register_tool calls were present.
"""

import logging
import asyncio
from typing import Dict, Any, Optional, List
from playwright.async_api import Page, TimeoutError as PlaywrightTimeout

log = logging.getLogger(__name__)

# Cookie-Banner Selektoren für gängige Systeme
COOKIE_ACCEPT_SELECTORS = [
    # OneTrust / CookiePro
    "button#onetrust-accept-btn-handler",
    "button#accept-recommended-btn-handler",
    "#onetrust-pc-btn-handler",

    # Cookiebot
    "button.CybotCookiebotDialogBodyButtonAccept",
    "button#CybotCookiebotDialogBodyButtonAccept",

    # Usercentrics
    "button[data-testid='uc-accept-all-button']",
    "button.uc-accept-all-button",

    # Quantcast
    "button.qc-cmp-ui-content.qc-cmp-button.qc-cmp-primary-button",
    "button[aria-label='Accept']",

    # Deutsche Seiten
    "button[aria-label='Alle akzeptieren']",
    "button[aria-label='Accept all']",
    "button[data-testid='cookie-banner-accept']",
    "button.cmpboxbtnyes",
    "button.fc-cta-consent",

    # Generisch
    "button:has-text('Accept')",
    "button:has-text('Akzeptieren')",
    "button:has-text('Alle akzeptieren')",
    "button:has-text('Zustimmen')",
    "button:has-text('Einverstanden')",

    # Telekom/t-online spezifisch
    "button[data-tracking='cookie-banner-accept']",
    ".sp-deny-btn",  # Manche Varianten
]

COOKIE_REJECT_SELECTORS = [
    # Ablehnen/Notwendige nur
    "button#onetrust-reject-all-handler",
    "button[data-testid='uc-reject-all-button']",
    "button:has-text('Ablehnen')",
    "button:has-text('Nur notwendige')",
    "button:has-text('Essential only')",
]


async def check_and_handle_cookie_banner(
    page: Page,
    auto_accept: bool = True,
    timeout_ms: int = 3000
) -> Dict[str, Any]:
    """
    Prüft auf Cookie-Banner und behandelt sie automatisch.

    Args:
        page: Playwright Page Objekt
        auto_accept: True = Akzeptieren, False = Ablehnen
        timeout_ms: Timeout für Suche

    Returns:
        {
            "found": bool,
            "handled": bool,
            "selector": str (oder None),
            "method": str
        }
    """
    selectors = COOKIE_ACCEPT_SELECTORS if auto_accept else COOKIE_REJECT_SELECTORS
    action_text = "akzeptiert" if auto_accept else "abgelehnt"

    log.info(f"🔍 Suche Cookie-Banner (Auto-{'Accept' if auto_accept else 'Reject'})...")

    # Versuche jeden Selektor
    for selector in selectors:
        try:
            # Prüfe ob Element sichtbar ist
            element = page.locator(selector).first
            is_visible = await element.is_visible(timeout=timeout_ms)

            if is_visible:
                log.info(f"✅ Cookie-Banner gefunden: {selector}")

                # Klicke auf den Button
                await element.click(timeout=5000)
                log.info(f"✅ Cookie-Banner {action_text}")

                # Kurze Pause für Animation
                await asyncio.sleep(0.5)

                return {
                    "found": True,
                    "handled": True,
                    "selector": selector,
                    "method": "auto_click"
                }

        except PlaywrightTimeout:
            continue
        except Exception as e:
            log.debug(f"Selector {selector} fehlgeschlagen: {e}")
            continue

    log.info("ℹ️  Kein Cookie-Banner gefunden (oder bereits geschlossen)")
    return {
        "found": False,
        "handled": False,
        "selector": None,
        "method": None
    }


async def wait_for_and_handle_cookie_banner(
    page: Page,
    auto_accept: bool = True,
    max_wait_seconds: int = 5
) -> Dict[str, Any]:
    """
    Wartet auf Cookie-Banner und behandelt ihn.

    Args:
        page: Playwright Page Objekt
        auto_accept: True = Akzeptieren, False = Ablehnen
        max_wait_seconds: Maximale Wartezeit

    Returns:
        Ergebnis-Dict
    """
    log.info(f"⏳ Warte bis {max_wait_seconds}s auf Cookie-Banner...")

    # Versuche mehrmals über die Zeitspanne
    check_interval = 0.5  # Alle 500ms prüfen
    attempts = int(max_wait_seconds / check_interval)

    for i in range(attempts):
        result = await check_and_handle_cookie_banner(
            page,
            auto_accept=auto_accept,
            timeout_ms=500  # Kurzer Timeout pro Versuch
        )

        if result["found"]:
            return result

        # Warte kurz und versuche erneut
        await asyncio.sleep(check_interval)

    return {
        "found": False,
        "handled": False,
        "selector": None,
        "method": "timeout"
    }


async def dismiss_overlays_and_popups(page: Page) -> List[str]:
    """
    Schließt alle Overlays, Popups und Banner.

    Returns:
        Liste der geschlossenen Elemente
    """
    closed = []

    # Cookie-Banner
    cookie_result = await check_and_handle_cookie_banner(page)
    if cookie_result["handled"]:
        closed.append(f"cookie_banner ({cookie_result['selector']})")

    # Newsletter Popups (häufig)
    newsletter_selectors = [
        "button[aria-label='Close']",
        "button.close-modal",
        "button.dismiss",
        ".modal-close",
        "button:has-text('Schließen')",
        "button:has-text('Close')",
        "button:has-text('Nein danke')",
        "button:has-text('Später')",
    ]

    for selector in newsletter_selectors:
        try:
            element = page.locator(selector).first
            if await element.is_visible(timeout=500):
                await element.click(timeout=2000)
                closed.append(f"popup ({selector})")
                await asyncio.sleep(0.3)
        except:
            continue

    if closed:
        log.info(f"✅ {len(closed)} Overlays geschlossen: {closed}")
    else:
        log.info("ℹ️  Keine Overlays gefunden")

    return closed


# Für direkten Import
__all__ = [
    "check_and_handle_cookie_banner",
    "wait_for_and_handle_cookie_banner",
    "dismiss_overlays_and_popups",
    "COOKIE_ACCEPT_SELECTORS",
    "COOKIE_REJECT_SELECTORS"
]
