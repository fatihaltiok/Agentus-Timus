"""
orchestration/proactive_triggers.py — M10: Proactive Triggers

Zeitgesteuerte Routinen für Timus.
Trigger feuern wenn Uhrzeit ±FIRE_WINDOW_MIN passt und noch nicht heute ausgelöst.

Feature-Flag: AUTONOMY_PROACTIVE_TRIGGERS_ENABLED=false
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
from typing import List, Optional

log = logging.getLogger("ProactiveTriggers")

DB_PATH = Path(__file__).resolve().parents[1] / "data" / "task_queue.db"

FIRE_WINDOW_MIN = 14  # ±14 Minuten Toleranzfenster


# ──────────────────────────────────────────────────────────────────
# Dataclass
# ──────────────────────────────────────────────────────────────────

@dataclass
class ProactiveTrigger:
    name: str
    time_of_day: str         # "HH:MM"
    action_query: str
    target_agent: str = "meta"
    days_of_week: List[int] = field(default_factory=list)  # [] = täglich
    enabled: bool = True
    last_fired_at: str = ""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))


# ──────────────────────────────────────────────────────────────────
# Built-in Templates
# ──────────────────────────────────────────────────────────────────

MORNING_ROUTINE = ProactiveTrigger(
    name="Morgen-Routine",
    time_of_day="08:00",
    days_of_week=[0, 1, 2, 3, 4],  # Mo–Fr
    action_query="Prüfe neue E-Mails, fasse sie zusammen und schlage Aktionen vor.",
    target_agent="communication",
    enabled=os.getenv("TRIGGER_MORNING_ENABLED", "false").lower() == "true",
)

EVENING_REFLECTION = ProactiveTrigger(
    name="Abend-Reflexion",
    time_of_day="20:00",
    days_of_week=[],  # täglich
    action_query="Fasse den heutigen Tag zusammen: was wurde erreicht, was steht noch offen.",
    target_agent="meta",
    enabled=os.getenv("TRIGGER_EVENING_ENABLED", "false").lower() == "true",
)


# ──────────────────────────────────────────────────────────────────
# ProactiveTriggerEngine
# ──────────────────────────────────────────────────────────────────

class ProactiveTriggerEngine:
    """
    Verwaltet zeitgesteuerte Routinen und feuert sie bei Übereinstimmung.
    """

    def __init__(self, db_path: Path = DB_PATH):
        self.db_path = db_path
        self._ensure_table()
        self._seed_builtin_triggers()

    # ------------------------------------------------------------------
    # DB-Setup
    # ------------------------------------------------------------------

    def _ensure_table(self) -> None:
        """Erstellt proactive_triggers Tabelle falls nicht vorhanden."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS proactive_triggers (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    time_of_day TEXT NOT NULL,
                    days_of_week TEXT DEFAULT '[]',
                    action_query TEXT NOT NULL,
                    target_agent TEXT DEFAULT 'meta',
                    enabled INTEGER DEFAULT 1,
                    last_fired_at TEXT DEFAULT ''
                )
            """)
            conn.commit()

    def _seed_builtin_triggers(self) -> None:
        """Fügt Built-in Templates ein wenn noch nicht vorhanden."""
        for t in [MORNING_ROUTINE, EVENING_REFLECTION]:
            self._upsert_trigger_if_missing(t)

    def _upsert_trigger_if_missing(self, trigger: ProactiveTrigger) -> None:
        """Fügt Trigger ein falls noch nicht in DB."""
        with sqlite3.connect(str(self.db_path)) as conn:
            existing = conn.execute(
                "SELECT id FROM proactive_triggers WHERE name = ?",
                (trigger.name,),
            ).fetchone()
            if not existing:
                conn.execute(
                    """INSERT INTO proactive_triggers
                       (id, name, time_of_day, days_of_week, action_query,
                        target_agent, enabled, last_fired_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        trigger.id,
                        trigger.name,
                        trigger.time_of_day,
                        json.dumps(trigger.days_of_week),
                        trigger.action_query,
                        trigger.target_agent,
                        int(trigger.enabled),
                        trigger.last_fired_at,
                    ),
                )
                conn.commit()

    # ------------------------------------------------------------------
    # Auslösen
    # ------------------------------------------------------------------

    def check_and_fire(self) -> List[str]:
        """
        Prüft alle Trigger und löst fällige aus.

        Returns:
            Liste der ausgelösten Trigger-IDs
        """
        now = datetime.now()
        today = now.strftime("%Y-%m-%d")
        now_minutes = now.hour * 60 + now.minute

        fired_ids: List[str] = []

        triggers = self._load_enabled_triggers()
        for t in triggers:
            # Wochentag-Check
            if t.days_of_week and now.weekday() not in t.days_of_week:
                continue

            # Uhrzeit-Check: ±FIRE_WINDOW_MIN
            try:
                parts = t.time_of_day.split(":")
                trigger_minutes = int(parts[0]) * 60 + int(parts[1])
            except Exception:
                continue

            diff = abs(now_minutes - trigger_minutes)
            if diff > FIRE_WINDOW_MIN:
                continue

            # Duplikat-Schutz: nur 1x pro Tag
            if t.last_fired_at.startswith(today):
                continue

            # Task in Queue einstellen
            self._enqueue_trigger_task(t)

            # last_fired_at aktualisieren
            self._update_last_fired(t.id, now.isoformat())
            fired_ids.append(t.id)

            log.info("⏰ Trigger '%s' ausgelöst → %s", t.name, t.target_agent)

            # Telegram-Benachrichtigung (Event-Loop-sicheres Pattern)
            try:
                import asyncio
                from utils.telegram_notify import send_telegram

                msg = f"⏰ *Trigger '{t.name}' ausgelöst*\n→ Agent: `{t.target_agent}`"
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    asyncio.ensure_future(send_telegram(msg))
                else:
                    loop.run_until_complete(send_telegram(msg))
            except RuntimeError:
                pass
            except Exception:
                pass

        return fired_ids

    def _enqueue_trigger_task(self, trigger: ProactiveTrigger) -> None:
        """Erstellt Task in der Task-Queue."""
        try:
            from orchestration.task_queue import TaskType, Priority, get_queue

            queue = get_queue()
            queue.enqueue(
                description=trigger.action_query,
                task_type=TaskType.TRIGGERED,
                priority=Priority.NORMAL,
                target_agent=trigger.target_agent,
                metadata={"trigger_id": trigger.id, "trigger_name": trigger.name},
            )
        except Exception as e:
            log.warning("_enqueue_trigger_task: %s", e)

    def _update_last_fired(self, trigger_id: str, fired_at: str) -> None:
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.execute(
                "UPDATE proactive_triggers SET last_fired_at = ? WHERE id = ?",
                (fired_at, trigger_id),
            )
            conn.commit()

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    def _load_enabled_triggers(self) -> List[ProactiveTrigger]:
        """Lädt alle aktivierten Trigger aus der DB."""
        with sqlite3.connect(str(self.db_path)) as conn:
            rows = conn.execute(
                """SELECT id, name, time_of_day, days_of_week, action_query,
                          target_agent, enabled, last_fired_at
                   FROM proactive_triggers WHERE enabled = 1"""
            ).fetchall()
            return [self._row_to_trigger(r) for r in rows]

    @staticmethod
    def _row_to_trigger(row: tuple) -> ProactiveTrigger:
        days_raw = row[3] or "[]"
        try:
            days = json.loads(days_raw)
        except Exception:
            days = []
        return ProactiveTrigger(
            id=row[0],
            name=row[1],
            time_of_day=row[2],
            days_of_week=days,
            action_query=row[4],
            target_agent=row[5],
            enabled=bool(row[6]),
            last_fired_at=row[7] or "",
        )

    def add_trigger(self, trigger: ProactiveTrigger) -> str:
        """Fügt neuen Trigger hinzu. Gibt ID zurück."""
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.execute(
                """INSERT INTO proactive_triggers
                   (id, name, time_of_day, days_of_week, action_query,
                    target_agent, enabled, last_fired_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, '')""",
                (
                    trigger.id,
                    trigger.name,
                    trigger.time_of_day,
                    json.dumps(trigger.days_of_week),
                    trigger.action_query,
                    trigger.target_agent,
                    int(trigger.enabled),
                ),
            )
            conn.commit()
        log.info("Trigger hinzugefügt: %s (%s)", trigger.name, trigger.id)
        return trigger.id

    def remove_trigger(self, trigger_id: str) -> bool:
        """Entfernt Trigger. Gibt True zurück wenn gefunden."""
        with sqlite3.connect(str(self.db_path)) as conn:
            cursor = conn.execute(
                "DELETE FROM proactive_triggers WHERE id = ?",
                (trigger_id,),
            )
            conn.commit()
            return cursor.rowcount > 0

    def list_triggers(self) -> List[dict]:
        """Gibt alle Trigger als Dicts zurück."""
        with sqlite3.connect(str(self.db_path)) as conn:
            rows = conn.execute(
                """SELECT id, name, time_of_day, days_of_week, action_query,
                          target_agent, enabled, last_fired_at
                   FROM proactive_triggers ORDER BY name"""
            ).fetchall()
        result = []
        for r in rows:
            try:
                days = json.loads(r[3] or "[]")
            except Exception:
                days = []
            result.append({
                "id": r[0],
                "name": r[1],
                "time_of_day": r[2],
                "days_of_week": days,
                "action_query": r[4],
                "target_agent": r[5],
                "enabled": bool(r[6]),
                "last_fired_at": r[7] or "",
            })
        return result

    def enable_trigger(self, trigger_id: str, enabled: bool) -> bool:
        """Aktiviert/Deaktiviert einen Trigger. Gibt True zurück wenn gefunden."""
        with sqlite3.connect(str(self.db_path)) as conn:
            cursor = conn.execute(
                "UPDATE proactive_triggers SET enabled = ? WHERE id = ?",
                (int(enabled), trigger_id),
            )
            conn.commit()
            return cursor.rowcount > 0


# ──────────────────────────────────────────────────────────────────
# Singleton
# ──────────────────────────────────────────────────────────────────

_engine_instance: Optional[ProactiveTriggerEngine] = None


def get_trigger_engine(db_path: Path = DB_PATH) -> ProactiveTriggerEngine:
    global _engine_instance
    if _engine_instance is None:
        _engine_instance = ProactiveTriggerEngine(db_path)
    return _engine_instance
