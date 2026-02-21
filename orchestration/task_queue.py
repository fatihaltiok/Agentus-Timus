"""
orchestration/task_queue.py

Persistente SQLite-Task-Queue für Timus.
Ersetzt tasks.json mit echtem Priority-System und atomaren Operationen.

Prioritäten:  CRITICAL(0) > HIGH(1) > NORMAL(2) > LOW(3)
Task-Typen:   manual | scheduled | triggered | delegated
Status:       pending → in_progress → completed | failed | cancelled
"""

import logging
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime
from enum import IntEnum
from pathlib import Path
from typing import Generator, List, Optional

log = logging.getLogger("TaskQueue")

DB_PATH = Path(__file__).parent.parent / "data" / "task_queue.db"


# ──────────────────────────────────────────────────────────────────
# Enums
# ──────────────────────────────────────────────────────────────────

class Priority(IntEnum):
    CRITICAL = 0
    HIGH     = 1
    NORMAL   = 2
    LOW      = 3


class TaskType:
    MANUAL    = "manual"      # Vom User direkt eingegeben
    SCHEDULED = "scheduled"   # Zeitgesteuert (Cron)
    TRIGGERED = "triggered"   # Durch Webhook/Event
    DELEGATED = "delegated"   # Von einem anderen Agenten


class TaskStatus:
    PENDING     = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED   = "completed"
    FAILED      = "failed"
    CANCELLED   = "cancelled"


# ──────────────────────────────────────────────────────────────────
# Schema
# ──────────────────────────────────────────────────────────────────

SCHEMA = """
CREATE TABLE IF NOT EXISTS tasks (
    id           TEXT PRIMARY KEY,
    description  TEXT NOT NULL,
    priority     INTEGER NOT NULL DEFAULT 2,
    task_type    TEXT NOT NULL DEFAULT 'manual',
    target_agent TEXT,
    status       TEXT NOT NULL DEFAULT 'pending',
    retry_count  INTEGER NOT NULL DEFAULT 0,
    max_retries  INTEGER NOT NULL DEFAULT 3,
    created_at   TEXT NOT NULL,
    run_at       TEXT,
    started_at   TEXT,
    completed_at TEXT,
    result       TEXT,
    error        TEXT,
    metadata     TEXT
);

CREATE INDEX IF NOT EXISTS idx_status_priority
    ON tasks (status, priority, created_at);

CREATE INDEX IF NOT EXISTS idx_run_at
    ON tasks (run_at, status);
"""


# ──────────────────────────────────────────────────────────────────
# TaskQueue
# ──────────────────────────────────────────────────────────────────

class TaskQueue:
    """
    Thread-safe SQLite-basierte Task-Queue.
    Liefert Tasks in Reihenfolge: Priorität → Erstellungszeit.
    """

    def __init__(self, db_path: Path = DB_PATH):
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    # ------------------------------------------------------------------
    # DB-Verwaltung
    # ------------------------------------------------------------------

    @contextmanager
    def _conn(self) -> Generator[sqlite3.Connection, None, None]:
        conn = sqlite3.connect(self.db_path, timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")   # Parallele Reads
        conn.execute("PRAGMA foreign_keys=ON")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _init_db(self) -> None:
        with self._conn() as conn:
            conn.executescript(SCHEMA)
            # Migration: fehlende Spalten ergänzen (für bestehende DBs)
            existing_cols = {row[1] for row in conn.execute("PRAGMA table_info(tasks)")}
            for col, definition in [("run_at", "TEXT")]:
                if col not in existing_cols:
                    conn.execute(f"ALTER TABLE tasks ADD COLUMN {col} {definition}")
                    log.info(f"Migration: Spalte '{col}' hinzugefügt")
        log.info(f"TaskQueue initialisiert: {self.db_path}")

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    def add(
        self,
        description: str,
        priority: int = Priority.NORMAL,
        task_type: str = TaskType.MANUAL,
        target_agent: Optional[str] = None,
        max_retries: int = 3,
        metadata: Optional[str] = None,
        run_at: Optional[str] = None,
    ) -> str:
        """
        Fügt einen Task hinzu. Gibt die Task-ID zurück.
        run_at: ISO-8601 Zeitpunkt (z.B. '2026-02-22T09:00:00') für Erinnerungen.
                Tasks mit run_at werden erst ab diesem Zeitpunkt ausgeführt.
        """
        task_id = str(uuid.uuid4())
        now = datetime.now().isoformat()
        with self._conn() as conn:
            conn.execute(
                """INSERT INTO tasks
                   (id, description, priority, task_type, target_agent,
                    status, retry_count, max_retries, created_at, run_at, metadata)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (task_id, description, priority, task_type, target_agent,
                 TaskStatus.PENDING, 0, max_retries, now, run_at, metadata),
            )
        when = f" | fällig: {run_at[:16]}" if run_at else ""
        log.info(f"Task hinzugefügt [{task_id[:8]}] prio={priority}{when}: {description[:60]}")
        return task_id

    def get_due_reminders(self) -> List[dict]:
        """Gibt alle Erinnerungen zurück deren run_at-Zeit erreicht ist."""
        now = datetime.now().isoformat()
        with self._conn() as conn:
            rows = conn.execute(
                """SELECT * FROM tasks
                   WHERE status='pending' AND run_at IS NOT NULL AND run_at <= ?
                   ORDER BY run_at ASC""",
                (now,),
            ).fetchall()
            return [dict(r) for r in rows]

    def claim_next(self) -> Optional[dict]:
        """
        Holt den nächsten pending Task (höchste Priorität, ältester zuerst)
        und markiert ihn atomar als in_progress.
        Gibt None zurück wenn keine Tasks verfügbar.
        Thread-safe durch EXCLUSIVE-Transaktion.
        """
        with self._conn() as conn:
            # Subquery-basiertes atomares UPDATE: kein SELECT → UPDATE Race
            now = datetime.now().isoformat()
            row = conn.execute(
                """UPDATE tasks SET status='in_progress', started_at=?
                   WHERE id = (
                       SELECT id FROM tasks
                       WHERE status = 'pending'
                         AND (run_at IS NULL OR run_at <= ?)
                       ORDER BY priority ASC, created_at ASC
                       LIMIT 1
                   )
                   RETURNING *""",
                (now, now),
            ).fetchone()
            return dict(row) if row else None

    def complete(self, task_id: str, result: str) -> None:
        with self._conn() as conn:
            conn.execute(
                """UPDATE tasks
                   SET status='completed', completed_at=?, result=?
                   WHERE id=?""",
                (datetime.now().isoformat(), result[:2000], task_id),
            )

    def fail(self, task_id: str, error: str) -> bool:
        """
        Markiert Task als fehlgeschlagen.
        Gibt True zurück wenn nochmals versucht wird (retry),
        False wenn max_retries erreicht → status='failed'.
        """
        with self._conn() as conn:
            row = conn.execute(
                "SELECT retry_count, max_retries FROM tasks WHERE id=?",
                (task_id,),
            ).fetchone()

            if not row:
                return False

            new_count = row["retry_count"] + 1
            if new_count < row["max_retries"]:
                # Retry: zurück auf pending
                conn.execute(
                    """UPDATE tasks
                       SET status='pending', retry_count=?, error=?, started_at=NULL
                       WHERE id=?""",
                    (new_count, error[:500], task_id),
                )
                log.info(f"Task [{task_id[:8]}] → Retry {new_count}/{row['max_retries']}")
                return True
            else:
                conn.execute(
                    """UPDATE tasks
                       SET status='failed', completed_at=?, error=?, retry_count=?
                       WHERE id=?""",
                    (datetime.now().isoformat(), error[:500], new_count, task_id),
                )
                log.warning(f"Task [{task_id[:8]}] → endgültig fehlgeschlagen nach {new_count} Versuchen")
                return False

    def cancel(self, task_id: str) -> None:
        with self._conn() as conn:
            conn.execute(
                "UPDATE tasks SET status='cancelled', completed_at=? WHERE id=?",
                (datetime.now().isoformat(), task_id),
            )

    # ------------------------------------------------------------------
    # Abfragen
    # ------------------------------------------------------------------

    def get_pending(self) -> List[dict]:
        """Alle pending Tasks, sortiert nach Priorität."""
        with self._conn() as conn:
            rows = conn.execute(
                """SELECT * FROM tasks
                   WHERE status='pending'
                   ORDER BY priority ASC, created_at ASC"""
            ).fetchall()
            return [dict(r) for r in rows]

    def get_all(self, limit: int = 50) -> List[dict]:
        """Alle Tasks (neueste zuerst)."""
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM tasks ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
            return [dict(r) for r in rows]

    def get_by_id(self, task_id: str) -> Optional[dict]:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM tasks WHERE id=?", (task_id,)
            ).fetchone()
            return dict(row) if row else None

    def stats(self) -> dict:
        """Zusammenfassung der Queue."""
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT status, COUNT(*) as n FROM tasks GROUP BY status"
            ).fetchall()
            return {r["status"]: r["n"] for r in rows}


# ──────────────────────────────────────────────────────────────────
# Migration: tasks.json → SQLite
# ──────────────────────────────────────────────────────────────────

def migrate_from_json(
    queue: TaskQueue,
    json_path: Path = Path(__file__).parent.parent / "tasks.json",
) -> int:
    """
    Importiert bestehende tasks.json-Einträge in die SQLite-Queue.
    Überspringt bereits vorhandene IDs. Gibt Anzahl migrierter Tasks zurück.
    """
    import json

    if not json_path.exists():
        return 0

    try:
        data = json.loads(json_path.read_text(encoding="utf-8"))
    except Exception as e:
        log.error(f"Migration: tasks.json nicht lesbar: {e}")
        return 0

    migrated = 0
    for t in data.get("tasks", []):
        task_id = t.get("id")
        if not task_id:
            continue

        # Bereits vorhanden?
        if queue.get_by_id(task_id):
            continue

        # Status mappen
        raw_status = t.get("status", "pending")
        status = raw_status if raw_status in (
            TaskStatus.PENDING, TaskStatus.IN_PROGRESS,
            TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED,
        ) else TaskStatus.PENDING

        # Priorität mappen (tasks.json nutzte 1-3, wir 0-3)
        raw_prio = t.get("priority", 2)
        priority = max(0, min(3, raw_prio))

        now = datetime.now().isoformat()
        try:
            with queue._conn() as conn:
                conn.execute(
                    """INSERT INTO tasks
                       (id, description, priority, task_type, target_agent,
                        status, retry_count, max_retries, created_at,
                        completed_at, result, error)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        task_id,
                        t.get("description", ""),
                        priority,
                        TaskType.MANUAL,
                        t.get("target_agent"),
                        status,
                        0, 3,
                        t.get("created_at", now),
                        t.get("completed_at"),
                        t.get("result_summary"),
                        None,
                    ),
                )
            migrated += 1
        except sqlite3.IntegrityError:
            pass  # Doppelt — überspringen

    log.info(f"Migration: {migrated} Tasks aus tasks.json importiert")
    return migrated


# ──────────────────────────────────────────────────────────────────
# Singleton
# ──────────────────────────────────────────────────────────────────

_queue: Optional[TaskQueue] = None


def get_queue() -> TaskQueue:
    global _queue
    if _queue is None:
        _queue = TaskQueue()
    return _queue
