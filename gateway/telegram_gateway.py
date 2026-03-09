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
    /approvals [limit]      Offene Audit-Freigaben anzeigen
    /approve <id> [note]    Freigabe erteilen
    /reject <id> [note]     Freigabe ablehnen
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
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from gateway.status_snapshot import collect_status_snapshot, format_status_message
from utils.telegram_notify import build_feedback_markup, decode_feedback_signal

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


async def _send_long(update: Update, text: str, parse_mode: Optional[str] = None) -> None:
    """Sendet lange Texte in Blöcken (Telegram-Limit: 4096 Zeichen)."""
    MAX = 4000
    if not text:
        text = "(kein Ergebnis)"
    for i in range(0, len(text), MAX):
        await update.message.reply_text(text[i : i + MAX], parse_mode=parse_mode)


def _looks_like_browser_ui_flow(query: str) -> bool:
    query_lower = str(query or "").lower()
    has_browser_target = bool(
        re.search(r"https?://[^\s]+", query_lower)
        or re.search(r"\b[a-z0-9.-]+\.(?:de|com|org|net|io|ai)\b", query_lower)
        or "browser" in query_lower
        or "webseite" in query_lower
        or "website" in query_lower
    )
    has_ui_action = any(
        token in query_lower
        for token in (
            "gehe auf",
            "gehe zu",
            "navigiere zu",
            "tippe",
            "gib ein",
            "wähle",
            "waehle",
            "klicke",
            "drücke",
            "druecke",
            "formular",
            "suche",
            "login",
            "anmelden",
        )
    )
    return has_browser_target and has_ui_action


def _build_feedback_targets(query: str, agent: str) -> list[dict[str, str]]:
    query_lower = str(query or "").lower()
    items: list[dict[str, str]] = []

    if agent:
        items.append({"namespace": "dispatcher_agent", "key": agent})

    if agent in {"visual", "visual_nemotron"} or (agent == "meta" and _looks_like_browser_ui_flow(query)):
        items.append({"namespace": "visual_strategy", "key": "browser_flow"})
        if any(token in query_lower for token in ("klicke", "button", "suche", "suchen")):
            items.append({"namespace": "visual_strategy", "key": "click_targeting"})
        if any(token in query_lower for token in ("tippe", "gib ein", "suchfeld", "formular")):
            items.append({"namespace": "visual_strategy", "key": "ocr_text"})
        if any(token in query_lower for token in ("datum", "kalender", "anreise", "abreise", "15.", "17.")):
            items.append({"namespace": "visual_strategy", "key": "datepicker"})

    unique: dict[tuple[str, str], dict[str, str]] = {}
    for item in items:
        namespace = str(item.get("namespace") or "").strip()
        key = str(item.get("key") or "").strip()
        if namespace and key:
            unique[(namespace, key)] = {"namespace": namespace, "key": key}
    return list(unique.values())


def _build_reply_feedback_context(
    *,
    user_id: int,
    session_id: str,
    query: str,
    agent: str,
    response: str,
    source: str,
) -> dict:
    return {
        "source": source,
        "user_id": user_id,
        "session_id": session_id,
        "query": str(query or "")[:280],
        "dispatcher_agent": str(agent or ""),
        "response_preview": str(response or "")[:280],
    }


async def _reply_with_feedback(
    update: Update,
    *,
    text: Optional[str],
    action_id: str,
    context: dict,
    feedback_targets: list[dict[str, str]],
    parse_mode: Optional[str] = None,
) -> None:
    keyboard = build_feedback_markup(
        action_id=action_id,
        context=context,
        feedback_targets=feedback_targets,
    )
    body = str(text or "")
    if body and len(body) <= 4000:
        await update.message.reply_text(body, parse_mode=parse_mode, reply_markup=keyboard)
        return
    if body:
        await _send_long(update, body, parse_mode=parse_mode)
    await update.message.reply_text("War diese Antwort hilfreich?", reply_markup=keyboard)


async def _try_send_image(update: Update, result: str) -> bool:
    """
    Erkennt ob das Agent-Ergebnis ein Bild enthält und sendet es als Foto.
    Gibt True zurück wenn ein Bild gesendet wurde.

    Priorität:
      1. Lokale Datei (results/*.png) — zuverlässig, kein Ablauf
      2. Jede HTTPS-URL im Text — Download + als Bytes senden
         (Telegram kann OpenAI-CDN-URLs nicht direkt laden)
    """
    prompt_match = re.search(r'(?:Verwendeter Prompt|Prompt)[:\s]+(.{10,300})', result)
    caption = prompt_match.group(1).strip()[:1024] if prompt_match else "🎨 Timus hat dieses Bild generiert"

    # 1. Lokale Bilddatei suchen
    path_match = re.search(r'results/[^\n"\']+\.(?:png|jpg|jpeg|webp)', result, re.IGNORECASE)
    if path_match:
        image_path = _PROJECT_ROOT / path_match.group(0).strip()
        if image_path.exists():
            try:
                with open(image_path, "rb") as f:
                    await update.message.reply_photo(photo=f, caption=caption)
                log.info(f"Bild gesendet (lokal): {image_path.name}")
                return True
            except Exception as e:
                log.error(f"Fehler beim Senden der lokalen Bilddatei: {e}")

    # 2. Jede HTTPS-URL im Text — breites Regex, kein "URL:"-Präfix nötig
    url_match = re.search(r'https://[^\s\n"\'<>]{20,}', result, re.IGNORECASE)
    if url_match:
        image_url = url_match.group(0).rstrip('.,)')
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.get(image_url)
                resp.raise_for_status()
                image_bytes = resp.content
            await update.message.reply_photo(photo=image_bytes, caption=caption)
            log.info(f"Bild gesendet (URL-Download): {image_url[:60]}...")
            return True
        except Exception as e:
            log.error(f"Fehler beim Senden via URL-Download: {e}")

    return False


async def _try_send_document(update: Update, result: str) -> bool:
    """
    Erkennt ob das Agent-Ergebnis eine nicht-Bild-Datei enthält und sendet sie als Dokument.
    Gibt True zurück wenn eine Datei gesendet wurde.
    """
    # Dateierweiterungen die als Dokument gesendet werden (keine Bilder — die gehen über _try_send_image)
    DOC_EXTENSIONS = r'\.(?:pdf|txt|csv|json|md|py|js|html|css|docx|xlsx|zip|tar|gz|log|xml|yaml|yml)'
    path_match = re.search(
        r'(?:results|data|reports)/[^\n"\']+' + DOC_EXTENSIONS,
        result, re.IGNORECASE
    )
    if not path_match:
        return False

    file_path = _PROJECT_ROOT / path_match.group(0).strip()
    if not file_path.exists():
        return False

    try:
        with open(file_path, "rb") as f:
            await update.message.reply_document(
                document=f,
                filename=file_path.name,
                caption=f"📄 {file_path.name}",
            )
        log.info(f"Dokument gesendet: {file_path.name}")
        return True
    except Exception as e:
        log.error(f"Fehler beim Senden des Dokuments: {e}")
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
        f"  /approvals — offene Audit-Freigaben\n"
        f"  /approve <id> — Freigabe erteilen\n"
        f"  /reject <id> — Freigabe ablehnen\n"
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
        goal_metrics = queue.get_goal_alignment_metrics(include_conflicts=False)
        planning_metrics = queue.get_planning_metrics()
        replanning_metrics = queue.get_replanning_metrics()
        review_metrics = queue.get_commitment_review_metrics()
        healing_metrics = queue.get_self_healing_metrics()
        try:
            from utils.policy_gate import get_policy_decision_metrics

            policy_metrics = get_policy_decision_metrics(window_hours=24)
        except Exception:
            policy_metrics = {
                "decisions_total": 0,
                "blocked_total": 0,
                "observed_total": 0,
                "canary_deferred_total": 0,
            }
        try:
            from orchestration.autonomy_scorecard import build_autonomy_scorecard

            scorecard_window = max(1, int(os.getenv("AUTONOMY_SCORECARD_WINDOW_HOURS", "24")))
            autonomy_scorecard = build_autonomy_scorecard(queue=queue, window_hours=scorecard_window)
        except Exception:
            autonomy_scorecard = {
                "overall_score": 0.0,
                "overall_score_10": 0.0,
                "autonomy_level": "low",
                "ready_for_very_high_autonomy": False,
            }
        tasks = queue.get_all(limit=15)
        if not tasks:
            await update.message.reply_text("Keine Tasks vorhanden.")
            return
        icons = {"pending": "⏳", "in_progress": "🔄", "completed": "✅", "failed": "❌", "cancelled": "🚫"}
        prio_names = {0: "🔴", 1: "🟠", 2: "🟡", 3: "🟢"}
        lines = [f"📋 *Task-Queue* | {stats}\n"]
        lines.append(
            "🎯 Alignment offen: "
            f"{goal_metrics.get('open_aligned_tasks', 0)}/{goal_metrics.get('open_tasks', 0)} "
            f"({goal_metrics.get('open_alignment_rate', 0.0)}%)"
        )
        lines.append(
            "🗓️ Planung: "
            f"{planning_metrics.get('active_plans', 0)} aktive Plaene | "
            f"{planning_metrics.get('commitments_total', 0)} Commitments | "
            f"Deviation {planning_metrics.get('plan_deviation_score', 0.0)}"
        )
        lines.append(
            "🔁 Replanning: "
            f"{replanning_metrics.get('events_last_24h', 0)} Events/24h | "
            f"Overdue-Kandidaten {replanning_metrics.get('overdue_candidates', 0)} | "
            f"Top-Priority {replanning_metrics.get('top_priority_score', 0.0)}"
        )
        lines.append(
            "📋 Reviews: "
            f"Due {review_metrics.get('due_reviews', 0)} | "
            f"Escalated(7d) {review_metrics.get('escalated_last_7d', 0)} | "
            f"Gap(7d) {review_metrics.get('avg_gap_last_7d', 0.0)}"
        )
        lines.append(
            "🛠️ Healing: "
            f"Mode {healing_metrics.get('degrade_mode', 'normal')} | "
            f"Open {healing_metrics.get('open_incidents', 0)} | "
            f"EscalatedOpen {healing_metrics.get('open_escalated_incidents', 0)} | "
            f"BreakerOpen {healing_metrics.get('circuit_breakers_open', 0)} | "
            f"24h {healing_metrics.get('created_last_24h', 0)}/"
            f"{healing_metrics.get('recovered_last_24h', 0)}"
        )
        lines.append(
            "🛡️ Policy(24h): "
            f"Decisions {policy_metrics.get('decisions_total', 0)} | "
            f"Blocked {policy_metrics.get('blocked_total', 0)} | "
            f"Observed {policy_metrics.get('observed_total', 0)} | "
            f"CanaryDeferred {policy_metrics.get('canary_deferred_total', 0)}"
        )
        lines.append(
            "🧭 Autonomy-Score: "
            f"{autonomy_scorecard.get('overall_score', 0.0)}/100 "
            f"({autonomy_scorecard.get('overall_score_10', 0.0)}/10) | "
            f"Level {autonomy_scorecard.get('autonomy_level', 'low')} | "
            f"Ready9/10 {autonomy_scorecard.get('ready_for_very_high_autonomy', False)}"
        )
        control_state = autonomy_scorecard.get("control", {}) if isinstance(autonomy_scorecard, dict) else {}
        lines.append(
            "🧭 Control: "
            f"Action {control_state.get('scorecard_last_action', 'n/a')} | "
            f"Canary {control_state.get('canary_percent_override', 'n/a')} | "
            f"StrictOff {control_state.get('strict_force_off', False)} | "
            f"Gov {control_state.get('scorecard_governance_state', 'n/a')}"
        )
        trend_state = autonomy_scorecard.get("trends", {}) if isinstance(autonomy_scorecard, dict) else {}
        lines.append(
            "🧭 Trend: "
            f"Δ24h {trend_state.get('trend_delta', 0.0)} | "
            f"Dir {trend_state.get('trend_direction', 'stable')} | "
            f"Avg24h {trend_state.get('avg_score_window', 0.0)} | "
            f"Vol24h {trend_state.get('volatility_window', 0.0)}"
        )
        audit_rec = queue.get_policy_runtime_state("audit_report_last_recommendation")
        audit_exported = queue.get_policy_runtime_state("audit_report_last_exported_at")
        change_action = queue.get_policy_runtime_state("audit_change_last_action")
        change_status = queue.get_policy_runtime_state("audit_change_last_status")
        change_pending = queue.get_policy_runtime_state("audit_change_pending_approval_count")
        change_approval_status = queue.get_policy_runtime_state("audit_change_last_approval_status")
        hardening_state = queue.get_policy_runtime_state("hardening_last_state")
        hardening_action = queue.get_policy_runtime_state("hardening_last_action")
        hardening_reasons = queue.get_policy_runtime_state("hardening_last_reasons")
        lines.append(
            "🧾 Audit: "
            f"Rec {str((audit_rec or {}).get('state_value') or 'n/a')} | "
            f"At {str((audit_exported or {}).get('state_value') or 'n/a')[:19]}"
        )
        lines.append(
            "🧾 ChangeReq: "
            f"Action {str((change_action or {}).get('state_value') or 'n/a')} | "
            f"Status {str((change_status or {}).get('state_value') or 'n/a')} | "
            f"PendingApproval {str((change_pending or {}).get('state_value') or '0')} | "
            f"LastApproval {str((change_approval_status or {}).get('state_value') or 'n/a')}"
        )
        lines.append(
            "🧱 Hardening: "
            f"State {str((hardening_state or {}).get('state_value') or 'n/a')} | "
            f"Action {str((hardening_action or {}).get('state_value') or 'n/a')} | "
            f"Reasons {str((hardening_reasons or {}).get('state_value') or 'n/a')[:48]}"
        )
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
        queue = get_queue()
        stats = queue.stats()
        goal_metrics = queue.get_goal_alignment_metrics(include_conflicts=True)
        planning_metrics = queue.get_planning_metrics()
        replanning_metrics = queue.get_replanning_metrics()
        review_metrics = queue.get_commitment_review_metrics()
        healing_metrics = queue.get_self_healing_metrics()
        try:
            from utils.policy_gate import get_policy_decision_metrics

            policy_metrics = get_policy_decision_metrics(window_hours=24)
        except Exception:
            policy_metrics = {
                "decisions_total": 0,
                "blocked_total": 0,
                "observed_total": 0,
                "canary_deferred_total": 0,
            }
        try:
            from orchestration.autonomy_scorecard import build_autonomy_scorecard

            scorecard_window = max(1, int(os.getenv("AUTONOMY_SCORECARD_WINDOW_HOURS", "24")))
            autonomy_scorecard = build_autonomy_scorecard(queue=queue, window_hours=scorecard_window)
        except Exception:
            autonomy_scorecard = {
                "overall_score": 0.0,
                "overall_score_10": 0.0,
                "autonomy_level": "low",
                "ready_for_very_high_autonomy": False,
            }
        queue_line = (
            f"📋 Queue: ⏳{stats.get('pending',0)} "
            f"🔄{stats.get('in_progress',0)} "
            f"✅{stats.get('completed',0)} "
            f"❌{stats.get('failed',0)}"
        )
        goal_line = (
            "🎯 Goals: "
            f"Ausrichtung {goal_metrics.get('open_aligned_tasks', 0)}/{goal_metrics.get('open_tasks', 0)} "
            f"({goal_metrics.get('open_alignment_rate', 0.0)}%) | "
            f"Aktiv {goal_metrics.get('goal_counts', {}).get('active', 0)} | "
            f"Blocked {goal_metrics.get('goal_counts', {}).get('blocked', 0)} | "
            f"Konflikte {goal_metrics.get('conflict_count', 0)}"
        )
        planning_line = (
            "🗓️ Planning: "
            f"Plaene {planning_metrics.get('active_plans', 0)} | "
            f"Commitments {planning_metrics.get('commitments_total', 0)} | "
            f"Overdue {planning_metrics.get('overdue_commitments', 0)} | "
            f"Deviation {planning_metrics.get('plan_deviation_score', 0.0)}"
        )
        replanning_line = (
            "🔁 Replanning: "
            f"Events {replanning_metrics.get('events_total', 0)} | "
            f"24h {replanning_metrics.get('events_last_24h', 0)} | "
            f"Overdue-Kandidaten {replanning_metrics.get('overdue_candidates', 0)} | "
            f"Top-Priority {replanning_metrics.get('top_priority_score', 0.0)}"
        )
        review_line = (
            "📋 Reviews: "
            f"Due {review_metrics.get('due_reviews', 0)} | "
            f"Scheduled {review_metrics.get('scheduled_reviews', 0)} | "
            f"Escalated(7d) {review_metrics.get('escalated_last_7d', 0)} | "
            f"Gap(7d) {review_metrics.get('avg_gap_last_7d', 0.0)}"
        )
        healing_line = (
            "🛠️ Healing: "
            f"Mode {healing_metrics.get('degrade_mode', 'normal')} | "
            f"Open {healing_metrics.get('open_incidents', 0)} | "
            f"EscalatedOpen {healing_metrics.get('open_escalated_incidents', 0)} | "
            f"BreakerOpen {healing_metrics.get('circuit_breakers_open', 0)} | "
            f"Created24h {healing_metrics.get('created_last_24h', 0)} | "
            f"Recovered24h {healing_metrics.get('recovered_last_24h', 0)} | "
            f"RecoveryRate {healing_metrics.get('recovery_rate_24h', 0.0)}%"
        )
        policy_line = (
            "🛡️ Policy(24h): "
            f"Decisions {policy_metrics.get('decisions_total', 0)} | "
            f"Blocked {policy_metrics.get('blocked_total', 0)} | "
            f"Observed {policy_metrics.get('observed_total', 0)} | "
            f"CanaryDeferred {policy_metrics.get('canary_deferred_total', 0)}"
        )
        autonomy_line = (
            "🧭 Autonomy-Score: "
            f"{autonomy_scorecard.get('overall_score', 0.0)}/100 "
            f"({autonomy_scorecard.get('overall_score_10', 0.0)}/10) | "
            f"Level {autonomy_scorecard.get('autonomy_level', 'low')} | "
            f"Ready9/10 {autonomy_scorecard.get('ready_for_very_high_autonomy', False)}"
        )
        control_state = autonomy_scorecard.get("control", {}) if isinstance(autonomy_scorecard, dict) else {}
        control_line = (
            "🧭 Control: "
            f"Action {control_state.get('scorecard_last_action', 'n/a')} | "
            f"Canary {control_state.get('canary_percent_override', 'n/a')} | "
            f"StrictOff {control_state.get('strict_force_off', False)} | "
            f"Gov {control_state.get('scorecard_governance_state', 'n/a')}"
        )
        trend_state = autonomy_scorecard.get("trends", {}) if isinstance(autonomy_scorecard, dict) else {}
        trend_line = (
            "🧭 Trend: "
            f"Δ24h {trend_state.get('trend_delta', 0.0)} | "
            f"Dir {trend_state.get('trend_direction', 'stable')} | "
            f"Avg24h {trend_state.get('avg_score_window', 0.0)} | "
            f"Vol24h {trend_state.get('volatility_window', 0.0)}"
        )
        audit_rec = queue.get_policy_runtime_state("audit_report_last_recommendation")
        audit_exported = queue.get_policy_runtime_state("audit_report_last_exported_at")
        change_action = queue.get_policy_runtime_state("audit_change_last_action")
        change_status = queue.get_policy_runtime_state("audit_change_last_status")
        change_pending = queue.get_policy_runtime_state("audit_change_pending_approval_count")
        change_approval_status = queue.get_policy_runtime_state("audit_change_last_approval_status")
        hardening_state = queue.get_policy_runtime_state("hardening_last_state")
        hardening_action = queue.get_policy_runtime_state("hardening_last_action")
        hardening_reasons = queue.get_policy_runtime_state("hardening_last_reasons")
        audit_line = (
            "🧾 Audit: "
            f"Rec {str((audit_rec or {}).get('state_value') or 'n/a')} | "
            f"At {str((audit_exported or {}).get('state_value') or 'n/a')[:19]}"
        )
        change_line = (
            "🧾 ChangeReq: "
            f"Action {str((change_action or {}).get('state_value') or 'n/a')} | "
            f"Status {str((change_status or {}).get('state_value') or 'n/a')} | "
            f"PendingApproval {str((change_pending or {}).get('state_value') or '0')} | "
            f"LastApproval {str((change_approval_status or {}).get('state_value') or 'n/a')}"
        )
        hardening_line = (
            "🧱 Hardening: "
            f"State {str((hardening_state or {}).get('state_value') or 'n/a')} | "
            f"Action {str((hardening_action or {}).get('state_value') or 'n/a')} | "
            f"Reasons {str((hardening_reasons or {}).get('state_value') or 'n/a')[:48]}"
        )

        # System
        sys_stats = await asyncio.to_thread(get_system_stats)
        sys_line = (
            f"💻 CPU {sys_stats['cpu_percent']}% | "
            f"RAM {sys_stats['ram_percent']}% "
            f"({sys_stats['ram_used_gb']}/{sys_stats['ram_total_gb']} GB) | "
            f"Disk {sys_stats['disk_percent']}%"
        )

        snapshot = await collect_status_snapshot()
        summary_lines = [
            sched_line,
            queue_line,
            goal_line,
            planning_line,
            replanning_line,
            review_line,
            healing_line,
            policy_line,
            autonomy_line,
            control_line,
            trend_line,
            audit_line,
            change_line,
            hardening_line,
            sys_line,
        ]
        msg = format_status_message(snapshot, summary_lines)
        await _send_long(update, msg)
    except Exception as e:
        await update.message.reply_text(f"Fehler: {e}")


async def cmd_approvals(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_allowed(update.effective_user.id):
        return
    try:
        from orchestration.autonomy_change_control import list_pending_approval_change_requests
        from orchestration.task_queue import get_queue

        limit = 10
        if context.args:
            try:
                limit = max(1, min(50, int(str(context.args[0]))))
            except Exception:
                limit = 10

        queue = get_queue()
        listed = list_pending_approval_change_requests(queue=queue, limit=limit)
        items = listed.get("items", []) if isinstance(listed, dict) else []
        if not items:
            await update.message.reply_text("Keine offenen Freigaben.")
            return

        lines = [f"🧾 *Pending Approvals* ({len(items)})"]
        for item in items:
            rid = str(item.get("id") or "")
            rec = str(item.get("recommendation") or "hold")
            pending_min = item.get("pending_minutes")
            min_txt = f"{pending_min:.1f}m" if isinstance(pending_min, (int, float)) else "n/a"
            reason = str(item.get("reason") or "")[:48]
            lines.append(f"`{rid[:12]}` | {rec} | {min_txt} | {reason}")
        lines.append("")
        lines.append("Nutze `/approve <id>` oder `/reject <id>`.")
        await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.MARKDOWN)
    except Exception as e:
        await update.message.reply_text(f"Fehler: {e}")


async def cmd_approve(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_allowed(update.effective_user.id):
        return
    if not context.args:
        await update.message.reply_text("Verwendung: `/approve <request_id_prefix> [note]`", parse_mode=ParseMode.MARKDOWN)
        return
    try:
        from orchestration.autonomy_change_control import (
            evaluate_and_apply_pending_approved_change_requests,
            set_change_request_approval,
        )
        from orchestration.task_queue import get_queue

        request_id = str(context.args[0]).strip()
        note = " ".join(context.args[1:]).strip() or None
        decision = set_change_request_approval(
            request_id=request_id,
            approved=True,
            approver=f"telegram:{update.effective_user.id}",
            note=note,
        )
        if decision.get("status") != "ok":
            await update.message.reply_text(f"❌ Freigabe fehlgeschlagen: `{decision}`", parse_mode=ParseMode.MARKDOWN)
            return

        queue = get_queue()
        applied = evaluate_and_apply_pending_approved_change_requests(queue=queue, limit=5)
        processed = int(applied.get("processed", 0) or 0)
        await update.message.reply_text(
            "✅ Freigegeben\n"
            f"Request: `{str(decision.get('request_id') or '')[:12]}`\n"
            f"AppliedNow: `{processed}`",
            parse_mode=ParseMode.MARKDOWN,
        )
    except Exception as e:
        await update.message.reply_text(f"Fehler: {e}")


async def cmd_reject(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_allowed(update.effective_user.id):
        return
    if not context.args:
        await update.message.reply_text("Verwendung: `/reject <request_id_prefix> [note]`", parse_mode=ParseMode.MARKDOWN)
        return
    try:
        from orchestration.autonomy_change_control import set_change_request_approval

        request_id = str(context.args[0]).strip()
        note = " ".join(context.args[1:]).strip() or None
        decision = set_change_request_approval(
            request_id=request_id,
            approved=False,
            approver=f"telegram:{update.effective_user.id}",
            note=note,
        )
        if decision.get("status") != "ok":
            await update.message.reply_text(f"❌ Ablehnung fehlgeschlagen: `{decision}`", parse_mode=ParseMode.MARKDOWN)
            return
        await update.message.reply_text(
            "🛑 Abgelehnt\n"
            f"Request: `{str(decision.get('request_id') or '')[:12]}`",
            parse_mode=ParseMode.MARKDOWN,
        )
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
        agent = await get_agent_decision(text, session_id=session_id)
        log.info(f"  Agent gewählt: {agent.upper()}")

        # Multi-Step-Tasks (META) brauchen mehr Zeit — Status-Update senden
        if agent == "meta":
            try:
                await thinking_msg.edit_text(
                    "🧠 Timus plant & koordiniert… (mehrstufiger Auftrag, bitte warten)"
                )
            except Exception:
                pass

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
        feedback_targets = _build_feedback_targets(text, agent)
        feedback_context = _build_reply_feedback_context(
            user_id=user.id,
            session_id=session_id,
            query=text,
            agent=agent,
            response=response,
            source="telegram_reply",
        )
        action_id = f"tgmsg:{session_id}:{uuid.uuid4().hex[:8]}"

        # Bild → als Foto senden
        image_sent = await _try_send_image(update, response)
        # Dokument → als Datei senden
        doc_sent = await _try_send_document(update, response)
        # Kein Bild/Datei → als Text senden
        if not image_sent and not doc_sent:
            await _reply_with_feedback(
                update,
                text=response,
                action_id=action_id,
                context=feedback_context,
                feedback_targets=feedback_targets,
            )
        else:
            await _reply_with_feedback(
                update,
                text="War diese Antwort hilfreich?",
                action_id=action_id,
                context=feedback_context,
                feedback_targets=feedback_targets,
            )

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
        agent = await get_agent_decision(user_text, session_id=session_id)
        log.info(f"  Voice-Agent: {agent.upper()}")

        # Meta braucht länger — Status-Update
        if agent == "meta":
            try:
                await thinking_msg.edit_text(
                    f"🎤 _{user_text}_\n\n🧠 Timus plant & koordiniert… (bitte warten)",
                    parse_mode=ParseMode.MARKDOWN,
                )
            except Exception:
                pass

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
        feedback_targets = _build_feedback_targets(user_text, agent)
        feedback_context = _build_reply_feedback_context(
            user_id=user.id,
            session_id=session_id,
            query=user_text,
            agent=agent,
            response=response,
            source="telegram_voice_reply",
        )
        action_id = f"tgvoice:{session_id}:{uuid.uuid4().hex[:8]}"

        # 4. Bild-Check / Dokument-Check
        image_sent = await _try_send_image(update, response)
        doc_sent   = await _try_send_document(update, response)

        # 5. TTS → Sprachnachricht zurück (nur wenn kein Dokument/Bild bereits gesendet)
        await update.message.chat.send_action(ChatAction.RECORD_VOICE)
        ogg_audio = await _synthesize_voice(response)

        if ogg_audio:
            # Kurze Caption: erste 200 Zeichen der Antwort
            caption = response[:200] + ("…" if len(response) > 200 else "")
            await update.message.reply_voice(
                voice=io.BytesIO(ogg_audio),
                caption=caption if not image_sent and not doc_sent else None,
            )
            await _reply_with_feedback(
                update,
                text="War diese Sprachantwort hilfreich?",
                action_id=action_id,
                context=feedback_context,
                feedback_targets=feedback_targets,
            )
        else:
            # Kein TTS konfiguriert → Textantwort (nur wenn kein Bild/Dok gesendet)
            if not image_sent and not doc_sent:
                await _reply_with_feedback(
                    update,
                    text=response,
                    action_id=action_id,
                    context=feedback_context,
                    feedback_targets=feedback_targets,
                )
            else:
                await _reply_with_feedback(
                    update,
                    text="War diese Antwort hilfreich?",
                    action_id=action_id,
                    context=feedback_context,
                    feedback_targets=feedback_targets,
                )

    except Exception as e:
        log.error(f"Voice-Handler Fehler: {e}", exc_info=True)
        try:
            await thinking_msg.delete()
        except Exception:
            pass
        await update.message.reply_text(f"❌ Fehler bei Sprachverarbeitung: {e}")


async def handle_document_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Empfängt Dateien (Dokumente, Bilder als Datei) von Telegram.
    Speichert sie in data/uploads/ und gibt Timus Bescheid.
    """
    user = update.effective_user
    if not _is_allowed(user.id):
        await update.message.reply_text("⛔ Kein Zugriff.")
        return

    # Dokument oder Foto-als-Datei
    doc = update.message.document
    if not doc:
        return

    await update.message.chat.send_action(ChatAction.TYPING)

    try:
        file = await context.bot.get_file(doc.file_id)
        file_bytes = bytes(await file.download_as_bytearray())

        safe_name = re.sub(r"[^\w.\-]", "_", doc.file_name or "upload.bin")[:120]
        upload_dir = _PROJECT_ROOT / "data" / "uploads"
        upload_dir.mkdir(parents=True, exist_ok=True)
        dest = upload_dir / f"tg_{uuid.uuid4().hex[:8]}_{safe_name}"
        dest.write_bytes(file_bytes)

        rel_path = str(dest.relative_to(_PROJECT_ROOT))
        size_kb = len(file_bytes) / 1024

        await update.message.reply_text(
            f"📎 Datei empfangen: *{doc.file_name}* ({size_kb:.1f} KB)\n"
            f"Gespeichert: `{rel_path}`\n\n"
            f"Was soll ich damit machen?",
            parse_mode=ParseMode.MARKDOWN,
        )
        log.info(f"Dokument empfangen: {doc.file_name} → {rel_path}")

    except Exception as e:
        log.error(f"Fehler beim Empfangen der Datei: {e}", exc_info=True)
        await update.message.reply_text(f"❌ Fehler beim Empfangen der Datei: {e}")


async def handle_callback_query(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    M16: Verarbeitet InlineKeyboard-Callbacks (👍/👎/🤷).
    Speichert Signal in FeedbackEngine, bestätigt den Callback via Telegram ACK.
    """
    query = update.callback_query
    if not query:
        return

    user = update.effective_user
    if not _is_allowed(user.id):
        await query.answer("⛔ Kein Zugriff")
        return

    try:
        data = json.loads(query.data)
    except (json.JSONDecodeError, TypeError):
        await query.answer("❌ Ungültige Callback-Daten")
        return

    # Dispatch nach type-Feld (M14/M13 nutzen type-Feld; M16-Feedback hat keins)
    cb_type = data.get("type", "feedback")

    # M14: E-Mail-Approval
    if cb_type == "email_approve":
        action_id = data.get("aid", "")
        try:
            from orchestration.email_autonomy_engine import get_email_autonomy_engine
            get_email_autonomy_engine().execute_if_approved(action_id, approved=True)
            await query.answer("✅ E-Mail wird gesendet")
            log.info("M14: E-Mail-Approval: aid=%s user=%d", action_id, user.id)
        except Exception as e:
            log.warning("M14: E-Mail-Approval fehlgeschlagen: %s", e)
            await query.answer("⚠️ Fehler bei E-Mail-Approval")
        return

    if cb_type == "email_reject":
        action_id = data.get("aid", "")
        try:
            from orchestration.email_autonomy_engine import get_email_autonomy_engine
            get_email_autonomy_engine().execute_if_approved(action_id, approved=False)
            await query.answer("❌ E-Mail abgebrochen")
            log.info("M14: E-Mail abgelehnt: aid=%s user=%d", action_id, user.id)
        except Exception as e:
            log.warning("M14: E-Mail-Ablehnung fehlgeschlagen: %s", e)
            await query.answer("⚠️ Fehler bei E-Mail-Ablehnung")
        return

    # M13: Tool-Approval
    if cb_type == "tool_approve":
        action_id = data.get("aid", "")
        try:
            from orchestration.tool_generator_engine import get_tool_generator_engine
            success = get_tool_generator_engine().activate(action_id)
            if success:
                await query.answer("✅ Tool aktiviert!")
            else:
                await query.answer("⚠️ Aktivierung fehlgeschlagen")
            log.info("M13: Tool-Approval: aid=%s user=%d success=%s", action_id, user.id, success)
        except Exception as e:
            log.warning("M13: Tool-Approval fehlgeschlagen: %s", e)
            await query.answer("⚠️ Fehler bei Tool-Aktivierung")
        return

    if cb_type == "tool_reject":
        action_id = data.get("aid", "")
        try:
            from orchestration.tool_generator_engine import get_tool_generator_engine
            get_tool_generator_engine().reject(action_id)
            await query.answer("❌ Tool abgelehnt")
            log.info("M13: Tool abgelehnt: aid=%s user=%d", action_id, user.id)
        except Exception as e:
            log.warning("M13: Tool-Ablehnung fehlgeschlagen: %s", e)
            await query.answer("⚠️ Fehler bei Tool-Ablehnung")
        return

    # M18: Code-Edit-Approval
    if cb_type == "code_edit_approve":
        pending_id = data.get("pid", "")
        try:
            from orchestration.self_modifier_engine import get_self_modifier_engine

            result = await get_self_modifier_engine().approve_pending(
                pending_id,
                approver=f"telegram:{user.id}",
            )
            if result.status == "success":
                await query.answer("✅ Code-Änderung angewendet")
            elif result.status == "rolled_back":
                await query.answer("⚠️ Änderung angewendet, Tests fehlgeschlagen, Rollback durchgeführt")
            else:
                await query.answer("⚠️ Code-Änderung konnte nicht angewendet werden")
            log.info("M18: Code-Edit-Approval: pid=%s user=%d status=%s", pending_id, user.id, result.status)
        except Exception as e:
            log.warning("M18: Code-Edit-Approval fehlgeschlagen: %s", e)
            await query.answer("⚠️ Fehler bei Code-Edit-Approval")
        return

    if cb_type == "code_edit_reject":
        pending_id = data.get("pid", "")
        try:
            from orchestration.self_modifier_engine import get_self_modifier_engine

            result = await get_self_modifier_engine().reject_pending(
                pending_id,
                approver=f"telegram:{user.id}",
            )
            if result.status == "blocked":
                await query.answer("❌ Code-Änderung abgelehnt")
            else:
                await query.answer("⚠️ Änderung konnte nicht abgelehnt werden")
            log.info("M18: Code-Edit-Reject: pid=%s user=%d status=%s", pending_id, user.id, result.status)
        except Exception as e:
            log.warning("M18: Code-Edit-Ablehnung fehlgeschlagen: %s", e)
            await query.answer("⚠️ Fehler bei Code-Edit-Ablehnung")
        return

    # M16-Feedback-Handler (Fallback für type="feedback" oder kein type-Feld)
    signal = decode_feedback_signal(data.get("s") or data.get("fb"))
    action_id = data.get("aid", "unknown")
    hooks_raw = data.get("hooks", "[]")
    feedback_context = {}
    feedback_targets = []

    request_token = str(data.get("t") or "").strip()
    if request_token:
        try:
            from orchestration.feedback_engine import get_feedback_engine

            payload = get_feedback_engine().resolve_feedback_request(request_token)
            if payload:
                action_id = payload.action_id
                hooks_raw = payload.hook_names
                feedback_context = dict(payload.context or {})
                feedback_targets = list(payload.feedback_targets or [])
        except Exception as e:
            log.warning("M16 Feedback: Token-Aufloesung fehlgeschlagen: %s", e)

    if signal not in {"positive", "negative", "neutral"}:
        await query.answer("❌ Unbekanntes Signal")
        return

    try:
        hook_names = json.loads(hooks_raw) if isinstance(hooks_raw, str) else (hooks_raw or [])
    except (json.JSONDecodeError, TypeError):
        hook_names = []

    # Signal in FeedbackEngine speichern
    try:
        from orchestration.feedback_engine import get_feedback_engine
        get_feedback_engine().record_signal(
            action_id=action_id,
            signal=signal,
            hook_names=hook_names,
            context={
                **feedback_context,
                "user_id": user.id,
                "username": getattr(user, "username", ""),
            },
            feedback_targets=feedback_targets,
        )
        signal_emoji = {"positive": "👍", "negative": "👎", "neutral": "🤷"}.get(signal, "?")
        await query.answer(f"{signal_emoji} Feedback gespeichert!")
        log.info("M16 Feedback: user=%d action=%s signal=%s hooks=%s", user.id, action_id, signal, hook_names)
    except Exception as e:
        log.warning("M16 Feedback: Speichern fehlgeschlagen: %s", e)
        await query.answer("⚠️ Feedback konnte nicht gespeichert werden")


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
            self._app.add_handler(CommandHandler("approvals", cmd_approvals))
            self._app.add_handler(CommandHandler("approve", cmd_approve))
            self._app.add_handler(CommandHandler("reject", cmd_reject))
            self._app.add_handler(
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message)
            )
            self._app.add_handler(
                MessageHandler(filters.VOICE, handle_voice_message)
            )
            self._app.add_handler(
                MessageHandler(filters.Document.ALL, handle_document_message)
            )
            # M16: Feedback-Buttons
            self._app.add_handler(CallbackQueryHandler(handle_callback_query))

            await self._app.initialize()
            await self._app.start()
            await self._app.updater.start_polling(
                drop_pending_updates=True,
                allowed_updates=["message", "callback_query"],
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
