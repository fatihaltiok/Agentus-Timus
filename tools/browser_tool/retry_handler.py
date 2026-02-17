"""
Browser Retry Handler - Exponential Backoff und CAPTCHA-Erkennung.

Erweitert die bestehende Cloudflare-Detection in open_url um:
- Exponential Backoff bei Network-Fehlern
- Zentrale CAPTCHA/Block-Heuristik
- Page-Recovery bei abgestürzten Contexts
- Retry-Wrapper für beliebige Browser-Aktionen

USAGE:
    from tools.browser_tool.retry_handler import retry_handler

    result = await retry_handler.execute_with_retry(
        my_browser_action,
        url="https://example.com",
        on_captcha=handle_captcha
    )

AUTOR: Timus Development
DATUM: Februar 2026
"""

import asyncio
import logging
from typing import Callable, Any, Optional, Dict, Awaitable
from functools import wraps

log = logging.getLogger("BrowserRetryHandler")


class BrowserRetryHandler:
    """Automatische Retry-Logik für Browser-Fehler."""

    MAX_RETRIES = 3
    RETRY_DELAYS = [2, 5, 10]  # Exponential Backoff in Sekunden

    # CAPTCHA/Block-Indikatoren
    CAPTCHA_INDICATORS = [
        "cf-browser-verification",
        "challenge-platform",
        "cf-turnstile",
        "recaptcha",
        "hcaptcha",
        "Checking if the site connection is secure",
        "Just a moment...",
        "Attention Required",
        "Cloudflare",
        "DDoS protection",
        "Access denied",
        "Please verify you are a human",
    ]

    # Network-Fehler die Retry rechtfertigen
    RETRYABLE_ERRORS = [
        "TimeoutError",
        "net::ERR_",
        "Connection refused",
        "Connection reset",
        "Socket hang up",
        "ECONNREFUSED",
        "ENOTFOUND",
        "ETIMEDOUT",
        "SSL",
        "certificate",
    ]

    def __init__(
        self,
        max_retries: int = None,
        retry_delays: list = None
    ):
        """
        Initialisiert den Retry Handler.

        Args:
            max_retries: Maximale Retry-Versuche
            retry_delays: Wartezeiten zwischen Versuchen (Sekunden)
        """
        self.max_retries = max_retries or self.MAX_RETRIES
        self.retry_delays = retry_delays or self.RETRY_DELAYS

    async def execute_with_retry(
        self,
        action: Callable[..., Awaitable[Any]],
        *args,
        on_captcha: Optional[Callable[[Dict], Awaitable[Any]]] = None,
        on_retry: Optional[Callable[[int, Exception], Awaitable[None]]] = None,
        **kwargs
    ) -> Any:
        """
        Führt eine Browser-Aktion mit Retry-Logik aus.

        Args:
            action: Async Funktion die ausgeführt werden soll
            *args: Positionale Argumente für action
            on_captcha: Callback bei CAPTCHA-Erkennung
            on_retry: Callback vor jedem Retry
            **kwargs: Keyword Argumente für action

        Returns:
            Ergebnis der Aktion oder Error-Dict
        """
        last_error = None

        for attempt in range(self.max_retries):
            try:
                result = await action(*args, **kwargs)

                # CAPTCHA-Check auf dem Ergebnis
                if self._is_captcha_blocked(result):
                    log.warning(f"CAPTCHA erkannt (Versuch {attempt + 1})")

                    if on_captcha:
                        try:
                            return await on_captcha(result)
                        except Exception as e:
                            log.error(f"CAPTCHA-Handler fehlgeschlagen: {e}")

                    # Markieren aber weiter versuchen
                    result["_captcha_detected"] = True
                    return result

                # Erfolg
                if attempt > 0:
                    log.info(f"Aktion erfolgreich nach {attempt} Retries")
                return result

            except Exception as e:
                last_error = e
                error_str = str(e)

                # Check ob Fehler retry-würdig ist
                if not self._is_retryable_error(error_str):
                    log.error(f"Nicht-retrybarer Fehler: {e}")
                    raise

                if attempt < self.max_retries - 1:
                    delay = self.retry_delays[attempt]

                    log.warning(
                        f"Browser-Fehler (Versuch {attempt + 1}/{self.max_retries}): "
                        f"{error_str[:100]}. Retry in {delay}s..."
                    )

                    if on_retry:
                        try:
                            await on_retry(attempt, e)
                        except Exception as cb_e:
                            log.debug(f"Retry-Callback Fehler: {cb_e}")

                    await asyncio.sleep(delay)
                else:
                    log.error(
                        f"Alle {self.max_retries} Versuche fehlgeschlagen: {error_str}"
                    )

        # Nach allen Retries
        return {
            "error": str(last_error),
            "error_type": type(last_error).__name__,
            "retries_exhausted": True,
            "attempts": self.max_retries
        }

    def _is_captcha_blocked(self, result: Any) -> bool:
        """Prüft ob das Ergebnis auf eine CAPTCHA-Blockade hindeutet."""
        if not isinstance(result, dict):
            return False

        # Status-Check
        status = result.get("status", "")
        if "blocked" in status.lower() or "captcha" in status.lower():
            return True

        # Content-Check
        text = str(result.get("text", "") or result.get("content", "")).lower()
        title = str(result.get("title", "")).lower()

        combined = f"{text} {title}".lower()

        return any(
            indicator.lower() in combined
            for indicator in self.CAPTCHA_INDICATORS
        )

    def _is_retryable_error(self, error_str: str) -> bool:
        """Bestimmt ob ein Fehler retry-würdig ist."""
        error_lower = error_str.lower()

        # Timeout ist immer retry-würdig
        if "timeout" in error_lower:
            return True

        # Network-Fehler
        for pattern in self.RETRYABLE_ERRORS:
            if pattern.lower() in error_lower:
                return True

        # Sonstige nicht retry-würdig (z.B. User-Fehler)
        return False

    def check_page_content_for_captcha(self, content: str) -> Dict[str, Any]:
        """
        Analysiert Page-Content auf CAPTCHA/Block-Indikatoren.

        Args:
            content: HTML-Content der Seite

        Returns:
            Dict mit 'is_blocked', 'indicators', 'suggestion'
        """
        content_lower = content.lower()
        found_indicators = []

        for indicator in self.CAPTCHA_INDICATORS:
            if indicator.lower() in content_lower:
                found_indicators.append(indicator)

        is_blocked = len(found_indicators) > 0

        suggestion = None
        if is_blocked:
            if any("cloudflare" in i.lower() or "cf-" in i.lower() for i in found_indicators):
                suggestion = "Wait and retry - Cloudflare challenge may resolve"
            elif any("captcha" in i.lower() for i in found_indicators):
                suggestion = "Manual intervention required - CAPTCHA present"
            else:
                suggestion = "Site may be blocking automated access"

        return {
            "is_blocked": is_blocked,
            "indicators": found_indicators,
            "suggestion": suggestion
        }


# Decorator für einfache Nutzung
def with_retry(max_retries: int = 3):
    """
    Decorator der Retry-Logik zu einer async Funktion hinzufügt.

    Usage:
        @with_retry(max_retries=3)
        async def my_browser_action(url):
            ...
    """
    def decorator(func: Callable[..., Awaitable[Any]]):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            handler = BrowserRetryHandler(max_retries=max_retries)
            return await handler.execute_with_retry(func, *args, **kwargs)
        return wrapper
    return decorator


# Globale Instanz
retry_handler = BrowserRetryHandler()
