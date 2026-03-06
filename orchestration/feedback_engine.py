"""
orchestration/feedback_engine.py — M16: Feedback Engine

Speichert Telegram-Feedback-Signale (👍/👎/🤷) und verknüpft sie mit
behavior_hooks des Soul Engine. Grundlage für echte Lernfähigkeit.

Feature-Flag: AUTONOMY_M16_ENABLED=false
ENV:
  M16_FEEDBACK_DELTA=0.15   # Weight-Änderung pro Signal
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

log = logging.getLogger("FeedbackEngine")

MEMORY_DB_PATH = Path(__file__).resolve().parents[1] / "data" / "timus_memory.db"

FEEDBACK_DELTA = float(os.getenv("M16_FEEDBACK_DELTA", "0.15"))

_SCHEMA = """
CREATE TABLE IF NOT EXISTS feedback_events (
    id          TEXT PRIMARY KEY,
    action_id   TEXT NOT NULL,
    signal      TEXT NOT NULL,
    hook_names  TEXT NOT NULL DEFAULT '[]',
    context     TEXT NOT NULL DEFAULT '{}',
    created_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_feedback_action ON feedback_events(action_id);
CREATE INDEX IF NOT EXISTS idx_feedback_signal ON feedback_events(signal);
"""


def _ensure_tables(db_path: Path = MEMORY_DB_PATH) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(str(db_path)) as conn:
        conn.executescript(_SCHEMA)
        conn.commit()


@dataclass
class FeedbackEvent:
    id: str
    action_id: str
    signal: str  # "positive" | "negative" | "neutral"
    hook_names: List[str] = field(default_factory=list)
    context: Dict = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())


class FeedbackEngine:
    """
    Nimmt Telegram-Feedback-Signale entgegen und leitet sie an den Soul Engine weiter.

    Signals:
      - positive  (👍): weight + FEEDBACK_DELTA, topic_score + 0.1
      - negative  (👎): weight - FEEDBACK_DELTA, topic_score - 0.1
      - neutral   (🤷): keine Änderung (Noop)
    """

    def __init__(self, db_path: Path = MEMORY_DB_PATH):
        self.db_path = db_path
        _ensure_tables(db_path)

    # ------------------------------------------------------------------
    # Haupt-API
    # ------------------------------------------------------------------

    def record_signal(
        self,
        action_id: str,
        signal: str,
        hook_names: Optional[List[str]] = None,
        context: Optional[Dict] = None,
    ) -> FeedbackEvent:
        """
        Speichert ein Feedback-Signal in der DB und wendet es auf Hook-Weights an.

        Args:
            action_id: ID der bewerteten Aktion (beliebiger String)
            signal: "positive", "negative" oder "neutral"
            hook_names: Liste der betroffenen behavior_hooks (optional)
            context: Zusätzlicher Kontext (topic, agent_type usw.)

        Returns:
            Gespeichertes FeedbackEvent
        """
        if signal not in {"positive", "negative", "neutral"}:
            raise ValueError(f"Ungültiges Signal: {signal!r}. Erlaubt: positive, negative, neutral")

        event = FeedbackEvent(
            id=str(uuid.uuid4()),
            action_id=action_id,
            signal=signal,
            hook_names=hook_names or [],
            context=context or {},
        )

        self._save(event)
        log.info("Feedback gespeichert: action=%s signal=%s hooks=%s", action_id, signal, event.hook_names)

        # Hook-Weights aktualisieren (nur wenn hooks angegeben)
        if signal != "neutral" and event.hook_names:
            self._apply_to_hooks(event.hook_names, signal)

        return event

    def get_hook_stats(self, hook_name: str) -> Dict:
        """
        Gibt Feedback-Statistik für einen Hook zurück.

        post: 0.05 <= __return__["weight"] <= 2.0
        post: __return__["total"] == __return__["pos"] + __return__["neg"] + __return__["neutral"]

        Returns:
            {pos: n, neg: n, neutral: n, total: n, weight: float}
        """
        try:
            with sqlite3.connect(str(self.db_path)) as conn:
                rows = conn.execute(
                    "SELECT signal, COUNT(*) FROM feedback_events "
                    "WHERE hook_names LIKE ? GROUP BY signal",
                    (f'%"{hook_name}"%',),
                ).fetchall()

            counts = {"positive": 0, "negative": 0, "neutral": 0}
            for signal, count in rows:
                if signal in counts:
                    counts[signal] = count

            total = sum(counts.values())
            # Weight als Ratio positiver Signale (nur wenn > 0 feedback vorhanden)
            if total > 0 and (counts["positive"] + counts["negative"]) > 0:
                net = counts["positive"] - counts["negative"]
                weight = 1.0 + net * FEEDBACK_DELTA
                weight = max(0.05, min(2.0, weight))
            else:
                weight = 1.0

            return {
                "pos": counts["positive"],
                "neg": counts["negative"],
                "neutral": counts["neutral"],
                "total": total,
                "weight": round(weight, 4),
            }
        except Exception as e:
            log.error("get_hook_stats fehlgeschlagen: %s", e)
            return {"pos": 0, "neg": 0, "neutral": 0, "total": 0, "weight": 1.0}

    def get_recent_events(self, limit: int = 20) -> List[FeedbackEvent]:
        """Gibt die letzten N Feedback-Events zurück."""
        try:
            with sqlite3.connect(str(self.db_path)) as conn:
                rows = conn.execute(
                    "SELECT id, action_id, signal, hook_names, context, created_at "
                    "FROM feedback_events ORDER BY created_at DESC LIMIT ?",
                    (limit,),
                ).fetchall()
            return [
                FeedbackEvent(
                    id=r[0],
                    action_id=r[1],
                    signal=r[2],
                    hook_names=json.loads(r[3] or "[]"),
                    context=json.loads(r[4] or "{}"),
                    created_at=r[5],
                )
                for r in rows
            ]
        except Exception as e:
            log.error("get_recent_events fehlgeschlagen: %s", e)
            return []

    def process_pending(self) -> int:
        """
        Heartbeat-Hook: verarbeitet noch offene Signals (Future-Use).
        Aktuell immer sofort verarbeitet — gibt Anzahl letzter Events zurück.
        """
        try:
            with sqlite3.connect(str(self.db_path)) as conn:
                count = conn.execute(
                    "SELECT COUNT(*) FROM feedback_events WHERE DATE(created_at) = DATE('now')"
                ).fetchone()[0]
            return count
        except Exception:
            return 0

    # ------------------------------------------------------------------
    # Interne Helfer
    # ------------------------------------------------------------------

    def _save(self, event: FeedbackEvent) -> None:
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.execute(
                "INSERT INTO feedback_events (id, action_id, signal, hook_names, context, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    event.id,
                    event.action_id,
                    event.signal,
                    json.dumps(event.hook_names, ensure_ascii=False),
                    json.dumps(event.context, ensure_ascii=False),
                    event.created_at,
                ),
            )
            conn.commit()

    def _apply_to_hooks(self, hook_names: List[str], signal: str) -> None:
        """Wendet Feedback-Signal auf Soul Engine Hooks an."""
        try:
            from memory.soul_engine import get_soul_engine
            soul = get_soul_engine()
            for hook_name in hook_names:
                soul.apply_hook_feedback(hook_name, signal)
        except Exception as e:
            log.warning("Hook-Feedback konnte nicht angewendet werden: %s", e)


# ------------------------------------------------------------------
# Singleton
# ------------------------------------------------------------------

_engine: Optional[FeedbackEngine] = None


def get_feedback_engine() -> FeedbackEngine:
    global _engine
    if _engine is None:
        _engine = FeedbackEngine()
    return _engine
