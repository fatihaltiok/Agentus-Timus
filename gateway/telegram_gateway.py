"""
gateway/telegram_gateway.py

Telegram-Bot Gateway für Timus.
Eingehende Nachrichten → run_agent() → Antwort zurück an Telegram.

Konfiguration (.env):
    TELEGRAM_BOT_TOKEN   = dein Bot-Token von @BotFather
    TELEGRAM_ALLOWED_IDS = kommagetrennte User-IDs (optional, leer = alle erlaubt)

Befehle:
    /start                  Begrüßung
    /tasks                  Offene Tasks anzeigen
    /task <text>            Task zur autonomen Queue hinzufügen
    /remind <zeit> <text>   Erinnerung setzen (z.B. /remind 09:00 Meeting)
    /status                 Runner-Status + System-Info anzeigen
    <normaler Text>         Wird direkt an Timus weitergegeben
"""

import asyncio
import json
import logging
import os
import uuid
from pathlib import Path
from typing import Optional

from telegram import Update
from telegram.constants import ChatAction, ParseMode
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

log = logging.getLogger("TelegramGateway")

# Session-Mapping: Telegram-User-ID → Timus-Session-ID
_user_sessions: dict[int, str] = {}


def _get_session(user_id: int) -> str:
    """Gibt persistente Session-ID für einen Telegram-User zurück."""
    if user_id not in _user_sessions:
        _user_sessions[user_id] = f"tg_{user_id}_{uuid.uuid4().hex[:6]}"
    return _user_sessions[user_id]


def _get_allowed_ids() -> set[int]:
    """Liest erlaubte Telegram-User-IDs aus .env."""
    raw = os.getenv("TELEGRAM_ALLOWED_IDS", "").strip()
    if not raw:
        return set()  # Leer = alle erlaubt
    try:
        return {int(x.strip()) for x in raw.split(",") if x.strip()}
    except ValueError:
        log.warning("TELEGRAM_ALLOWED_IDS enthält ungültige Werte")
        return set()


def _is_allowed(user_id: int) -> bool:
    allowed = _get_allowed_ids()
    return not allowed or user_id in allowed


async def _send_long(update: Update, text: str) -> None:
    """Sendet lange Texte in Blöcken (Telegram-Limit: 4096 Zeichen)."""
    MAX = 4000
    if not text:
        text = "(kein Ergebnis)"
    for i in range(0, len(text), MAX):
        await update.message.reply_text(text[i : i + MAX])


# ──────────────────────────────────────────────────────────────────
# Handler
# ──────────────────────────────────────────────────────────────────

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if not _is_allowed(user.id):
        await update.message.reply_text("⛔ Kein Zugriff.")
        return
    session = _get_session(user.id)
    await update.message.reply_text(
        f"👋 Hallo {user.first_name}!\n"
        f"Ich bin Timus — dein autonomer KI-Assistent.\n\n"
        f"Session: `{session}`\n\n"
        f"Befehle:\n"
        f"  /tasks — offene Tasks anzeigen\n"
        f"  /task <text> — Task zur Queue hinzufügen\n"
        f"  /status — Runner-Status\n"
        f"  Oder einfach eine Frage stellen!",
        parse_mode=ParseMode.MARKDOWN,
    )


async def cmd_tasks(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_allowed(update.effective_user.id):
        return
    try:
        from orchestration.task_queue import get_queue
        queue = get_queue()
        stats = queue.stats()
        tasks = queue.get_all(limit=15)
        if not tasks:
            await update.message.reply_text("Keine Tasks vorhanden.")
            return
        icons = {"pending": "⏳", "in_progress": "🔄", "completed": "✅", "failed": "❌", "cancelled": "🚫"}
        prio_names = {0: "🔴", 1: "🟠", 2: "🟡", 3: "🟢"}
        lines = [f"📋 *Task-Queue* | {stats}\n"]
        for t in tasks:
            icon = icons.get(t.get("status", ""), "•")
            prio = prio_names.get(t.get("priority", 2), "•")
            desc = t.get("description", "")[:45]
            agent = (t.get("target_agent") or "auto")[:8]
            lines.append(f"{prio}{icon} `{t['id'][:8]}` [{agent}] {desc}")
        await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.MARKDOWN)
    except Exception as e:
        await update.message.reply_text(f"Fehler: {e}")


async def cmd_task(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Fügt einen neuen Task zur autonomen Queue hinzu."""
    if not _is_allowed(update.effective_user.id):
        return
    text = " ".join(context.args).strip()
    if not text:
        await update.message.reply_text("Verwendung: `/task <Beschreibung>`", parse_mode=ParseMode.MARKDOWN)
        return
    try:
        from orchestration.autonomous_runner import add_task
        task_id = add_task(text)
        await update.message.reply_text(
            f"✅ Task hinzugefügt!\n`{task_id[:8]}` — wird beim nächsten Heartbeat ausgeführt.",
            parse_mode=ParseMode.MARKDOWN,
        )
    except Exception as e:
        await update.message.reply_text(f"❌ Fehler: {e}")


async def cmd_remind(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    /remind <zeit> <text>
    Beispiele:
      /remind 09:00 Meeting vorbereiten
      /remind 14:30 morgen Arzttermin
      /remind 2026-02-22T09:00 Präsentation
    """
    if not _is_allowed(update.effective_user.id):
        return

    if not context.args or len(context.args) < 2:
        await update.message.reply_text(
            "Verwendung:\n"
            "`/remind 09:00 Erinnerungstext`\n"
            "`/remind 14:30 morgen Meeting`\n"
            "`/remind 2026-02-22T09:00 Präsentation`",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    time_str = context.args[0]
    reminder_text = " ".join(context.args[1:])

    # Zeit parsen
    run_at = _parse_reminder_time(time_str)
    if not run_at:
        await update.message.reply_text(
            f"❌ Zeit nicht erkannt: `{time_str}`\n"
            "Format: `HH:MM` oder `YYYY-MM-DDTHH:MM`",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    try:
        from orchestration.task_queue import get_queue, Priority, TaskType
        task_id = get_queue().add(
            description=f"⏰ Erinnerung: {reminder_text}",
            priority=Priority.HIGH,
            task_type=TaskType.SCHEDULED,
            target_agent="executor",
            run_at=run_at,
        )
        await update.message.reply_text(
            f"✅ Erinnerung gesetzt!\n"
            f"`{task_id[:8]}` — {reminder_text}\n"
            f"📅 Fällig: {run_at[:16].replace('T', ' ')} Uhr",
            parse_mode=ParseMode.MARKDOWN,
        )
    except Exception as e:
        await update.message.reply_text(f"❌ Fehler: {e}")


def _parse_reminder_time(time_str: str) -> Optional[str]:
    """Parst Zeitangaben in ISO-8601. Gibt None bei Fehler zurück."""
    from datetime import datetime, timedelta

    now = datetime.now()

    # Format: HH:MM (heute oder morgen wenn Zeit bereits vorbei)
    if len(time_str) == 5 and ":" in time_str:
        try:
            h, m = time_str.split(":")
            target = now.replace(hour=int(h), minute=int(m), second=0, microsecond=0)
            if target <= now:
                target += timedelta(days=1)
            return target.isoformat()
        except ValueError:
            return None

    # Format: ISO-8601 (2026-02-22T09:00)
    for fmt in ("%Y-%m-%dT%H:%M", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(time_str, fmt).isoformat()
        except ValueError:
            continue

    return None


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_allowed(update.effective_user.id):
        return
    try:
        from orchestration.scheduler import get_scheduler
        from orchestration.task_queue import get_queue
        from gateway.system_monitor import get_system_stats

        # Scheduler
        sched = get_scheduler()
        if sched:
            s = sched.get_status()
            sched_line = (
                f"{'🟢' if s['running'] else '🔴'} Scheduler | "
                f"{s['heartbeat_count']} Beats | alle {s['interval_minutes']} min"
            )
        else:
            sched_line = "⚠️ Scheduler nicht aktiv"

        # Queue
        stats = get_queue().stats()
        queue_line = (
            f"📋 Queue: ⏳{stats.get('pending',0)} "
            f"🔄{stats.get('in_progress',0)} "
            f"✅{stats.get('completed',0)} "
            f"❌{stats.get('failed',0)}"
        )

        # System
        sys_stats = await asyncio.to_thread(get_system_stats)
        sys_line = (
            f"💻 CPU {sys_stats['cpu_percent']}% | "
            f"RAM {sys_stats['ram_percent']}% "
            f"({sys_stats['ram_used_gb']}/{sys_stats['ram_total_gb']} GB) | "
            f"Disk {sys_stats['disk_percent']}%"
        )

        msg = f"🤖 *Timus Status*\n\n{sched_line}\n{queue_line}\n{sys_line}"
        await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)
    except Exception as e:
        await update.message.reply_text(f"Fehler: {e}")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Verarbeitet normale Textnachrichten → run_agent()."""
    user = update.effective_user
    if not _is_allowed(user.id):
        await update.message.reply_text("⛔ Kein Zugriff.")
        return

    text = (update.message.text or "").strip()
    if not text:
        return

    session_id = _get_session(user.id)
    log.info(f"Telegram [{user.id}] → Session {session_id}: {text[:60]}")

    # "Ich arbeite daran..." sofort senden
    await update.message.chat.send_action(ChatAction.TYPING)
    thinking_msg = await update.message.reply_text("🤔 Timus denkt...")

    try:
        from main_dispatcher import run_agent, get_agent_decision

        tools_desc = context.bot_data.get("tools_desc", "")
        agent = await get_agent_decision(text)
        log.info(f"  Agent gewählt: {agent.upper()}")

        # Typing-Indikator während Verarbeitung
        async def keep_typing():
            while True:
                await asyncio.sleep(4)
                try:
                    await update.message.chat.send_action(ChatAction.TYPING)
                except Exception:
                    break

        typing_task = asyncio.create_task(keep_typing())
        try:
            result = await run_agent(
                agent_name=agent,
                query=text,
                tools_description=tools_desc,
                session_id=session_id,
            )
        finally:
            typing_task.cancel()

        # Thinking-Nachricht löschen
        try:
            await thinking_msg.delete()
        except Exception:
            pass

        response = str(result) if result else "_(kein Ergebnis)_"
        await _send_long(update, response)

    except Exception as e:
        log.error(f"Fehler bei Telegram-Nachricht: {e}", exc_info=True)
        try:
            await thinking_msg.delete()
        except Exception:
            pass
        await update.message.reply_text(f"❌ Fehler: {e}")


# ──────────────────────────────────────────────────────────────────
# Gateway-Klasse
# ──────────────────────────────────────────────────────────────────

class TelegramGateway:
    """Startet und verwaltet den Telegram-Bot."""

    def __init__(self, token: str, tools_desc: str = ""):
        self.token = token
        self.tools_desc = tools_desc
        self._app: Optional[Application] = None

    async def start(self) -> bool:
        """Startet den Bot. Gibt False zurück wenn Token fehlt/ungültig."""
        if not self.token:
            log.warning("TELEGRAM_BOT_TOKEN nicht gesetzt — Gateway inaktiv")
            return False

        try:
            self._app = (
                Application.builder()
                .token(self.token)
                .build()
            )
            # Tools-Beschreibung in bot_data teilen
            self._app.bot_data["tools_desc"] = self.tools_desc

            # Handler registrieren
            self._app.add_handler(CommandHandler("start", cmd_start))
            self._app.add_handler(CommandHandler("tasks", cmd_tasks))
            self._app.add_handler(CommandHandler("task", cmd_task))
            self._app.add_handler(CommandHandler("remind", cmd_remind))
            self._app.add_handler(CommandHandler("status", cmd_status))
            self._app.add_handler(
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message)
            )

            await self._app.initialize()
            await self._app.start()
            await self._app.updater.start_polling(
                drop_pending_updates=True,
                allowed_updates=["message"],
            )
            log.info("✅ Telegram-Bot aktiv (Polling läuft)")
            return True

        except Exception as e:
            log.error(f"❌ Telegram-Bot Start fehlgeschlagen: {e}")
            return False

    async def stop(self) -> None:
        """Stoppt den Bot sauber."""
        if self._app:
            try:
                await self._app.updater.stop()
                await self._app.stop()
                await self._app.shutdown()
                log.info("Telegram-Bot gestoppt")
            except Exception as e:
                log.warning(f"Fehler beim Stoppen des Bots: {e}")
