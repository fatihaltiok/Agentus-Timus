# tools/cookie_banner_tool/tool.py
"""
Cookie-Banner Auto-Detection Tool

Erkennt und akzeptiert automatisch Cookie-Banner auf Webseiten.

Features:
- Multi-Backend OCR (EasyOCR, Tesseract, PaddleOCR, TrOCR)
- Erkennt Cookie-relevante Texte in mehreren Sprachen
- Findet "Akzeptieren" / "Accept" / "OK" Buttons
- Klickt automatisch
- Verifikation nach Klick
- Fallback-Strategien

Typische Cookie-Banner Begriffe:
- Deutsch: "Cookie", "Cookies", "Akzeptieren", "Alle akzeptieren", "Zustimmen"
- Englisch: "Cookie", "Accept", "Accept all", "Agree", "OK", "Got it"
- Französisch: "Accepter", "Tout accepter"
- Spanisch: "Aceptar", "Aceptar todas"
"""

import logging
import os
import sys
import asyncio
import re
from pathlib import Path
from typing import Union, Optional, List, Dict, Tuple
from dataclasses import dataclass

from jsonrpcserver import method, Success, Error
from tools.universal_tool_caller import register_tool

# --- Setup ---
log = logging.getLogger(__name__)
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

# Screenshot & Image Processing
try:
    import mss
    from PIL import Image, ImageDraw
    import io
    MSS_AVAILABLE = True
except ImportError:
    MSS_AVAILABLE = False
    log.warning("⚠️ mss/PIL nicht verfügbar. Cookie-Banner-Detection eingeschränkt.")

# OCR Engine importieren
try:
    from tools.engines.ocr_engine import ocr_engine_instance
    OCR_AVAILABLE = True
except ImportError:
    OCR_AVAILABLE = False
    log.warning("⚠️ OCR Engine nicht verfügbar.")

# Mouse Tool für Klicks (Import nur die Tool-Registry, nicht die Funktionen direkt)
MOUSE_AVAILABLE = True  # Wird über RPC aufgerufen, nicht direkt importiert


# --- Konfiguration ---
ACTIVE_MONITOR = int(os.getenv("ACTIVE_MONITOR", "1"))

# Cookie-Banner Keywords (Priorität)
COOKIE_KEYWORDS = {
    "high_priority": [
        # Deutsch
        "alle akzeptieren", "alle cookies akzeptieren", "alles akzeptieren",
        "akzeptieren und schließen", "einverstanden",
        # Englisch
        "accept all", "accept all cookies", "accept cookies",
        "agree and close", "i agree", "got it",
        # Französisch
        "tout accepter", "accepter tout",
        # Spanisch
        "aceptar todas", "aceptar todo",
    ],
    "medium_priority": [
        "akzeptieren", "zustimmen", "ok",
        "accept", "agree", "allow",
        "accepter", "aceptar",
    ],
    "low_priority": [
        "schließen", "verstanden",
        "close", "dismiss", "continue",
        "fermer", "cerrar",
    ]
}

# Cookie-Hinweis Keywords (um Banner zu identifizieren)
BANNER_DETECTION_KEYWORDS = [
    "cookie", "cookies", "datenschutz", "privacy",
    "daten", "data protection", "gdpr", "tracking",
]


@dataclass
class CookieButton:
    """Repräsentiert einen gefundenen Cookie-Button."""
    text: str
    x: int
    y: int
    width: int
    height: int
    confidence: float
    priority: str  # "high", "medium", "low"

    @property
    def center_x(self) -> int:
        return self.x + self.width // 2

    @property
    def center_y(self) -> int:
        return self.y + self.height // 2


def normalize_text(text: str) -> str:
    """Normalisiert Text für Vergleich."""
    return re.sub(r'\s+', ' ', text.lower().strip())


def is_cookie_related(text: str) -> bool:
    """Prüft ob Text Cookie-bezogen ist."""
    normalized = normalize_text(text)
    return any(keyword in normalized for keyword in BANNER_DETECTION_KEYWORDS)


def get_button_priority(text: str) -> Optional[str]:
    """Ermittelt Priorität eines Buttons basierend auf Text."""
    normalized = normalize_text(text)

    for keyword in COOKIE_KEYWORDS["high_priority"]:
        if keyword in normalized:
            return "high"

    for keyword in COOKIE_KEYWORDS["medium_priority"]:
        if keyword in normalized:
            return "medium"

    for keyword in COOKIE_KEYWORDS["low_priority"]:
        if keyword in normalized:
            return "low"

    return None


def get_screenshot_pil() -> Optional[Image.Image]:
    """Erstellt Screenshot als PIL Image."""
    if not MSS_AVAILABLE:
        return None

    try:
        with mss.mss() as sct:
            monitors = sct.monitors
            if ACTIVE_MONITOR < len(monitors):
                monitor = monitors[ACTIVE_MONITOR]
            else:
                monitor = monitors[1] if len(monitors) > 1 else monitors[0]

            sct_img = sct.grab(monitor)
            img = Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")
            return img
    except Exception as e:
        log.error(f"Screenshot-Fehler: {e}")
        return None


def find_cookie_buttons(ocr_result: dict) -> List[CookieButton]:
    """Findet Cookie-Buttons aus OCR-Ergebnissen."""
    buttons = []

    extracted_texts = ocr_result.get("extracted_text", [])

    for item in extracted_texts:
        text = item.get("text", "")
        if not text:
            continue

        # Prüfe ob es ein Accept-Button sein könnte
        priority = get_button_priority(text)
        if not priority:
            continue

        bbox = item.get("bbox", [])
        confidence = item.get("confidence", 0.0)

        if len(bbox) >= 4:
            x, y, x2, y2 = bbox[:4]
            width = x2 - x
            height = y2 - y

            button = CookieButton(
                text=text,
                x=x,
                y=y,
                width=width,
                height=height,
                confidence=confidence,
                priority=priority
            )
            buttons.append(button)
            log.debug(f"Button gefunden: '{text}' @ ({x},{y}) [Prio: {priority}]")

    return buttons


def has_cookie_banner(ocr_result: dict, min_cookie_mentions: int = 1) -> bool:
    """Prüft ob ein Cookie-Banner vorhanden ist."""
    extracted_texts = ocr_result.get("extracted_text", [])

    cookie_count = 0
    for item in extracted_texts:
        text = item.get("text", "")
        if is_cookie_related(text):
            cookie_count += 1
            if cookie_count >= min_cookie_mentions:
                return True

    return False


async def click_button(button: CookieButton, verify: bool = True) -> bool:
    """Klickt auf einen Button via RPC."""
    try:
        # Importiere call_tool lokal
        import httpx
        import json
        import os

        mcp_url = os.getenv("MCP_URL", "http://127.0.0.1:5000")

        log.info(f"🖱️ Klicke auf Button: '{button.text}' @ ({button.center_x}, {button.center_y})")

        # RPC-Aufruf
        method = "click_with_verification" if verify else "click_at"
        payload = {
            "jsonrpc": "2.0",
            "method": method,
            "params": {"x": button.center_x, "y": button.center_y},
            "id": 1
        }

        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(mcp_url, json=payload)
            data = response.json()

            if "error" in data:
                log.warning(f"⚠️ Klick fehlgeschlagen: {data['error']}")
                return False

            result = data.get("result", {})
            success = result.get("success", False) if verify else not result.get("error")

            if success:
                log.info(f"✅ Klick erfolgreich auf '{button.text}'")
            else:
                log.warning(f"⚠️ Klick fehlgeschlagen auf '{button.text}'")

            return success

    except Exception as e:
        log.error(f"Fehler beim Klick auf Button: {e}")
        return False


@method
async def cookie_banner_health() -> Union[Success, Error]:
    """
    Health-Check für das Cookie-Banner Tool.

    Returns:
        Success mit Status-Info oder Error
    """
    try:
        issues = []

        if not OCR_AVAILABLE:
            issues.append("OCR Engine nicht verfügbar")

        if not MSS_AVAILABLE:
            issues.append("mss/PIL nicht verfügbar (Screenshots)")

        # Mouse Tool wird via RPC aufgerufen, immer verfügbar wenn MCP-Server läuft

        if issues:
            return Error(
                code=-32091,
                message=f"Cookie-Banner Tool eingeschränkt: {', '.join(issues)}"
            )

        return Success({
            "status": "healthy",
            "ocr_available": OCR_AVAILABLE,
            "ocr_backend": os.getenv("OCR_BACKEND", "auto"),
            "screenshot_available": MSS_AVAILABLE,
            "mouse_available": MOUSE_AVAILABLE,
            "active_monitor": ACTIVE_MONITOR,
            "supported_languages": [
                "Deutsch", "Englisch", "Französisch", "Spanisch"
            ],
            "detection_keywords": len(BANNER_DETECTION_KEYWORDS),
            "accept_patterns": sum(len(v) for v in COOKIE_KEYWORDS.values())
        })

    except Exception as e:
        log.error(f"Cookie-Banner Health-Check fehlgeschlagen: {e}", exc_info=True)
        return Error(code=-32092, message=f"Health-Check fehlgeschlagen: {e}")


@method
async def detect_cookie_banner(
    click_accept: Optional[bool] = False,
    verify_click: Optional[bool] = True
) -> Union[Success, Error]:
    """
    Erkennt Cookie-Banner auf dem aktuellen Bildschirm.

    Args:
        click_accept: Wenn True, klickt automatisch auf "Akzeptieren"
        verify_click: Wenn True, verifiziert Klick (langsamer aber sicherer)

    Returns:
        Success mit Informationen über gefundene Banner/Buttons oder Error
    """
    try:
        if not OCR_AVAILABLE:
            return Error(code=-32093, message="OCR Engine nicht verfügbar")

        if not MSS_AVAILABLE:
            return Error(code=-32094, message="Screenshot nicht möglich (mss/PIL fehlt)")

        log.info("🍪 Suche nach Cookie-Banner...")

        # Screenshot machen
        screenshot = get_screenshot_pil()
        if not screenshot:
            return Error(code=-32095, message="Screenshot fehlgeschlagen")

        log.debug(f"Screenshot: {screenshot.size[0]}x{screenshot.size[1]}")

        # OCR durchführen
        ocr_result = await asyncio.to_thread(
            ocr_engine_instance.process,
            screenshot,
            with_boxes=True
        )

        text_count = ocr_result.get("count", 0)
        log.debug(f"OCR: {text_count} Textblöcke gefunden")

        # Prüfe ob Cookie-Banner vorhanden
        has_banner = has_cookie_banner(ocr_result)

        if not has_banner:
            return Success({
                "cookie_banner_detected": False,
                "message": "Kein Cookie-Banner gefunden",
                "text_blocks_analyzed": text_count
            })

        log.info("✅ Cookie-Banner erkannt!")

        # Finde Accept-Buttons
        buttons = find_cookie_buttons(ocr_result)

        if not buttons:
            return Success({
                "cookie_banner_detected": True,
                "accept_button_found": False,
                "message": "Cookie-Banner gefunden, aber kein Akzeptieren-Button erkannt",
                "text_blocks_analyzed": text_count
            })

        # Sortiere Buttons nach Priorität
        priority_order = {"high": 0, "medium": 1, "low": 2}
        buttons.sort(key=lambda b: (priority_order[b.priority], -b.confidence))

        best_button = buttons[0]
        log.info(f"✅ Bester Button: '{best_button.text}' (Prio: {best_button.priority}, Conf: {best_button.confidence:.0%})")

        # Klicken wenn gewünscht
        clicked = False
        click_success = False

        if click_accept:

            # Versuche besten Button
            click_success = await click_button(best_button, verify=verify_click)
            clicked = True

            # Bei Fehler: Versuche nächsten Button
            if not click_success and len(buttons) > 1:
                log.info("Versuche nächsten Button...")
                click_success = await click_button(buttons[1], verify=verify_click)

        return Success({
            "cookie_banner_detected": True,
            "accept_button_found": True,
            "button_text": best_button.text,
            "button_position": {
                "x": best_button.center_x,
                "y": best_button.center_y
            },
            "button_priority": best_button.priority,
            "button_confidence": best_button.confidence,
            "total_buttons_found": len(buttons),
            "all_buttons": [
                {
                    "text": b.text,
                    "x": b.center_x,
                    "y": b.center_y,
                    "priority": b.priority,
                    "confidence": b.confidence
                }
                for b in buttons[:5]  # Maximal 5 Buttons zurückgeben
            ],
            "clicked": clicked,
            "click_success": click_success if clicked else None,
            "message": (
                f"Cookie-Banner akzeptiert: '{best_button.text}'"
                if clicked and click_success
                else f"Cookie-Banner erkannt, Button gefunden: '{best_button.text}'"
            )
        })

    except Exception as e:
        log.error(f"Fehler bei Cookie-Banner Detection: {e}", exc_info=True)
        return Error(code=-32099, message=f"Cookie-Banner Detection fehlgeschlagen: {e}")


@method
async def auto_accept_cookies(
    max_attempts: Optional[int] = 1,
    wait_between_attempts: Optional[float] = 2.0
) -> Union[Success, Error]:
    """
    Automatisches Akzeptieren von Cookie-Bannern.

    Versucht mehrfach Cookie-Banner zu finden und zu akzeptieren.
    Nützlich wenn Banner verzögert lädt.

    Args:
        max_attempts: Maximale Anzahl Versuche (Standard: 1)
        wait_between_attempts: Wartezeit zwischen Versuchen in Sekunden (Standard: 2.0)

    Returns:
        Success wenn erfolgreich, Error bei Fehler
    """
    try:
        log.info(f"🍪 Auto-Accept: {max_attempts} Versuch(e)")

        for attempt in range(max_attempts):
            if attempt > 0:
                log.info(f"Versuch {attempt + 1}/{max_attempts}...")
                await asyncio.sleep(wait_between_attempts)

            result = await detect_cookie_banner(click_accept=True, verify_click=True)

            if isinstance(result, Error):
                if attempt < max_attempts - 1:
                    log.warning(f"Versuch {attempt + 1} fehlgeschlagen: {result.message}")
                    continue
                else:
                    return result

            data = result.data

            # Banner gefunden und geklickt?
            if data.get("clicked") and data.get("click_success"):
                return Success({
                    "status": "success",
                    "attempts": attempt + 1,
                    "button_clicked": data.get("button_text"),
                    "message": f"Cookie-Banner nach {attempt + 1} Versuch(en) akzeptiert"
                })

            # Banner gefunden aber nicht geklickt?
            if data.get("cookie_banner_detected") and not data.get("accept_button_found"):
                return Success({
                    "status": "banner_found_no_button",
                    "attempts": attempt + 1,
                    "message": "Cookie-Banner gefunden, aber kein Akzeptieren-Button erkannt"
                })

            # Kein Banner gefunden
            if not data.get("cookie_banner_detected"):
                return Success({
                    "status": "no_banner",
                    "attempts": attempt + 1,
                    "message": "Kein Cookie-Banner gefunden"
                })

        return Success({
            "status": "max_attempts_reached",
            "attempts": max_attempts,
            "message": f"Kein Cookie-Banner nach {max_attempts} Versuch(en) gefunden"
        })

    except Exception as e:
        log.error(f"Fehler bei Auto-Accept: {e}", exc_info=True)
        return Error(code=-32099, message=f"Auto-Accept fehlgeschlagen: {e}")


# --- Registrierung ---
register_tool("cookie_banner_health", cookie_banner_health)
register_tool("detect_cookie_banner", detect_cookie_banner)
register_tool("auto_accept_cookies", auto_accept_cookies)

log.info("✅ Cookie-Banner Tool (cookie_banner_health, detect_cookie_banner, auto_accept_cookies) registriert.")
