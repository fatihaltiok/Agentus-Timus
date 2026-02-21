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
import base64
import io
import json
import logging
import os
import re
import uuid
from pathlib import Path
from typing import Optional

import httpx
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


_PROJECT_ROOT = Path(__file__).parent.parent


async def _send_long(update: Update, text: str) -> None:
    """Sendet lange Texte in Blöcken (Telegram-Limit: 4096 Zeichen)."""
    MAX = 4000
    if not text:
        text = "(kein Ergebnis)"
    for i in range(0, len(text), MAX):
        await update.message.reply_text(text[i : i + MAX])


async def _try_send_image(update: Update, result: str) -> bool:
    """
    Erkennt ob das Agent-Ergebnis ein Bild enthält und sendet es als Foto.
    Gibt True zurück wenn ein Bild gesendet wurde.

    Priorität:
      1. Lokale Datei (results/*.png) — zuverlässig, kein Ablauf
      2. HTTP-URL aus dem Ergebnis — als Fallback (DALL-E URLs verfallen nach 24h)
    """
    # 1. Lokalen Dateipfad suchen (results/DATUM_image_NAME.png)
    match = re.search(r'results/[\w\-]+\.(?:png|jpg|jpeg|webp)', result)
    if match:
        image_path = _PROJECT_ROOT / match.group(0)
        if image_path.exists():
            # Caption: Prompt-Teil aus der Antwort extrahieren
            prompt_match = re.search(r'(?:Prompt|prompt)[:\s]+(.{10,200})', result)
            caption = prompt_match.group(1).strip()[:1024] if prompt_match else "Timus hat dieses Bild generiert"
            try:
                with open(image_path, "rb") as f:
                    await update.message.reply_photo(photo=f, caption=caption)
                log.info(f"Bild gesendet: {image_path.name}")
                return True
            except Exception as e:
                log.error(f"Fehler beim Senden der lokalen Bilddatei: {e}")

    # 2. URL als Fallback (z.B. wenn kein b64 geliefert wurde)
    url_match = re.search(r'https://[^\s]+\.(?:png|jpg|jpeg|webp)[^\s]*', result)
    if url_match:
        image_url = url_match.group(0)
        try:
            await update.message.reply_photo(photo=image_url)
            log.info(f"Bild per URL gesendet: {image_url[:60]}...")
            return True
        except Exception as e:
            log.error(f"Fehler beim Senden der Bild-URL: {e}")

    return False


# ──────────────────────────────────────────────────────────────────
# Voice-System (Whisper STT + Inworld.AI TTS)
# ──────────────────────────────────────────────────────────────────

_whisper_model = None  # Lazy-Init beim ersten Voice-Message


def _get_whisper():
    """Lädt Whisper beim ersten Aufruf (CUDA wenn verfügbar, sonst CPU)."""
    global _whisper_model
    if _whisper_model is None:
        from faster_whisper import WhisperModel
        try:
            _whisper_model = WhisperModel("medium", device="cuda", compute_type="float16")
            log.info("Whisper geladen (CUDA)")
        except Exception:
            _whisper_model = WhisperModel("medium", device="cpu", compute_type="int8")
            log.info("Whisper geladen (CPU Fallback)")
    return _whisper_model


def _transcribe_sync(ogg_bytes: bytes) -> str:
    """OGG-Bytes → Text (synchron, für asyncio.to_thread)."""
    import numpy as np
    from pydub import AudioSegment

    audio = AudioSegment.from_ogg(io.BytesIO(ogg_bytes))
    audio = audio.set_channels(1).set_frame_rate(16000)
    samples = np.array(audio.get_array_of_samples(), dtype=np.float32) / 32768.0

    whisper = _get_whisper()
    segments, _ = whisper.transcribe(samples, language="de", vad_filter=True)
    return " ".join(s.text.strip() for s in segments)


async def _transcribe_ogg(ogg_bytes: bytes) -> str:
    """Async-Wrapper für Whisper-Transkription."""
    return await asyncio.to_thread(_transcribe_sync, ogg_bytes)


async def _synthesize_voice(text: str) -> Optional[bytes]:
    """
    Text → OGG/Opus-Bytes via Inworld.AI TTS.
    Gibt None zurück wenn INWORLD_API_KEY nicht gesetzt oder Fehler.
    """
    api_key = os.getenv("INWORLD_API_KEY", "")
    if not api_key or not text.strip():
        return None

    voice   = os.getenv("INWORLD_VOICE", "Ashley")
    model   = os.getenv("INWORLD_MODEL", "inworld-tts-1.5-max")
    rate    = float(os.getenv("INWORLD_SPEAKING_RATE", "1.3"))
    temp    = float(os.getenv("INWORLD_TEMPERATURE", "1.5"))

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                "https://api.inworld.ai/tts/v1/voice",
                json={
                    "text": text[:500],
                    "voiceId": voice,
                    "modelId": model,
                    "voiceSettings": {"speaking_rate": rate},
                    "temperature": temp,
                },
                headers={
                    "Authorization": f"Basic {api_key}",
                    "Content-Type": "application/json",
                },
            )
            resp.raise_for_status()

        mp3_bytes = base64.b64decode(resp.json()["audioContent"])

        # MP3 → OGG/Opus (Telegram erwartet OGG)
        from pydub import AudioSegment
        audio = AudioSegment.from_mp3(io.BytesIO(mp3_bytes))
        ogg_buf = io.BytesIO()
        audio.export(ogg_buf, format="ogg", codec="libopus")
        return ogg_buf.getvalue()

    except Exception as e:
        log.error(f"TTS Fehler: {e}")
        return None


async def _keep_typing(update: Update) -> None:
    """Hält den Typing-Indikator aktiv (alle 4s erneuern)."""
    while True:
        await asyncio.sleep(4)
        try:
            await update.message.chat.send_action(ChatAction.TYPING)
        except Exception:
            break


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

        typing_task = asyncio.create_task(_keep_typing(update))
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

        # Bild-Erkennung: wenn der Agent ein Bild generiert hat → als Foto senden
        image_sent = await _try_send_image(update, response)
        if not image_sent:
            await _send_long(update, response)

    except Exception as e:
        log.error(f"Fehler bei Telegram-Nachricht: {e}", exc_info=True)
        try:
            await thinking_msg.delete()
        except Exception:
            pass
        await update.message.reply_text(f"❌ Fehler: {e}")


async def handle_voice_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Verarbeitet eingehende Telegram-Sprachnachrichten.

    Ablauf:
      1. OGG-Datei herunterladen
      2. Whisper-Transkription (STT)
      3. Timus Agent-Pipeline (run_agent)
      4. Inworld.AI TTS → OGG → reply_voice()
         (Fallback: reply_text() wenn kein INWORLD_API_KEY)
    """
    user = update.effective_user
    if not _is_allowed(user.id):
        await update.message.reply_text("⛔ Kein Zugriff.")
        return

    session_id = _get_session(user.id)
    await update.message.chat.send_action(ChatAction.TYPING)
    thinking_msg = await update.message.reply_text("🎤 Verstehe deine Stimme…")

    try:
        # 1. Sprachnachricht herunterladen (OGG/Opus von Telegram)
        voice_file = await context.bot.get_file(update.message.voice.file_id)
        ogg_bytes = bytes(await voice_file.download_as_bytearray())

        # 2. Transkribieren
        await update.message.chat.send_action(ChatAction.TYPING)
        user_text = await _transcribe_ogg(ogg_bytes)

        if not user_text.strip():
            await thinking_msg.edit_text("❌ Konnte deine Stimme nicht verstehen. Bitte nochmal versuchen.")
            return

        log.info(f"Voice [{user.id}] transkribiert: {user_text[:80]}")
        await thinking_msg.edit_text(
            f"🎤 _{user_text}_\n\n🤔 Timus denkt…",
            parse_mode=ParseMode.MARKDOWN,
        )

        # 3. Agent-Pipeline (gleiche Logik wie handle_message)
        from main_dispatcher import run_agent, get_agent_decision
        tools_desc = context.bot_data.get("tools_desc", "")
        agent = await get_agent_decision(user_text)
        log.info(f"  Voice-Agent: {agent.upper()}")

        typing_task = asyncio.create_task(_keep_typing(update))
        try:
            result = await run_agent(
                agent_name=agent,
                query=user_text,
                tools_description=tools_desc,
                session_id=session_id,
            )
        finally:
            typing_task.cancel()

        try:
            await thinking_msg.delete()
        except Exception:
            pass

        response = str(result) if result else "Ich konnte keine Antwort generieren."

        # 4. Bild-Check (falls CreativeAgent ein Bild erzeugt hat)
        image_sent = await _try_send_image(update, response)

        # 5. TTS → Sprachnachricht zurück
        await update.message.chat.send_action(ChatAction.RECORD_VOICE)
        ogg_audio = await _synthesize_voice(response)

        if ogg_audio:
            # Kurze Caption: erste 200 Zeichen der Antwort
            caption = response[:200] + ("…" if len(response) > 200 else "")
            await update.message.reply_voice(
                voice=io.BytesIO(ogg_audio),
                caption=caption if not image_sent else None,
            )
        else:
            # Kein TTS konfiguriert → Textantwort
            if not image_sent:
                await _send_long(update, response)

    except Exception as e:
        log.error(f"Voice-Handler Fehler: {e}", exc_info=True)
        try:
            await thinking_msg.delete()
        except Exception:
            pass
        await update.message.reply_text(f"❌ Fehler bei Sprachverarbeitung: {e}")


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
            self._app.add_handler(
                MessageHandler(filters.VOICE, handle_voice_message)
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
