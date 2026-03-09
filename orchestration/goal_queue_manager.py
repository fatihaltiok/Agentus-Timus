"""
orchestration/goal_queue_manager.py — M11: Goal Queue Manager

Nutzergesteuertes Ziel-Management über die bestehenden M1-Tabellen
(goals, goal_edges, goal_state in task_queue.db).

Feature-Flag: AUTONOMY_GOAL_QUEUE_ENABLED=true (sofort aktiv, bestehende Tabellen)
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

log = logging.getLogger("GoalQueueManager")

DB_PATH = Path(__file__).resolve().parents[1] / "data" / "task_queue.db"


class GoalQueueManager:
    """
    Nutzergesteuertes Ziel-Management über die bestehenden M1-Tabellen.

    Unterstützt Hierarchien (Parent-Goal → Sub-Goals), Meilensteine
    und Fortschritts-Rollup.
    """

    def __init__(self, db_path: Path = DB_PATH):
        self.db_path = db_path

    # ------------------------------------------------------------------
    # Ziele anlegen
    # ------------------------------------------------------------------

    def add_goal(
        self,
        title: str,
        description: str = "",
        parent_goal_id: Optional[str] = None,
        milestones: Optional[List[str]] = None,
    ) -> str:
        """
        Legt ein neues Ziel an.

        Args:
            title: Kurzer Titel des Ziels
            description: Detailbeschreibung
            parent_goal_id: ID des übergeordneten Ziels (None = Wurzel-Ziel)
            milestones: Optionale Liste von Meilensteinen

        Returns:
            Neue goal_id
        """
        goal_id = str(uuid.uuid4())
        now = datetime.now().isoformat()

        metrics = {}
        if milestones:
            metrics = {
                "milestones": milestones,
                "completed": [],
            }

        with sqlite3.connect(str(self.db_path)) as conn:
            conn.execute(
                """INSERT INTO goals
                   (id, title, description, source, priority_score, status, created_at, updated_at)
                   VALUES (?, ?, ?, 'user', 0.5, 'active', ?, ?)""",
                (goal_id, title, description, now, now),
            )

            # goal_state für Progress-Tracking
            conn.execute(
                """INSERT OR REPLACE INTO goal_state
                   (goal_id, progress, last_event, metrics_json, updated_at)
                   VALUES (?, 0.0, 'created', ?, ?)""",
                (goal_id, json.dumps(metrics, ensure_ascii=False), now),
            )

            # Parent-Child Edge falls parent gesetzt
            if parent_goal_id:
                conn.execute(
                    """INSERT OR IGNORE INTO goal_edges
                       (parent_goal_id, child_goal_id, edge_type, weight, created_at)
                       VALUES (?, ?, 'parent_child', 1.0, ?)""",
                    (parent_goal_id, goal_id, now),
                )

            conn.commit()

        log.info("Ziel angelegt: %s ('%s')", goal_id, title)
        return goal_id

    def add_subgoal(
        self,
        parent_id: str,
        title: str,
        description: str = "",
    ) -> str:
        """Legt ein Teilziel zu einem bestehenden Ziel an."""
        return self.add_goal(
            title=title,
            description=description,
            parent_goal_id=parent_id,
        )

    # ------------------------------------------------------------------
    # Meilensteine
    # ------------------------------------------------------------------

    def complete_milestone(self, goal_id: str, milestone_idx: int) -> float:
        """
        Markiert einen Meilenstein als erledigt.

        Args:
            goal_id: ID des Ziels
            milestone_idx: 0-basierter Index des Meilensteins

        Returns:
            Neuer Fortschritt (0.0–1.0)
        """
        try:
            with sqlite3.connect(str(self.db_path)) as conn:
                row = conn.execute(
                    "SELECT metrics_json, progress FROM goal_state WHERE goal_id = ?",
                    (goal_id,),
                ).fetchone()

                if not row:
                    log.warning("Ziel %s nicht gefunden", goal_id)
                    return 0.0

                metrics = json.loads(row[0] or "{}")
                milestones = metrics.get("milestones") or []
                if not isinstance(milestones, list):
                    milestones = []
                completed = metrics.get("completed") or []
                if not isinstance(completed, list):
                    completed = []

                if milestone_idx < 0 or milestone_idx >= len(milestones):
                    log.warning(
                        "Meilenstein-Index %d ungültig für Ziel %s (%d Meilensteine)",
                        milestone_idx,
                        goal_id,
                        len(milestones),
                    )
                    return float(row[1])

                if milestone_idx not in completed:
                    completed.append(milestone_idx)
                    metrics["completed"] = completed

                # Fortschritt berechnen
                progress = len(completed) / len(milestones) if milestones else 0.0

                now = datetime.now().isoformat()
                conn.execute(
                    """UPDATE goal_state
                       SET metrics_json = ?, progress = ?, last_event = ?, updated_at = ?
                       WHERE goal_id = ?""",
                    (
                        json.dumps(metrics, ensure_ascii=False),
                        progress,
                        f"milestone_{milestone_idx}_done",
                        now,
                        goal_id,
                    ),
                )

                # Status auf completed setzen wenn alle Meilensteine erledigt
                if progress >= 1.0:
                    conn.execute(
                        "UPDATE goals SET status = 'completed', updated_at = ? WHERE id = ?",
                        (now, goal_id),
                    )
                    log.info("🎯 Ziel %s vollständig abgeschlossen!", goal_id)

                conn.commit()

            # Rollup zu Parent-Ziel
            parent_id = self._get_parent_id(goal_id)
            if parent_id:
                self._rollup_progress(parent_id)

            # Telegram-Push bei Abschluss
            if progress >= 1.0:
                self._notify_goal_completed(goal_id)

            return progress

        except Exception as e:
            log.warning("complete_milestone: %s", e)
            return 0.0

    # ------------------------------------------------------------------
    # Abfragen
    # ------------------------------------------------------------------

    def get_goal_tree(self, root_id: Optional[str] = None) -> List[dict]:
        """
        Gibt den Ziel-Baum zurück (für Cytoscape hierarchical layout).

        Args:
            root_id: Wurzel-Ziel-ID (None = alle Wurzel-Ziele)

        Returns:
            Cytoscape-kompatibler Knoten/Kanten-Baum
        """
        try:
            with sqlite3.connect(str(self.db_path)) as conn:
                # Alle aktiven Ziele
                if root_id:
                    # Ziel + alle Nachkommen via goal_edges
                    goal_ids = self._get_descendant_ids(conn, root_id)
                    goal_ids.add(root_id)
                    goal_rows = conn.execute(
                        """SELECT g.id, g.title, g.description, g.status, g.priority_score,
                                   gs.progress, gs.metrics_json
                            FROM goals g
                            LEFT JOIN goal_state gs ON g.id = gs.goal_id
                            WHERE g.id IN (SELECT value FROM json_each(?)) AND g.status != 'cancelled'""",
                        (json.dumps(sorted(goal_ids)),),
                    ).fetchall()
                else:
                    goal_rows = conn.execute(
                        """SELECT g.id, g.title, g.description, g.status, g.priority_score,
                                  gs.progress, gs.metrics_json
                           FROM goals g
                           LEFT JOIN goal_state gs ON g.id = gs.goal_id
                           WHERE g.status != 'cancelled'
                           ORDER BY g.priority_score DESC, g.created_at DESC
                           LIMIT 50"""
                    ).fetchall()

                # Edges
                edge_rows = conn.execute(
                    "SELECT parent_goal_id, child_goal_id FROM goal_edges WHERE edge_type = 'parent_child'"
                ).fetchall()

            nodes = []
            for r in goal_rows:
                metrics = {}
                try:
                    metrics = json.loads(r[6] or "{}")
                except Exception:
                    pass
                nodes.append({
                    "data": {
                        "id": r[0],
                        "label": r[1],
                        "description": r[2] or "",
                        "status": r[3],
                        "priority": r[4],
                        "progress": round(float(r[5] or 0.0), 2),
                        "milestones": metrics.get("milestones", []),
                        "completed_milestones": metrics.get("completed", []),
                    }
                })

            edges = [
                {
                    "data": {
                        "id": f"e_{r[0]}_{r[1]}",
                        "source": r[0],
                        "target": r[1],
                    }
                }
                for r in edge_rows
            ]

            return nodes + edges

        except Exception as e:
            log.debug("get_goal_tree: %s", e)
            return []

    def get_goal_progress(self, goal_id: str) -> dict:
        """Gibt Fortschritt und Details eines Ziels zurück."""
        try:
            with sqlite3.connect(str(self.db_path)) as conn:
                row = conn.execute(
                    """SELECT g.id, g.title, g.status, gs.progress, gs.metrics_json,
                              gs.last_event, gs.updated_at
                       FROM goals g
                       LEFT JOIN goal_state gs ON g.id = gs.goal_id
                       WHERE g.id = ?""",
                    (goal_id,),
                ).fetchone()

                if not row:
                    return {"status": "not_found", "goal_id": goal_id}

                metrics = {}
                try:
                    metrics = json.loads(row[4] or "{}")
                except Exception:
                    pass

                return {
                    "goal_id": row[0],
                    "title": row[1],
                    "status": row[2],
                    "progress": round(float(row[3] or 0.0), 2),
                    "milestones": metrics.get("milestones", []),
                    "completed_milestones": metrics.get("completed", []),
                    "last_event": row[5],
                    "updated_at": row[6],
                }
        except Exception as e:
            log.debug("get_goal_progress: %s", e)
            return {"status": "error", "error": str(e)}

    # ------------------------------------------------------------------
    # Task-Verknüpfung
    # ------------------------------------------------------------------

    def link_task(self, task_id: str, goal_id: str) -> None:
        """Verknüpft einen Task mit einem Ziel."""
        try:
            with sqlite3.connect(str(self.db_path)) as conn:
                conn.execute(
                    "UPDATE tasks SET goal_id = ? WHERE id = ?",
                    (goal_id, task_id),
                )
                conn.commit()
        except Exception as e:
            log.debug("link_task: %s", e)

    # ------------------------------------------------------------------
    # Fortschritts-Rollup
    # ------------------------------------------------------------------

    def _rollup_progress(self, goal_id: str) -> None:
        """Rollup: Ø-Fortschritt aller Child-Goals → Parent aktualisieren."""
        try:
            with sqlite3.connect(str(self.db_path)) as conn:
                children = conn.execute(
                    """SELECT gs.progress FROM goal_edges ge
                       JOIN goal_state gs ON ge.child_goal_id = gs.goal_id
                       WHERE ge.parent_goal_id = ? AND ge.edge_type = 'parent_child'""",
                    (goal_id,),
                ).fetchall()

                if not children:
                    return

                avg_progress = sum(r[0] or 0.0 for r in children) / len(children)
                now = datetime.now().isoformat()

                conn.execute(
                    """UPDATE goal_state
                       SET progress = ?, last_event = 'child_rollup', updated_at = ?
                       WHERE goal_id = ?""",
                    (avg_progress, now, goal_id),
                )
                conn.commit()

        except Exception as e:
            log.debug("_rollup_progress: %s", e)

    def run_progress_cycle(self) -> None:
        """Rollup für alle ACTIVE Ziele mit Kindern — im Heartbeat aufrufen."""
        try:
            with sqlite3.connect(str(self.db_path)) as conn:
                parent_ids = conn.execute(
                    """SELECT DISTINCT parent_goal_id FROM goal_edges
                       WHERE edge_type = 'parent_child'"""
                ).fetchall()

            for (pid,) in parent_ids:
                self._rollup_progress(pid)

        except Exception as e:
            log.debug("run_progress_cycle: %s", e)

    # ------------------------------------------------------------------
    # Hilfsmethoden
    # ------------------------------------------------------------------

    def _get_parent_id(self, goal_id: str) -> Optional[str]:
        """Gibt Parent-Goal-ID zurück (None wenn kein Parent)."""
        try:
            with sqlite3.connect(str(self.db_path)) as conn:
                row = conn.execute(
                    """SELECT parent_goal_id FROM goal_edges
                       WHERE child_goal_id = ? AND edge_type = 'parent_child' LIMIT 1""",
                    (goal_id,),
                ).fetchone()
                return row[0] if row else None
        except Exception:
            return None

    def _get_descendant_ids(self, conn: sqlite3.Connection, root_id: str) -> set:
        """Rekursive Abfrage aller Nachkommen-IDs."""
        result = set()
        queue = [root_id]
        visited = set()
        while queue:
            current = queue.pop(0)
            if current in visited:
                continue
            visited.add(current)
            children = conn.execute(
                "SELECT child_goal_id FROM goal_edges WHERE parent_goal_id = ?",
                (current,),
            ).fetchall()
            for (child_id,) in children:
                result.add(child_id)
                queue.append(child_id)
        return result

    def _notify_goal_completed(self, goal_id: str) -> None:
        """Telegram-Push bei Ziel-Abschluss."""
        try:
            import asyncio
            from utils.telegram_notify import send_telegram

            with sqlite3.connect(str(self.db_path)) as conn:
                row = conn.execute(
                    "SELECT title FROM goals WHERE id = ?", (goal_id,)
                ).fetchone()
            title = row[0] if row else goal_id

            msg = f"🎯 *Ziel abgeschlossen!*\n{title}"

            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    asyncio.ensure_future(send_telegram(msg))
                else:
                    loop.run_until_complete(send_telegram(msg))
            except RuntimeError:
                pass  # Kein Event-Loop verfügbar
        except Exception:
            pass


# ──────────────────────────────────────────────────────────────────
# Singleton
# ──────────────────────────────────────────────────────────────────

_manager_instance: Optional[GoalQueueManager] = None


def get_goal_manager(db_path: Path = DB_PATH) -> GoalQueueManager:
    global _manager_instance
    if _manager_instance is None:
        _manager_instance = GoalQueueManager(db_path)
    return _manager_instance
