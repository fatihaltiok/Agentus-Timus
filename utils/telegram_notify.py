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
from typing import Any, Dict, List, Optional

log = logging.getLogger("telegram_notify")

_FEEDBACK_SIGNAL_CODES = {
    "positive": "p",
    "negative": "n",
    "neutral": "u",
}
_FEEDBACK_SIGNAL_FROM_CODE = {v: k for k, v in _FEEDBACK_SIGNAL_CODES.items()}


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
    context: Optional[Dict[str, Any]] = None,
    feedback_targets: Optional[List[Dict[str, str]]] = None,
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

    any_sent = False
    try:
        from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup
        from orchestration.feedback_engine import get_feedback_engine

        keyboard = build_feedback_markup(
            action_id=action_id,
            hook_names=hook_names,
            context=context,
            feedback_targets=feedback_targets,
        )

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

    return any_sent


def build_feedback_callback_data(signal: str, token: str) -> str:
    """Erzeugt kompakte callback_data fuer Telegram (64-Byte-Limit)."""
    signal_code = _FEEDBACK_SIGNAL_CODES.get(signal, "u")
    return json.dumps({"type": "feedback", "s": signal_code, "t": str(token)}, separators=(",", ":"))


def decode_feedback_signal(signal_or_code: str) -> str:
    """Akzeptiert volle Signale und die kompakten Callback-Codes."""
    if signal_or_code in _FEEDBACK_SIGNAL_CODES:
        return signal_or_code
    return _FEEDBACK_SIGNAL_FROM_CODE.get(str(signal_or_code or "").strip(), "")


def build_feedback_markup(
    action_id: str,
    hook_names: Optional[List[str]] = None,
    context: Optional[Dict[str, Any]] = None,
    feedback_targets: Optional[List[Dict[str, str]]] = None,
):
    """Baut ein Feedback-Keyboard und registriert die Payload serverseitig."""
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    from orchestration.feedback_engine import get_feedback_engine

    token = get_feedback_engine().register_feedback_request(
        action_id=action_id,
        hook_names=hook_names,
        context=context,
        feedback_targets=feedback_targets,
    )
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("👍", callback_data=build_feedback_callback_data("positive", token)),
            InlineKeyboardButton("👎", callback_data=build_feedback_callback_data("negative", token)),
            InlineKeyboardButton("🤷", callback_data=build_feedback_callback_data("neutral", token)),
        ]
    ])
