"""
orchestration/goal_generator.py

Signal-basierte Zielgenerierung fuer M1.2:
- Memory-Signale (last_user_goal, open_threads, top_topics)
- Curiosity-Signale (curiosity_sent)
- Event-Signale (unzugeordnete triggered Tasks)
"""

from __future__ import annotations

import logging
import os
import re
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from orchestration.task_queue import GoalStatus, TaskQueue, get_queue

log = logging.getLogger("GoalGenerator")


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name, "true" if default else "false").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def _goals_feature_enabled() -> bool:
    if _env_bool("AUTONOMY_COMPAT_MODE", True):
        return False
    return _env_bool("AUTONOMY_GOALS_ENABLED", False)


def _normalize_title(text: str) -> str:
    value = re.sub(r"\s+", " ", (text or "").strip().lower())
    return value


def _shorten(text: str, max_len: int = 140) -> str:
    clean = re.sub(r"\s+", " ", (text or "").strip())
    if len(clean) <= max_len:
        return clean
    return f"{clean[:max_len - 3].rstrip()}..."


@dataclass
class GoalSignal:
    title: str
    source: str
    priority_score: float = 0.5
    description: Optional[str] = None
    task_ids: List[str] = field(default_factory=list)


class GoalGenerator:
    """Erzeugt Ziele aus mehreren Signalkanälen."""

    def __init__(
        self,
        queue: Optional[TaskQueue] = None,
        memory_state_provider: Optional[Callable[[], Dict[str, Any]]] = None,
        curiosity_db_path: Optional[Path] = None,
        curiosity_lookback_hours: int = 72,
    ):
        self.queue = queue or get_queue()
        self.memory_state_provider = memory_state_provider or self._default_memory_state_provider
        self.curiosity_db_path = curiosity_db_path
        self.curiosity_lookback_hours = max(1, int(curiosity_lookback_hours))

    def run_cycle(self, max_goals: int = 3) -> List[str]:
        """Fuehrt eine Generierungsrunde aus und gibt Goal-IDs zurueck."""
        if not _goals_feature_enabled():
            return []

        signals = self.collect_signals()
        if not signals:
            return []

        deduped = self._dedupe_signals(signals)
        created: List[str] = []
        for signal in deduped[: max(1, int(max_goals))]:
            if not signal.title.strip():
                continue
            goal_id = self.queue.upsert_goal_from_signal(
                title=_shorten(signal.title, max_len=140),
                source=signal.source,
                description=_shorten(signal.description or "", max_len=280) or None,
                priority_score=signal.priority_score,
                status=GoalStatus.ACTIVE,
            )
            created.append(goal_id)
            self.queue.update_goal_state(
                goal_id,
                last_event=f"signal:{signal.source}",
            )
            for task_id in signal.task_ids:
                self.queue.assign_task_goal(task_id, goal_id)

        if created:
            log.info("🎯 GoalGenerator: %d Ziel(e) aktualisiert/erstellt", len(created))
        return created

    def collect_signals(self) -> List[GoalSignal]:
        signals: List[GoalSignal] = []
        signals.extend(self._memory_signals())
        signals.extend(self._curiosity_signals())
        signals.extend(self._event_signals())
        return signals

    def _dedupe_signals(self, signals: List[GoalSignal]) -> List[GoalSignal]:
        merged: Dict[str, GoalSignal] = {}
        for signal in signals:
            key = _normalize_title(signal.title)
            if not key:
                continue
            existing = merged.get(key)
            if existing is None:
                merged[key] = GoalSignal(
                    title=signal.title,
                    source=signal.source,
                    priority_score=float(signal.priority_score),
                    description=signal.description,
                    task_ids=list(signal.task_ids),
                )
                continue

            existing.priority_score = max(existing.priority_score, float(signal.priority_score))
            if not existing.description and signal.description:
                existing.description = signal.description
            existing.task_ids = sorted(set(existing.task_ids + list(signal.task_ids)))
        result = list(merged.values())
        result.sort(key=lambda item: item.priority_score, reverse=True)
        return result

    def _default_memory_state_provider(self) -> Dict[str, Any]:
        try:
            from memory.memory_system import memory_manager

            state = memory_manager.session.get_dynamic_state()
            return state if isinstance(state, dict) else {}
        except Exception:
            return {}

    def _memory_signals(self) -> List[GoalSignal]:
        state = self.memory_state_provider() or {}
        if not isinstance(state, dict):
            return []

        signals: List[GoalSignal] = []

        last_goal = _shorten(str(state.get("last_user_goal", "")), max_len=140)
        if len(last_goal) >= 8:
            signals.append(
                GoalSignal(
                    title=last_goal,
                    source="memory_last_user_goal",
                    priority_score=0.88,
                )
            )

        for thread in state.get("open_threads", [])[:3]:
            thread_text = _shorten(str(thread), max_len=140)
            if len(thread_text) >= 8:
                signals.append(
                    GoalSignal(
                        title=thread_text,
                        source="memory_open_thread",
                        priority_score=0.8,
                    )
                )

        for topic in state.get("top_topics", [])[:2]:
            topic_text = _shorten(str(topic), max_len=70)
            if len(topic_text) >= 3:
                signals.append(
                    GoalSignal(
                        title=f"Vertiefe Thema: {topic_text}",
                        source="memory_topic",
                        priority_score=0.6,
                    )
                )

        return signals

    def _curiosity_signals(self) -> List[GoalSignal]:
        db_path = self.curiosity_db_path
        if db_path is None:
            try:
                from orchestration.curiosity_engine import MEMORY_DB_PATH

                db_path = MEMORY_DB_PATH
            except Exception:
                return []
        if not db_path or not Path(db_path).exists():
            return []

        cutoff = (datetime.now() - timedelta(hours=self.curiosity_lookback_hours)).isoformat()
        try:
            with sqlite3.connect(db_path) as conn:
                has_table = conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name='curiosity_sent'"
                ).fetchone()
                if not has_table:
                    return []

                rows = conn.execute(
                    """SELECT topic, title, score, url, sent_at
                       FROM curiosity_sent
                       WHERE sent_at >= ?
                       ORDER BY sent_at DESC
                       LIMIT 3""",
                    (cutoff,),
                ).fetchall()
        except Exception:
            return []

        signals: List[GoalSignal] = []
        for row in rows:
            topic = str(row[0] or "").strip()
            title = str(row[1] or "").strip()
            score = float(row[2] or 0.0)
            url = str(row[3] or "").strip()
            base = _shorten(title or topic, max_len=95)
            if not base:
                continue
            prio = min(0.95, max(0.55, score / 10.0))
            detail = f"Curiosity Follow-up ({row[4] or ''})"
            if url:
                detail = f"{detail} | {url}"
            signals.append(
                GoalSignal(
                    title=f"Curiosity-Follow-up: {base}",
                    source="curiosity_sent",
                    priority_score=prio,
                    description=_shorten(detail, max_len=280),
                )
            )
        return signals

    def _event_signals(self) -> List[GoalSignal]:
        tasks = self.queue.get_unassigned_triggered_tasks(limit=8)
        signals: List[GoalSignal] = []
        for task in tasks:
            task_id = str(task.get("id") or "")
            desc = _shorten(str(task.get("description") or ""), max_len=110)
            if not task_id or not desc:
                continue

            prio_raw = int(task.get("priority") or 2)
            prio_map = {0: 0.95, 1: 0.82, 2: 0.68, 3: 0.55}
            prio = prio_map.get(prio_raw, 0.65)
            signals.append(
                GoalSignal(
                    title=f"Event-Aufgabe: {desc}",
                    source="event_triggered_task",
                    priority_score=prio,
                    description=f"Automatisch aus Event-Task {task_id[:8]} abgeleitet",
                    task_ids=[task_id],
                )
            )
        return signals
