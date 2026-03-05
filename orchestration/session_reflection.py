"""
orchestration/session_reflection.py — M8: Session Reflection Loop

Analysiert automatisch abgeschlossene Sessions und akkumuliert
Verbesserungsmuster aus Erfolgen und Fehlern.

Feature-Flag: AUTONOMY_REFLECTION_ENABLED=false
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

log = logging.getLogger("SessionReflectionLoop")

MEMORY_DB_PATH = Path(__file__).resolve().parents[1] / "data" / "timus_memory.db"

IDLE_THRESHOLD_MIN = int(os.getenv("REFLECTION_IDLE_THRESHOLD_MIN", "30"))
PATTERN_THRESHOLD = 3  # Gleicher Pattern ≥3x → improvement_suggestion


# ──────────────────────────────────────────────────────────────────
# DB-Migration
# ──────────────────────────────────────────────────────────────────

_SCHEMA = """
CREATE TABLE IF NOT EXISTS session_reflections (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT,
    reflected_at TEXT,
    tasks_count INTEGER,
    success_rate REAL,
    what_worked_json TEXT,
    what_failed_json TEXT,
    patterns_json TEXT,
    improvements_json TEXT
);

CREATE TABLE IF NOT EXISTS improvement_suggestions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pattern TEXT UNIQUE,
    occurrences INTEGER DEFAULT 1,
    suggestion TEXT,
    applied INTEGER DEFAULT 0,
    created_at TEXT
);
"""


def _ensure_tables(db_path: Path = MEMORY_DB_PATH) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(str(db_path)) as conn:
        conn.executescript(_SCHEMA)
        conn.commit()


# ──────────────────────────────────────────────────────────────────
# Dataclasses
# ──────────────────────────────────────────────────────────────────

@dataclass
class ReflectionSummary:
    session_id: str
    tasks_count: int
    success_rate: float
    what_worked: List[str] = field(default_factory=list)
    what_failed: List[str] = field(default_factory=list)
    patterns: List[str] = field(default_factory=list)
    improvements: List[str] = field(default_factory=list)
    reflected_at: str = field(default_factory=lambda: datetime.now().isoformat())


# ──────────────────────────────────────────────────────────────────
# SessionReflectionLoop
# ──────────────────────────────────────────────────────────────────

class SessionReflectionLoop:
    """
    Automatischer End-of-Session Reflection Loop.

    Erkennt Pausen ohne Aktivität und führt dann eine Reflexion
    über alle Tasks der letzten Session durch.
    """

    def __init__(self, db_path: Path = MEMORY_DB_PATH):
        self.db_path = db_path
        self._last_session_end: Optional[str] = None
        _ensure_tables(db_path)

    # ------------------------------------------------------------------
    # Hauptmethode
    # ------------------------------------------------------------------

    async def check_and_reflect(self) -> Optional[ReflectionSummary]:
        """
        Prüft ob eine Session gerade beendet wurde und führt Reflexion durch.

        Returns:
            ReflectionSummary wenn eine Reflexion stattgefunden hat, sonst None
        """
        try:
            last_activity, gap_minutes = self._get_last_activity_gap()

            if gap_minutes is None or gap_minutes < IDLE_THRESHOLD_MIN:
                return None

            # Prüfen ob diese Session schon reflektiert wurde
            if self._already_reflected(last_activity):
                return None

            # Tasks der letzten Session sammeln
            session_tasks = self._get_session_tasks(last_activity)
            if not session_tasks:
                return None

            log.info(
                "🪞 Session-Reflexion: %d Tasks, %.0f min Pause",
                len(session_tasks),
                gap_minutes,
            )

            # Reflexion durchführen
            summary = await self._build_reflection_summary(session_tasks, last_activity)

            # Speichern
            self._save_reflection(summary)

            # Pattern-Akkumulation
            self._accumulate_patterns(summary)

            # Soul-Drift: Erfolge → task_success
            if summary.success_rate >= 0.7:
                try:
                    from memory.soul_engine import get_soul_engine
                    get_soul_engine().apply_drift(
                        reflection=None,
                        user_input="task_success_batch",
                    )
                except Exception:
                    pass

            # M16: Reflexion → Hook-Feedback
            self._apply_reflection_to_hooks(summary)

            # Telegram-Push
            if os.getenv("REFLECTION_TELEGRAM_ENABLED", "true").lower() == "true":
                await self._send_telegram(summary)

            return summary

        except Exception as e:
            log.warning("SessionReflectionLoop.check_and_reflect fehlgeschlagen: %s", e)
            return None

    # ------------------------------------------------------------------
    # Hilfsmethoden
    # ------------------------------------------------------------------

    def _get_last_activity_gap(self) -> tuple[Optional[str], Optional[float]]:
        """
        Ermittelt letzte Aktivität und die Pause seit jetzt.

        Returns:
            (last_activity_iso, gap_minutes) oder (None, None)
        """
        try:
            with sqlite3.connect(str(self.db_path)) as conn:
                row = conn.execute(
                    "SELECT MAX(timestamp) FROM interaction_events"
                ).fetchone()
                if not row or not row[0]:
                    return None, None

                last_ts = row[0]
                last_dt = datetime.fromisoformat(last_ts)
                gap = (datetime.now() - last_dt).total_seconds() / 60
                return last_ts, gap
        except Exception as e:
            log.debug("_get_last_activity_gap: %s", e)
            return None, None

    def _already_reflected(self, last_activity: str) -> bool:
        """Prüft ob für diese Aktivitätszeit bereits reflektiert wurde."""
        try:
            with sqlite3.connect(str(self.db_path)) as conn:
                row = conn.execute(
                    "SELECT id FROM session_reflections WHERE reflected_at >= ? LIMIT 1",
                    (last_activity,),
                ).fetchone()
                return row is not None
        except Exception:
            return False

    def _get_session_tasks(self, last_activity: str) -> List[Dict[str, Any]]:
        """
        Lädt alle Tasks aus der letzten Session (max. 24h vor last_activity).
        """
        try:
            cutoff = (
                datetime.fromisoformat(last_activity) - timedelta(hours=24)
            ).isoformat()
            with sqlite3.connect(str(self.db_path)) as conn:
                rows = conn.execute(
                    """SELECT content, role, timestamp FROM interaction_events
                       WHERE timestamp >= ? AND timestamp <= ?
                       ORDER BY timestamp ASC LIMIT 100""",
                    (cutoff, last_activity),
                ).fetchall()
                return [
                    {"content": r[0], "role": r[1], "timestamp": r[2]}
                    for r in rows
                ]
        except Exception as e:
            log.debug("_get_session_tasks: %s", e)
            return []

    async def _build_reflection_summary(
        self,
        tasks: List[Dict[str, Any]],
        last_activity: str,
    ) -> ReflectionSummary:
        """
        Erstellt eine Reflexions-Zusammenfassung mit LLM oder Fallback.
        """
        session_id = str(uuid.uuid4())[:8]

        # Versuche LLM-Reflexion
        llm_result = await self._call_reflection_llm(tasks)

        if llm_result:
            return ReflectionSummary(
                session_id=session_id,
                tasks_count=len(tasks),
                success_rate=llm_result.get("success_rate", 0.5),
                what_worked=llm_result.get("what_worked", []),
                what_failed=llm_result.get("what_failed", []),
                patterns=llm_result.get("patterns", []),
                improvements=llm_result.get("improvements", []),
            )

        # Fallback: einfache Statistik
        return ReflectionSummary(
            session_id=session_id,
            tasks_count=len(tasks),
            success_rate=0.5,
            what_worked=["Session abgeschlossen"],
            what_failed=[],
            patterns=[],
            improvements=[],
        )

    async def _call_reflection_llm(
        self, tasks: List[Dict[str, Any]]
    ) -> Optional[Dict[str, Any]]:
        """LLM-Analyse der Session-Tasks."""
        try:
            from memory.reflection_engine import get_reflection_engine

            engine = get_reflection_engine()
            if not engine.llm:
                return None

            # Komprimierte Task-Liste für den Prompt
            task_summary = "\n".join(
                f"[{t['role']}] {str(t['content'])[:150]}"
                for t in tasks[-20:]
            )

            prompt = f"""Analysiere diese Konversations-Session und erstelle eine Reflexion.

SESSION-INHALT (letzte 20 Nachrichten):
{task_summary}

Antworte NUR als gültiges JSON:
{{
    "success_rate": 0.8,
    "what_worked": ["Punkt 1", "Punkt 2"],
    "what_failed": ["Problem 1"],
    "patterns": ["Pattern 1"],
    "improvements": ["Verbesserung 1"]
}}"""

            import asyncio

            from utils.openai_compat import prepare_openai_params

            client = engine._resolve_chat_client()
            if not client:
                return None

            response = await asyncio.to_thread(
                client.chat.completions.create,
                **prepare_openai_params({
                    "model": os.getenv("REFLECTION_MODEL", "gpt-4o-mini"),
                    "messages": [
                        {
                            "role": "system",
                            "content": "Du analysierst KI-Agenten-Sessions. Antworte NUR mit gültigem JSON.",
                        },
                        {"role": "user", "content": prompt},
                    ],
                    "max_tokens": 400,
                    "temperature": 0.3,
                    "response_format": {"type": "json_object"},
                }),
            )
            import re as _re

            raw = response.choices[0].message.content or ""
            raw = raw.strip()
            # JSON-Block extrahieren falls nötig
            m = _re.search(r"\{[\s\S]+\}", raw)
            if m:
                raw = m.group(0)
            return json.loads(raw)
        except Exception as e:
            log.debug("_call_reflection_llm: %s", e)
            return None

    def _save_reflection(self, summary: ReflectionSummary) -> None:
        """Speichert Reflexion in session_reflections Tabelle."""
        try:
            with sqlite3.connect(str(self.db_path)) as conn:
                conn.execute(
                    """INSERT INTO session_reflections
                       (session_id, reflected_at, tasks_count, success_rate,
                        what_worked_json, what_failed_json, patterns_json, improvements_json)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        summary.session_id,
                        summary.reflected_at,
                        summary.tasks_count,
                        summary.success_rate,
                        json.dumps(summary.what_worked, ensure_ascii=False),
                        json.dumps(summary.what_failed, ensure_ascii=False),
                        json.dumps(summary.patterns, ensure_ascii=False),
                        json.dumps(summary.improvements, ensure_ascii=False),
                    ),
                )
                conn.commit()
        except Exception as e:
            log.warning("_save_reflection: %s", e)

    def _accumulate_patterns(self, summary: ReflectionSummary) -> None:
        """
        Akkumuliert Patterns; wenn ≥3x dasselbe → improvement_suggestion erstellen.
        """
        try:
            with sqlite3.connect(str(self.db_path)) as conn:
                for pattern in summary.patterns[:5]:
                    if not pattern:
                        continue
                    existing = conn.execute(
                        "SELECT id, occurrences FROM improvement_suggestions WHERE pattern = ?",
                        (pattern,),
                    ).fetchone()

                    if existing:
                        new_count = existing[1] + 1
                        conn.execute(
                            "UPDATE improvement_suggestions SET occurrences = ? WHERE id = ?",
                            (new_count, existing[0]),
                        )
                        if new_count >= PATTERN_THRESHOLD:
                            log.info(
                                "💡 Pattern-Schwelle erreicht (%dx): %s",
                                new_count,
                                pattern[:80],
                            )
                    else:
                        suggestion = (
                            f"Häufig beobachtet: {pattern}. "
                            "Overhaul oder Automatisierung erwägen."
                        )
                        conn.execute(
                            """INSERT OR IGNORE INTO improvement_suggestions
                               (pattern, occurrences, suggestion, applied, created_at)
                               VALUES (?, 1, ?, 0, ?)""",
                            (pattern, suggestion, datetime.now().isoformat()),
                        )
                conn.commit()
        except Exception as e:
            log.warning("_accumulate_patterns: %s", e)

    def _apply_reflection_to_hooks(self, summary: ReflectionSummary) -> None:
        """
        M16: Verknüpft Reflexions-Ergebnisse mit behavior_hooks.

        - what_worked-Einträge → positive Feedback-Signal
        - what_failed-Einträge → negative Feedback-Signal

        Sucht Hooks die thematisch zu den Einträgen passen.
        """
        if not os.getenv("AUTONOMY_M16_ENABLED", "false").lower() == "true":
            return
        try:
            from orchestration.feedback_engine import get_feedback_engine
            from memory.soul_engine import get_soul_engine

            soul = get_soul_engine()
            feedback = get_feedback_engine()
            action_id = f"reflection_{summary.session_id}"

            # Positive Signale aus what_worked
            for item in summary.what_worked[:3]:
                if not item:
                    continue
                # Hooks mit thematischer Überlappung finden
                hooks_updated = soul.apply_hook_feedback(item[:30], "positive")
                feedback.record_signal(
                    action_id=f"{action_id}_pos",
                    signal="positive",
                    context={"source": "reflection", "item": item[:80]},
                )

            # Negative Signale aus what_failed
            for item in summary.what_failed[:3]:
                if not item:
                    continue
                soul.apply_hook_feedback(item[:30], "negative")
                feedback.record_signal(
                    action_id=f"{action_id}_neg",
                    signal="negative",
                    context={"source": "reflection", "item": item[:80]},
                )

            log.info(
                "M16 Reflection→Hooks: %d positiv, %d negativ",
                len(summary.what_worked[:3]),
                len(summary.what_failed[:3]),
            )
        except Exception as e:
            log.debug("_apply_reflection_to_hooks: %s", e)

    async def _send_telegram(self, summary: ReflectionSummary) -> None:
        """Telegram-Push mit Reflexions-Zusammenfassung."""
        try:
            rate_pct = int(summary.success_rate * 100)
            worked = summary.what_worked[:2]
            failed = summary.what_failed[:2]

            lines = [
                f"🪞 *Session-Reflexion abgeschlossen*",
                f"Tasks: {summary.tasks_count} · Erfolgsrate: {rate_pct}%",
            ]
            if worked:
                lines.append("✅ " + " | ".join(worked))
            if failed:
                lines.append("⚠️ " + " | ".join(failed))
            if summary.improvements:
                lines.append(f"💡 {summary.improvements[0][:100]}")

            from utils.telegram_notify import send_telegram

            await send_telegram("\n".join(lines))
        except Exception as e:
            log.debug("_send_telegram: %s", e)

    # ------------------------------------------------------------------
    # Abfrage-Methoden
    # ------------------------------------------------------------------

    async def get_recent_reflections(self, limit: int = 10) -> List[dict]:
        """Gibt die letzten Reflexionen zurück."""
        try:
            with sqlite3.connect(str(self.db_path)) as conn:
                rows = conn.execute(
                    """SELECT session_id, reflected_at, tasks_count, success_rate,
                              what_worked_json, what_failed_json, patterns_json, improvements_json
                       FROM session_reflections
                       ORDER BY reflected_at DESC LIMIT ?""",
                    (limit,),
                ).fetchall()
                result = []
                for r in rows:
                    result.append({
                        "session_id": r[0],
                        "reflected_at": r[1],
                        "tasks_count": r[2],
                        "success_rate": r[3],
                        "what_worked": json.loads(r[4] or "[]"),
                        "what_failed": json.loads(r[5] or "[]"),
                        "patterns": json.loads(r[6] or "[]"),
                        "improvements": json.loads(r[7] or "[]"),
                    })
                return result
        except Exception as e:
            log.debug("get_recent_reflections: %s", e)
            return []

    async def get_improvement_suggestions(self) -> List[dict]:
        """Gibt offene Verbesserungsvorschläge zurück."""
        try:
            with sqlite3.connect(str(self.db_path)) as conn:
                rows = conn.execute(
                    """SELECT id, pattern, occurrences, suggestion, applied, created_at
                       FROM improvement_suggestions
                       ORDER BY occurrences DESC, created_at DESC LIMIT 20""",
                ).fetchall()
                return [
                    {
                        "id": r[0],
                        "pattern": r[1],
                        "occurrences": r[2],
                        "suggestion": r[3],
                        "applied": bool(r[4]),
                        "created_at": r[5],
                    }
                    for r in rows
                ]
        except Exception as e:
            log.debug("get_improvement_suggestions: %s", e)
            return []
