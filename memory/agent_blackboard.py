"""
memory/agent_blackboard.py — M9: Agent Blackboard (Shared Memory)

Singleton-Blackboard für Inter-Agenten-Kommunikation.
Sub-Agenten können Ergebnisse publizieren und lesen.

Feature-Flag: AUTONOMY_BLACKBOARD_ENABLED=true (sofort aktiv, non-breaking)
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

log = logging.getLogger("AgentBlackboard")

MEMORY_DB_PATH = Path(__file__).resolve().parents[1] / "data" / "timus_memory.db"

DEFAULT_TTL_MIN = int(os.getenv("BLACKBOARD_DEFAULT_TTL_MIN", "60"))

_SCHEMA = """
CREATE TABLE IF NOT EXISTS agent_blackboard (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    agent TEXT NOT NULL,
    topic TEXT NOT NULL,
    key TEXT NOT NULL,
    value TEXT NOT NULL,
    ttl_minutes INTEGER DEFAULT 60,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    session_id TEXT DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_bb_topic ON agent_blackboard(topic);
CREATE INDEX IF NOT EXISTS idx_bb_expires ON agent_blackboard(expires_at);
"""


def _ensure_tables(db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(str(db_path)) as conn:
        conn.executescript(_SCHEMA)
        conn.commit()


# ──────────────────────────────────────────────────────────────────
# Singleton
# ──────────────────────────────────────────────────────────────────

_blackboard_instance: Optional["AgentBlackboard"] = None


def get_blackboard(db_path: Path = MEMORY_DB_PATH) -> "AgentBlackboard":
    """Gibt die globale Blackboard-Instanz zurück (Singleton)."""
    global _blackboard_instance
    if _blackboard_instance is None:
        _blackboard_instance = AgentBlackboard(db_path)
    return _blackboard_instance


# ──────────────────────────────────────────────────────────────────
# AgentBlackboard
# ──────────────────────────────────────────────────────────────────

class AgentBlackboard:
    """
    Gemeinsames Kurzzeit-Gedächtnis für alle Agenten.

    Agenten können Ergebnisse zu Topics publizieren und
    andere Agenten können diese lesen — mit TTL-basiertem Verfall.
    """

    def __init__(self, db_path: Path = MEMORY_DB_PATH):
        self.db_path = db_path
        _ensure_tables(db_path)

    # ------------------------------------------------------------------
    # Schreiben
    # ------------------------------------------------------------------

    def write(
        self,
        agent: str,
        topic: str,
        key: str,
        value: Any,
        ttl_minutes: int = DEFAULT_TTL_MIN,
        session_id: str = "",
    ) -> None:
        """
        Schreibt einen Eintrag in das Blackboard.

        Args:
            agent: Name des schreibenden Agenten
            topic: Themen-Kategorie (z.B. "research_results", "web_data")
            key: Eindeutiger Schlüssel innerhalb des Topics
            value: Beliebiger JSON-serialisierbarer Wert
            ttl_minutes: Gültigkeitsdauer in Minuten (default: 60)
            session_id: Optionale Session-ID
        """
        try:
            now = datetime.now()
            expires = now + timedelta(minutes=max(1, ttl_minutes))
            value_str = json.dumps(value, ensure_ascii=False) if not isinstance(value, str) else value

            with sqlite3.connect(str(self.db_path)) as conn:
                # Bestehenden Eintrag ersetzen (gleicher agent+topic+key)
                conn.execute(
                    """DELETE FROM agent_blackboard
                       WHERE agent = ? AND topic = ? AND key = ?""",
                    (agent, topic, key),
                )
                conn.execute(
                    """INSERT INTO agent_blackboard
                       (agent, topic, key, value, ttl_minutes, created_at, expires_at, session_id)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        agent,
                        topic,
                        key,
                        value_str,
                        ttl_minutes,
                        now.isoformat(),
                        expires.isoformat(),
                        session_id,
                    ),
                )
                conn.commit()
            log.debug("Blackboard.write: [%s:%s] %s", agent, topic, key)
        except Exception as e:
            log.warning("Blackboard.write fehlgeschlagen: %s", e)

    # ------------------------------------------------------------------
    # Lesen
    # ------------------------------------------------------------------

    def read(self, topic: str, key: str = "") -> List[dict]:
        """
        Liest Einträge für ein Topic (optional gefiltert nach Key).
        Gibt nur nicht-abgelaufene Einträge zurück.

        Args:
            topic: Das gesuchte Topic
            key: Optionaler Schlüssel-Filter (leer = alle Keys)

        Returns:
            Liste von Einträgen mit agent, topic, key, value, expires_at
        """
        try:
            now = datetime.now().isoformat()
            with sqlite3.connect(str(self.db_path)) as conn:
                if key:
                    rows = conn.execute(
                        """SELECT agent, topic, key, value, expires_at, created_at
                           FROM agent_blackboard
                           WHERE topic = ? AND key = ? AND expires_at > ?
                           ORDER BY created_at DESC""",
                        (topic, key, now),
                    ).fetchall()
                else:
                    rows = conn.execute(
                        """SELECT agent, topic, key, value, expires_at, created_at
                           FROM agent_blackboard
                           WHERE topic = ? AND expires_at > ?
                           ORDER BY created_at DESC""",
                        (topic, now),
                    ).fetchall()

                result = []
                for r in rows:
                    try:
                        val = json.loads(r[3])
                    except Exception:
                        val = r[3]
                    result.append({
                        "agent": r[0],
                        "topic": r[1],
                        "key": r[2],
                        "value": val,
                        "expires_at": r[4],
                        "created_at": r[5],
                    })
                return result
        except Exception as e:
            log.debug("Blackboard.read: %s", e)
            return []

    # ------------------------------------------------------------------
    # Suchen
    # ------------------------------------------------------------------

    def search(self, query: str, limit: int = 5) -> List[dict]:
        """
        Volltextsuche über Topic, Key und Value.

        Args:
            query: Suchbegriff
            limit: Maximale Ergebnisanzahl

        Returns:
            Liste von passenden Einträgen
        """
        try:
            now = datetime.now().isoformat()
            like = f"%{query}%"
            with sqlite3.connect(str(self.db_path)) as conn:
                rows = conn.execute(
                    """SELECT agent, topic, key, value, expires_at, created_at
                       FROM agent_blackboard
                       WHERE (topic LIKE ? OR key LIKE ? OR value LIKE ?)
                         AND expires_at > ?
                       ORDER BY created_at DESC
                       LIMIT ?""",
                    (like, like, like, now, limit),
                ).fetchall()

                result = []
                for r in rows:
                    try:
                        val = json.loads(r[3])
                    except Exception:
                        val = r[3]
                    result.append({
                        "agent": r[0],
                        "topic": r[1],
                        "key": r[2],
                        "value": val,
                        "expires_at": r[4],
                        "created_at": r[5],
                    })
                return result
        except Exception as e:
            log.debug("Blackboard.search: %s", e)
            return []

    # ------------------------------------------------------------------
    # Wartung
    # ------------------------------------------------------------------

    def clear_expired(self) -> int:
        """
        Löscht alle abgelaufenen Einträge.

        Returns:
            Anzahl der gelöschten Einträge
        """
        try:
            now = datetime.now().isoformat()
            with sqlite3.connect(str(self.db_path)) as conn:
                cursor = conn.execute(
                    "DELETE FROM agent_blackboard WHERE expires_at < ?",
                    (now,),
                )
                conn.commit()
                return cursor.rowcount
        except Exception as e:
            log.debug("Blackboard.clear_expired: %s", e)
            return 0

    def get_summary(self) -> dict:
        """
        Gibt eine Zusammenfassung des Blackboard-Inhalts zurück.

        Returns:
            Dict mit Einträgen pro Agent und Topic
        """
        try:
            now = datetime.now().isoformat()
            with sqlite3.connect(str(self.db_path)) as conn:
                total = conn.execute(
                    "SELECT COUNT(*) FROM agent_blackboard WHERE expires_at > ?",
                    (now,),
                ).fetchone()[0]

                by_agent = conn.execute(
                    """SELECT agent, COUNT(*) as cnt
                       FROM agent_blackboard WHERE expires_at > ?
                       GROUP BY agent ORDER BY cnt DESC""",
                    (now,),
                ).fetchall()

                by_topic = conn.execute(
                    """SELECT topic, COUNT(*) as cnt
                       FROM agent_blackboard WHERE expires_at > ?
                       GROUP BY topic ORDER BY cnt DESC""",
                    (now,),
                ).fetchall()

                last_entry = conn.execute(
                    """SELECT agent, topic, key, created_at
                       FROM agent_blackboard WHERE expires_at > ?
                       ORDER BY created_at DESC LIMIT 1""",
                    (now,),
                ).fetchone()

            return {
                "total_active": total,
                "by_agent": {r[0]: r[1] for r in by_agent},
                "by_topic": {r[0]: r[1] for r in by_topic},
                "last_entry": {
                    "agent": last_entry[0],
                    "topic": last_entry[1],
                    "key": last_entry[2],
                    "at": last_entry[3],
                } if last_entry else None,
            }
        except Exception as e:
            log.debug("Blackboard.get_summary: %s", e)
            return {"total_active": 0, "by_agent": {}, "by_topic": {}, "last_entry": None}
