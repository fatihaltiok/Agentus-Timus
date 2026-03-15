"""
utils/telegram_notify.py — Zentraler Telegram-Sender (DRY-Refactoring)

Einheitlicher Telegram-Sender für alle Autonomie-Module.
Liest TELEGRAM_BOT_TOKEN + TELEGRAM_ALLOWED_IDS aus os.getenv().

Digest-Modus (Standard):
    send_telegram() puffert Nachrichten und schickt alle 30 Minuten einen
    Sammel-Block. Sofort-Versand über urgent=True oder send_with_feedback().
    Intervall steuerbar per TELEGRAM_DIGEST_INTERVAL_MINUTES (default: 30).

Verwendung:
    from utils.telegram_notify import send_telegram
    await send_telegram("Hallo!")              # gebuffert
    await send_telegram("FEHLER!", urgent=True) # sofort

M16: send_with_feedback() sendet immer sofort (interaktiv, braucht Feedback-Buttons).
"""

import json
import logging
import os
import time
from typing import Any, Dict, List, Optional

log = logging.getLogger("telegram_notify")

_FEEDBACK_SIGNAL_CODES = {
    "positive": "p",
    "negative": "n",
    "neutral": "u",
}
_FEEDBACK_SIGNAL_FROM_CODE = {v: k for k, v in _FEEDBACK_SIGNAL_CODES.items()}

# ── Digest-Buffer ────────────────────────────────────────────────────────────
_buf: List[str] = []
_last_flush: float = 0.0


def _digest_interval_seconds() -> float:
    return float(os.getenv("TELEGRAM_DIGEST_INTERVAL_MINUTES", "30")) * 60


def _should_flush() -> bool:
    return (time.monotonic() - _last_flush) >= _digest_interval_seconds()


# ── Interner Low-Level-Sender ────────────────────────────────────────────────

async def _send_raw(msg: str, parse_mode: str = "Markdown") -> bool:
    """Schickt eine Nachricht direkt ohne Buffer."""
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

    # Telegram-Limit: 4096 Zeichen pro Nachricht
    if len(msg) > 4000:
        msg = msg[:3970] + "\n\n_[...gekürzt]_"

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


async def _flush_buffer() -> bool:
    """Fasst gepufferte Nachrichten zu einem Digest zusammen und sendet ihn."""
    global _buf, _last_flush

    if not _buf:
        _last_flush = time.monotonic()
        return False

    count = len(_buf)
    label = "Meldung" if count == 1 else "Meldungen"
    lines = [f"📬 *Timus — {count} {label}*"]
    for entry in _buf:
        lines.append("─" * 24)
        lines.append(entry)

    digest = "\n".join(lines)
    _buf.clear()
    _last_flush = time.monotonic()

    log.debug("Telegram Digest: %d Meldungen gesendet", count)
    return await _send_raw(digest)


# ── Öffentliche API ──────────────────────────────────────────────────────────

async def send_telegram(msg: str, parse_mode: str = "Markdown", urgent: bool = False) -> bool:
    """
    Sendet eine Nachricht via Telegram.

    Standardmäßig wird die Nachricht gepuffert und mit anderen Meldungen
    alle TELEGRAM_DIGEST_INTERVAL_MINUTES (default: 30) Minuten als Digest
    verschickt.

    urgent=True umgeht den Buffer (z.B. für kritische Fehler-Alerts).
    """
    global _buf, _last_flush

    if urgent:
        log.debug("Telegram [urgent]: sofort senden")
        return await _send_raw(msg, parse_mode)

    _buf.append(msg)

    if _should_flush():
        return await _flush_buffer()

    log.debug(
        "Telegram: Nachricht gepuffert (%d im Buffer, nächster Flush in %.0fs)",
        len(_buf),
        max(0, _digest_interval_seconds() - (time.monotonic() - _last_flush)),
    )
    return True


async def flush_telegram_digest() -> bool:
    """Explizites Flushen des Buffers — z.B. beim Herunterfahren."""
    return await _flush_buffer()


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

    Immer sofort — interaktive Nachrichten brauchen unmittelbare Zustellung.
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
