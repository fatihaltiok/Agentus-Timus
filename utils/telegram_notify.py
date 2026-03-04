"""
utils/telegram_notify.py — Zentraler Telegram-Sender (DRY-Refactoring)

Einheitlicher Telegram-Sender für alle Autonomie-Module.
Liest TELEGRAM_BOT_TOKEN + TELEGRAM_ALLOWED_IDS aus os.getenv().

Verwendung:
    from utils.telegram_notify import send_telegram
    await send_telegram("Hallo! 🎉")
"""

import logging
import os
from typing import Optional

log = logging.getLogger("telegram_notify")


async def send_telegram(msg: str, parse_mode: str = "Markdown") -> bool:
    """
    Sendet eine Nachricht via Telegram an alle konfigurierten Chat-IDs.

    Args:
        msg: Die zu sendende Nachricht
        parse_mode: "Markdown" (default) oder "HTML"

    Returns:
        True wenn mindestens eine Nachricht erfolgreich gesendet wurde, sonst False
    """
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    allowed_ids = os.getenv("TELEGRAM_ALLOWED_IDS", "").strip()

    if not token or not allowed_ids:
        log.debug("Telegram: TELEGRAM_BOT_TOKEN oder TELEGRAM_ALLOWED_IDS fehlt — übersprungen")
        return False

    chat_ids = []
    for x in allowed_ids.split(","):
        x = x.strip()
        if x:
            try:
                chat_ids.append(int(x))
            except ValueError:
                log.warning("Telegram: Ungültige Chat-ID ignoriert: %r", x)

    if not chat_ids:
        log.warning("Telegram: Keine gültigen Chat-IDs konfiguriert")
        return False

    any_sent = False
    try:
        from telegram import Bot

        bot = Bot(token=token)
        try:
            for chat_id in chat_ids:
                try:
                    await bot.send_message(
                        chat_id=chat_id,
                        text=msg,
                        parse_mode=parse_mode,
                    )
                    log.info("Telegram: Nachricht an %d gesendet", chat_id)
                    any_sent = True
                except Exception as e:
                    log.warning("Telegram: Senden an %d fehlgeschlagen: %s", chat_id, e)
        finally:
            try:
                await bot.close()
            except Exception:
                pass
    except ImportError:
        log.debug("Telegram: python-telegram-bot nicht installiert")
    except Exception as e:
        log.warning("Telegram: Fehler beim Senden: %s", e)

    return any_sent
