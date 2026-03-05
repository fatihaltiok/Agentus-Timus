"""
orchestration/ambient_context_engine.py — M15: Ambient Context Engine

Transformiert Timus vom Pull- zum Push-System: beobachtet Signalquellen,
bewertet Relevanz und erstellt Tasks eigenständig.

Signalquellen:
  - EmailWatcher       — neue ungelesene Mails
  - FileWatcher        — neue Dateien in ~/Downloads
  - GoalStalenessCheck — stagnierende Ziele (direkt via SQLite)
  - SystemWatcher      — CPU/RAM/Disk-Überlast

Feature-Flag: AUTONOMY_AMBIENT_CONTEXT_ENABLED=true
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import sqlite3
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional

log = logging.getLogger("AmbientContextEngine")

# ── Konfiguration aus Umgebungsvariablen ──────────────────────────────────────

SIGNAL_THRESHOLD = float(os.getenv("AMBIENT_SIGNAL_THRESHOLD", "0.6"))
CONFIRM_THRESHOLD = float(os.getenv("AMBIENT_CONFIRM_THRESHOLD", "0.85"))
SYSTEM_ALERT_THRESHOLD = float(os.getenv("AMBIENT_SYSTEM_ALERT_THRESHOLD", "0.70"))
GOAL_STALE_HOURS = float(os.getenv("AMBIENT_GOAL_STALE_HOURS", "48"))
HEARTBEAT_INTERVAL_MINUTES = int(os.getenv("HEARTBEAT_INTERVAL_MINUTES", "5"))

TIMUS_EMAIL = os.getenv("TIMUS_EMAIL", "timus.assistent@outlook.com").lower()

_URGENCY_KEYWORDS = [
    "dringend", "urgent", "asap", "deadline",
    "wichtig", "frist", "sofort",
]

_IGNORE_EXTENSIONS = {".crdownload", ".tmp", ".part", ".ds_store"}

_FILE_TYPE_MAP: dict[str, tuple[float, str]] = {
    ".pdf":  (0.80, "document"),
    ".csv":  (0.80, "data"),
    ".xlsx": (0.80, "data"),
    ".docx": (0.75, "document"),
    ".pptx": (0.75, "document"),
    ".txt":  (0.70, "executor"),
    ".json": (0.70, "data"),
    ".png":  (0.60, "executor"),
    ".jpg":  (0.60, "executor"),
    ".jpeg": (0.60, "executor"),
}

POLICY: dict[str, str] = {
    "email":      "auto",
    "file":       "auto",
    "goal_stale": "auto",
    "system":     "confirm",
}

MEMORY_DB_PATH = Path(__file__).resolve().parents[1] / "data" / "timus_memory.db"


# ──────────────────────────────────────────────────────────────────────────────
# Dataclass
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class AmbientSignal:
    source: str            # "email" | "file" | "goal_stale" | "system"
    score: float           # 0.0–1.0 (geclampt)
    description: str       # Task-Text für den Agenten
    target_agent: str      # Ziel-Agent
    dedup_key: str         # eindeutiger Key für Blackboard-Dedup
    cooldown_minutes: int  # Dedup-TTL
    context: dict = field(default_factory=dict)  # Signal-Metadaten (Audit)
    policy_level: str = "auto"


# ──────────────────────────────────────────────────────────────────────────────
# Singleton
# ──────────────────────────────────────────────────────────────────────────────

_ambient_engine_instance: Optional["AmbientContextEngine"] = None


def get_ambient_engine() -> "AmbientContextEngine":
    """Gibt die globale AmbientContextEngine-Instanz zurück (Singleton)."""
    global _ambient_engine_instance
    if _ambient_engine_instance is None:
        _ambient_engine_instance = AmbientContextEngine()
    return _ambient_engine_instance


# ──────────────────────────────────────────────────────────────────────────────
# AmbientContextEngine
# ──────────────────────────────────────────────────────────────────────────────

class AmbientContextEngine:
    """
    Beobachtet Signalquellen und erstellt Tasks eigenständig.
    Läuft alle 5 Min im Heartbeat (via autonomous_runner.py).
    """

    def __init__(self) -> None:
        self._tasks_queued_total: int = 0

    # ------------------------------------------------------------------
    # Dedup via Blackboard
    # ------------------------------------------------------------------

    def _is_duplicate(self, signal: AmbientSignal) -> bool:
        try:
            from memory.agent_blackboard import get_blackboard
            existing = get_blackboard().read(topic="ambient_dedup", key=signal.dedup_key)
            return len(existing) > 0
        except Exception as e:
            log.debug("Dedup-Check fehlgeschlagen: %s", e)
            return False

    def _mark_seen(self, signal: AmbientSignal) -> None:
        try:
            from memory.agent_blackboard import get_blackboard
            get_blackboard().write(
                agent="ambient_context",
                topic="ambient_dedup",
                key=signal.dedup_key,
                value={"score": round(signal.score, 3), "at": datetime.now().isoformat()},
                ttl_minutes=signal.cooldown_minutes,
            )
        except Exception as e:
            log.debug("Dedup-Markierung fehlgeschlagen: %s", e)

    def _write_audit(self, signal: AmbientSignal, action: str) -> None:
        try:
            from memory.agent_blackboard import get_blackboard
            audit_key = f"{signal.source}:{signal.dedup_key}:{datetime.now().isoformat()}"
            get_blackboard().write(
                agent="ambient_context",
                topic="ambient_audit",
                key=audit_key,
                value={
                    "source": signal.source,
                    "score": round(signal.score, 3),
                    "action": action,
                    "description": signal.description[:120],
                    "context": signal.context,
                },
                ttl_minutes=10080,  # 1 Woche
            )
        except Exception as e:
            log.debug("Audit-Log fehlgeschlagen: %s", e)

    # ------------------------------------------------------------------
    # Signal verarbeiten
    # ------------------------------------------------------------------

    async def _process_signal(self, signal: AmbientSignal) -> bool:
        """
        Prüft Threshold + Dedup, schickt ggf. Telegram-Benachrichtigung,
        legt Task in Queue an.

        Returns True wenn Task erstellt wurde.
        """
        if signal.score < SIGNAL_THRESHOLD:
            log.debug(
                "Signal ignoriert (score=%.2f < threshold=%.2f): %s",
                signal.score, SIGNAL_THRESHOLD, signal.dedup_key,
            )
            return False

        if self._is_duplicate(signal):
            log.debug("Signal dupliziert — ignoriert: %s", signal.dedup_key)
            return False

        # Telegram-Push wenn confirm-Policy ODER hoher Score
        should_notify = (
            signal.policy_level == "confirm"
            or signal.score >= CONFIRM_THRESHOLD
        )
        if should_notify:
            msg = (
                f"🤖 *Timus Ambient* — {signal.source.upper()}\n"
                f"Score: {signal.score:.2f} | Agent: `{signal.target_agent}`\n"
                f"{signal.description[:200]}"
            )
            try:
                from utils.telegram_notify import send_with_feedback
                await send_with_feedback(
                    msg,
                    action_id=signal.signal_id,
                    hook_names=["ambient_trigger"],
                )
            except Exception as e:
                log.debug("Telegram-Benachrichtigung fehlgeschlagen: %s", e)

        # Task in Queue legen
        try:
            from orchestration.task_queue import Priority, get_queue
            priority = Priority.HIGH if signal.score >= 0.8 else Priority.NORMAL
            get_queue().add(
                description=signal.description,
                priority=int(priority),
                task_type="ambient",
                target_agent=signal.target_agent,
                metadata=str(signal.context),
            )
            self._tasks_queued_total += 1
            log.info(
                "🌐 Ambient Task: source=%s score=%.2f agent=%s | %s",
                signal.source, signal.score, signal.target_agent,
                signal.description[:80],
            )
        except Exception as e:
            log.warning("Task-Erstellung fehlgeschlagen: %s", e)
            self._write_audit(signal, f"queue_error:{e}")
            return False

        self._mark_seen(signal)
        self._write_audit(signal, "queued")
        return True

    # ------------------------------------------------------------------
    # 1. EmailWatcher
    # ------------------------------------------------------------------

    async def _check_emails(self) -> List[AmbientSignal]:
        signals: List[AmbientSignal] = []
        try:
            from tools.email_tool.tool import get_email_status, read_emails

            status = await asyncio.to_thread(get_email_status)
            if not status.get("authenticated", False):
                log.debug("EmailWatcher: nicht authentifiziert — übersprungen")
                return signals

            result = await asyncio.to_thread(read_emails, "inbox", 5, True, "")
            emails = result.get("emails", []) if isinstance(result, dict) else []

            for mail in emails:
                sender = mail.get("from", {})
                if isinstance(sender, dict):
                    sender_addr = (
                        sender.get("emailAddress", {}).get("address", "").lower()
                    )
                else:
                    sender_addr = str(sender).lower()

                # Timus-eigene Mails ignorieren
                if sender_addr == TIMUS_EMAIL:
                    continue

                subject = mail.get("subject", "")
                body_preview = mail.get("bodyPreview", "")
                mail_id = mail.get("id", "")

                # Score-Berechnung
                score = 0.6
                combined = (subject + " " + body_preview).lower()
                if any(kw in combined for kw in _URGENCY_KEYWORDS):
                    score += 0.2
                if sender_addr != TIMUS_EMAIL:
                    score += 0.2
                score = max(0.0, min(1.0, score))

                if mail_id:
                    dedup_key = f"email:{mail_id}"
                else:
                    dedup_key = f"email:{hashlib.sha1(subject.encode()).hexdigest()[:8]}"

                signals.append(AmbientSignal(
                    source="email",
                    score=score,
                    description=(
                        f"Neue E-Mail von {sender_addr}: '{subject}'\n"
                        f"Vorschau: {body_preview[:120]}\n"
                        f"Bitte zusammenfassen und Antwort-Entwurf erstellen."
                    ),
                    target_agent="communication",
                    dedup_key=dedup_key,
                    cooldown_minutes=240,
                    context={"sender": sender_addr, "subject": subject, "id": mail_id},
                    policy_level=POLICY["email"],
                ))
        except Exception as e:
            log.debug("EmailWatcher fehlgeschlagen: %s", e)
        return signals

    # ------------------------------------------------------------------
    # 2. FileWatcher
    # ------------------------------------------------------------------

    async def _check_files(self) -> List[AmbientSignal]:
        signals: List[AmbientSignal] = []
        try:
            downloads_path = Path.home() / "Downloads"
            if not downloads_path.exists():
                return signals

            window_sec = HEARTBEAT_INTERVAL_MINUTES * 2 * 60  # default 600s
            cutoff = time.time() - window_sec

            def _scan() -> List[Path]:
                found: List[Path] = []
                for p in downloads_path.glob("*"):
                    if not p.is_file():
                        continue
                    if p.suffix.lower() in _IGNORE_EXTENSIONS:
                        continue
                    try:
                        if os.path.getmtime(p) > cutoff:
                            found.append(p)
                    except OSError:
                        continue
                return found[:20]

            new_files = await asyncio.to_thread(_scan)

            for fp in new_files:
                ext = fp.suffix.lower()
                if ext not in _FILE_TYPE_MAP:
                    continue  # unbekannte Dateitypen unter Threshold

                score, agent = _FILE_TYPE_MAP[ext]
                score = max(0.0, min(1.0, score))
                sha1_short = hashlib.sha1(str(fp).encode()).hexdigest()[:8]
                dedup_key = f"file:{sha1_short}"

                signals.append(AmbientSignal(
                    source="file",
                    score=score,
                    description=(
                        f"Neue Datei in Downloads: '{fp.name}'\n"
                        f"Bitte analysieren, klassifizieren und ggf. ablegen."
                    ),
                    target_agent=agent,
                    dedup_key=dedup_key,
                    cooldown_minutes=1440,
                    context={"path": str(fp), "ext": ext, "size": fp.stat().st_size},
                    policy_level=POLICY["file"],
                ))
        except Exception as e:
            log.debug("FileWatcher fehlgeschlagen: %s", e)
        return signals

    # ------------------------------------------------------------------
    # 3. GoalStalenessCheck
    # ------------------------------------------------------------------

    async def _check_goal_staleness(self) -> List[AmbientSignal]:
        signals: List[AmbientSignal] = []
        try:
            stale_cutoff = datetime.now() - timedelta(hours=GOAL_STALE_HOURS)

            def _query() -> List[dict]:
                if not MEMORY_DB_PATH.exists():
                    return []
                rows: List[dict] = []
                try:
                    with sqlite3.connect(str(MEMORY_DB_PATH)) as conn:
                        conn.row_factory = sqlite3.Row
                        cur = conn.execute(
                            """SELECT g.id, g.title, gs.progress, gs.updated_at
                               FROM goals g JOIN goal_state gs ON g.id = gs.goal_id
                               WHERE g.status = 'active' AND gs.progress < 1.0"""
                        )
                        rows = [dict(r) for r in cur.fetchall()]
                except Exception as sql_err:
                    log.debug("GoalStaleness SQL-Fehler: %s", sql_err)
                return rows

            rows = await asyncio.to_thread(_query)

            for row in rows:
                updated_raw = row.get("updated_at", "")
                try:
                    updated_at = datetime.fromisoformat(updated_raw)
                except (ValueError, TypeError):
                    continue

                if updated_at >= stale_cutoff:
                    continue  # noch frisch

                staleness_days = (datetime.now() - updated_at).total_seconds() / 86400
                score = max(0.0, min(1.0, staleness_days / 7.0))

                if score < 0.6:
                    continue  # < 4.2 Tage → ignorieren

                goal_id = row.get("id", "")
                title = row.get("title", "Unbekanntes Ziel")
                progress = row.get("progress", 0.0)

                signals.append(AmbientSignal(
                    source="goal_stale",
                    score=score,
                    description=(
                        f"Ziel stagniert seit {staleness_days:.1f} Tagen: '{title}'\n"
                        f"Aktueller Fortschritt: {progress:.0%}\n"
                        f"Bitte nächste Schritte planen oder Hindernisse identifizieren."
                    ),
                    target_agent="meta",
                    dedup_key=f"goal:{goal_id}",
                    cooldown_minutes=1440,
                    context={
                        "goal_id": str(goal_id),
                        "title": title,
                        "progress": progress,
                        "staleness_days": round(staleness_days, 1),
                    },
                    policy_level=POLICY["goal_stale"],
                ))
        except Exception as e:
            log.debug("GoalStalenessCheck fehlgeschlagen: %s", e)
        return signals

    # ------------------------------------------------------------------
    # 4. SystemWatcher
    # ------------------------------------------------------------------

    async def _check_system(self) -> List[AmbientSignal]:
        signals: List[AmbientSignal] = []
        try:
            from tools.system_monitor_tool.tool import _get_system_usage_sync

            usage = await asyncio.to_thread(_get_system_usage_sync)
            cpu_pct = float(usage.get("cpu_percent", 0.0))
            ram_pct = float(usage.get("memory", {}).get("percent", 0.0))
            disk_pct = float(usage.get("disk", {}).get("percent", 0.0))

            score = max(0.0, min(1.0, max(cpu_pct, ram_pct, disk_pct) / 100.0))

            if score >= SYSTEM_ALERT_THRESHOLD:
                signals.append(AmbientSignal(
                    source="system",
                    score=score,
                    description=(
                        f"System-Alert: CPU={cpu_pct:.0f}% RAM={ram_pct:.0f}% Disk={disk_pct:.0f}%\n"
                        f"Bitte System-Ressourcen prüfen und Diagnose erstellen."
                    ),
                    target_agent="system",
                    dedup_key="system:alert",
                    cooldown_minutes=60,
                    context={"cpu": cpu_pct, "ram": ram_pct, "disk": disk_pct},
                    policy_level=POLICY["system"],
                ))

            # Kritischer Disk-Füllstand → zusätzliches Cleanup-Signal
            if disk_pct > 90.0:
                disk_score = max(0.0, min(1.0, disk_pct / 100.0))
                signals.append(AmbientSignal(
                    source="system",
                    score=disk_score,
                    description=(
                        f"Kritischer Disk-Füllstand: {disk_pct:.0f}%\n"
                        f"Bitte Cleanup durchführen: Logs, Temp-Dateien, alte Backups prüfen."
                    ),
                    target_agent="shell",
                    dedup_key="system:disk_critical",
                    cooldown_minutes=120,
                    context={"disk": disk_pct},
                    policy_level=POLICY["system"],
                ))
        except Exception as e:
            log.debug("SystemWatcher fehlgeschlagen: %s", e)
        return signals

    # ------------------------------------------------------------------
    # Haupt-Zyklus
    # ------------------------------------------------------------------

    async def run_cycle(self) -> dict:
        """
        Führt einen Ambient-Context-Zyklus durch.
        Gibt Statistik zurück: {status, signals_found, tasks_queued, sources_checked}.
        """
        start = datetime.now()
        log.debug("AmbientContextEngine: Zyklus startet")

        results = await asyncio.gather(
            self._check_emails(),
            self._check_files(),
            self._check_goal_staleness(),
            self._check_system(),
            return_exceptions=True,
        )

        all_signals: List[AmbientSignal] = []
        sources_checked = 0
        for result in results:
            if isinstance(result, Exception):
                log.debug("Signalquelle fehlgeschlagen: %s", result)
            elif isinstance(result, list):
                all_signals.extend(result)
                sources_checked += 1

        tasks_created = 0
        for signal in all_signals:
            try:
                created = await self._process_signal(signal)
                if created:
                    tasks_created += 1
            except Exception as e:
                log.debug("Signal-Verarbeitung fehlgeschlagen: %s", e)

        elapsed = (datetime.now() - start).total_seconds()
        log.info(
            "🌐 AmbientContextEngine: %d Signal(e) → %d Task(s) [%.1fs]",
            len(all_signals), tasks_created, elapsed,
        )
        return {
            "status": "ok",
            "signals_found": len(all_signals),
            "tasks_queued": tasks_created,
            "sources_checked": sources_checked,
            "elapsed_s": round(elapsed, 2),
        }
