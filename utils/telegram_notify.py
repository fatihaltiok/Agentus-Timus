"""
utils/telegram_notify.py — Zentraler Telegram-Sender (DRY-Refactoring)

Einheitlicher Telegram-Sender für alle Autonomie-Module.
Liest TELEGRAM_BOT_TOKEN + TELEGRAM_ALLOWED_IDS aus os.getenv().

Verwendung:
    from utils.telegram_notify import send_telegram
    await send_telegram("Hallo! 🎉")

M16: send_with_feedback() sendet Nachrichten mit 👍/👎/🤷 InlineKeyboard.
"""

import json
import logging
import os
from typing import List, Optional

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


async def send_with_feedback(
    msg: str,
    action_id: str,
    hook_names: Optional[List[str]] = None,
    parse_mode: str = "Markdown",
) -> bool:
    """
    Sendet eine Telegram-Nachricht mit InlineKeyboard [👍][👎][🤷] für M16-Feedback.

    Args:
        msg: Die Nachricht
        action_id: ID der Aktion (für FeedbackEngine)
        hook_names: Betroffene behavior_hooks
        parse_mode: "Markdown" oder "HTML"

    Returns:
        True wenn erfolgreich gesendet
    """
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    allowed_ids = os.getenv("TELEGRAM_ALLOWED_IDS", "").strip()

    if not token or not allowed_ids:
        log.debug("Telegram Feedback: Token oder IDs fehlen — übersprungen")
        return False

    chat_ids = []
    for x in allowed_ids.split(","):
        x = x.strip()
        if x:
            try:
                chat_ids.append(int(x))
            except ValueError:
                pass

    if not chat_ids:
        return False

    hooks_json = json.dumps(hook_names or [], ensure_ascii=False)
    callback_prefix = json.dumps({"aid": action_id, "hooks": hooks_json}, ensure_ascii=False)

    any_sent = False
    try:
        from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup

        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("👍", callback_data=json.dumps({"fb": "positive", "aid": action_id, "hooks": hooks_json})),
                InlineKeyboardButton("👎", callback_data=json.dumps({"fb": "negative", "aid": action_id, "hooks": hooks_json})),
                InlineKeyboardButton("🤷", callback_data=json.dumps({"fb": "neutral",  "aid": action_id, "hooks": hooks_json})),
            ]
        ])

        bot = Bot(token=token)
        try:
            for chat_id in chat_ids:
                try:
                    await bot.send_message(
                        chat_id=chat_id,
                        text=msg,
                        parse_mode=parse_mode,
                        reply_markup=keyboard,
                    )
                    log.info("Telegram Feedback-Buttons an %d gesendet (action=%s)", chat_id, action_id)
                    any_sent = True
                except Exception as e:
                    log.warning("Telegram Feedback: Senden an %d fehlgeschlagen: %s", chat_id, e)
        finally:
            try:
                await bot.close()
            except Exception:
                pass
    except ImportError:
        log.debug("Telegram: python-telegram-bot nicht installiert")
    except Exception as e:
        log.warning("Telegram Feedback: Fehler: %s", e)

    # Sicherheits-Cleanup: callback_prefix wurde nur zur Lesbarkeit definiert
    del callback_prefix
    return any_sent
