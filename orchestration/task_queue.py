"""
orchestration/task_queue.py

Persistente SQLite-Task-Queue für Timus.
Ersetzt tasks.json mit echtem Priority-System und atomaren Operationen.

Prioritäten:  CRITICAL(0) > HIGH(1) > NORMAL(2) > LOW(3)
Task-Typen:   manual | scheduled | triggered | delegated
Status:       pending → in_progress → completed | failed | cancelled
"""

import logging
import os
import json
import math
import re
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta
from enum import IntEnum
from itertools import combinations
from pathlib import Path
from typing import Any, Dict, Generator, List, Optional, Set

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


class GoalStatus:
    ACTIVE = "active"
    BLOCKED = "blocked"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class PlanHorizon:
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"


class PlanStatus:
    ACTIVE = "active"
    ARCHIVED = "archived"


class PlanItemStatus:
    PLANNED = "planned"
    IN_PROGRESS = "in_progress"
    DONE = "done"
    CANCELLED = "cancelled"


class CommitmentStatus:
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    BLOCKED = "blocked"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ReplanTrigger:
    DEADLINE_TIMEOUT = "deadline_timeout"
    PARTIAL_STAGNATION = "partial_stagnation"
    GOAL_DRIFT = "goal_drift"
    GOAL_CONFLICT = "goal_conflict"


class ReplanEventStatus:
    DETECTED = "detected"
    APPLIED = "applied"
    IGNORED = "ignored"
    FAILED = "failed"


class CommitmentReviewStatus:
    SCHEDULED = "scheduled"
    COMPLETED = "completed"
    ESCALATED = "escalated"
    SKIPPED = "skipped"


class SelfHealingIncidentStatus:
    OPEN = "open"
    RECOVERED = "recovered"
    IGNORED = "ignored"
    FAILED = "failed"


class SelfHealingCircuitBreakerState:
    CLOSED = "closed"
    OPEN = "open"


class SelfHealingDegradeMode:
    NORMAL = "normal"
    DEGRADED = "degraded"
    EMERGENCY = "emergency"


GOAL_STATUS_VALUES = {
    GoalStatus.ACTIVE,
    GoalStatus.BLOCKED,
    GoalStatus.COMPLETED,
    GoalStatus.CANCELLED,
}


GOAL_ALLOWED_TRANSITIONS = {
    GoalStatus.ACTIVE: {GoalStatus.BLOCKED, GoalStatus.COMPLETED, GoalStatus.CANCELLED},
    GoalStatus.BLOCKED: {GoalStatus.ACTIVE, GoalStatus.COMPLETED, GoalStatus.CANCELLED},
    GoalStatus.COMPLETED: set(),
    GoalStatus.CANCELLED: set(),
}


_CONFLICT_ANTONYM_PAIRS = [
    ("enable", "disable"),
    ("aktivieren", "deaktivieren"),
    ("start", "stop"),
    ("starten", "stoppen"),
    ("increase", "decrease"),
    ("erhoehen", "senken"),
    ("steigern", "reduzieren"),
    ("allow", "deny"),
    ("erlauben", "verbieten"),
    ("include", "exclude"),
    ("einschliessen", "ausschliessen"),
    ("mehr", "weniger"),
    ("maximieren", "minimieren"),
]


_NEGATION_TOKENS = {"nicht", "kein", "keine", "ohne", "no", "not", "never"}

PLAN_HORIZON_VALUES = {PlanHorizon.DAILY, PlanHorizon.WEEKLY, PlanHorizon.MONTHLY}
PLAN_STATUS_VALUES = {PlanStatus.ACTIVE, PlanStatus.ARCHIVED}
PLAN_ITEM_STATUS_VALUES = {
    PlanItemStatus.PLANNED,
    PlanItemStatus.IN_PROGRESS,
    PlanItemStatus.DONE,
    PlanItemStatus.CANCELLED,
}
COMMITMENT_STATUS_VALUES = {
    CommitmentStatus.PENDING,
    CommitmentStatus.IN_PROGRESS,
    CommitmentStatus.COMPLETED,
    CommitmentStatus.BLOCKED,
    CommitmentStatus.FAILED,
    CommitmentStatus.CANCELLED,
}
REPLAN_TRIGGER_VALUES = {
    ReplanTrigger.DEADLINE_TIMEOUT,
    ReplanTrigger.PARTIAL_STAGNATION,
    ReplanTrigger.GOAL_DRIFT,
    ReplanTrigger.GOAL_CONFLICT,
}
REPLAN_EVENT_STATUS_VALUES = {
    ReplanEventStatus.DETECTED,
    ReplanEventStatus.APPLIED,
    ReplanEventStatus.IGNORED,
    ReplanEventStatus.FAILED,
}
COMMITMENT_REVIEW_STATUS_VALUES = {
    CommitmentReviewStatus.SCHEDULED,
    CommitmentReviewStatus.COMPLETED,
    CommitmentReviewStatus.ESCALATED,
    CommitmentReviewStatus.SKIPPED,
}
SELF_HEALING_INCIDENT_STATUS_VALUES = {
    SelfHealingIncidentStatus.OPEN,
    SelfHealingIncidentStatus.RECOVERED,
    SelfHealingIncidentStatus.IGNORED,
    SelfHealingIncidentStatus.FAILED,
}
SELF_HEALING_CIRCUIT_BREAKER_STATE_VALUES = {
    SelfHealingCircuitBreakerState.CLOSED,
    SelfHealingCircuitBreakerState.OPEN,
}
SELF_HEALING_DEGRADE_MODE_VALUES = {
    SelfHealingDegradeMode.NORMAL,
    SelfHealingDegradeMode.DEGRADED,
    SelfHealingDegradeMode.EMERGENCY,
}


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name, "true" if default else "false").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def _goals_feature_enabled() -> bool:
    if _env_bool("AUTONOMY_COMPAT_MODE", True):
        return False
    return _env_bool("AUTONOMY_GOALS_ENABLED", False)


def _planning_feature_enabled() -> bool:
    if _env_bool("AUTONOMY_COMPAT_MODE", True):
        return False
    return _env_bool("AUTONOMY_PLANNING_ENABLED", False)


def _replanning_feature_enabled() -> bool:
    if _env_bool("AUTONOMY_COMPAT_MODE", True):
        return False
    return _env_bool("AUTONOMY_REPLANNING_ENABLED", False)


def _normalize_umlauts(text: str) -> str:
    return (
        text.replace("ä", "ae")
        .replace("ö", "oe")
        .replace("ü", "ue")
        .replace("ß", "ss")
    )


def _normalize_goal_status(status: str) -> str:
    raw = (status or "").strip().lower()
    return raw if raw in GOAL_STATUS_VALUES else GoalStatus.ACTIVE


def _is_goal_transition_allowed(current: str, target: str) -> bool:
    current_norm = _normalize_goal_status(current)
    target_norm = _normalize_goal_status(target)
    if current_norm == target_norm:
        return True
    return target_norm in GOAL_ALLOWED_TRANSITIONS.get(current_norm, set())


def _goal_tokens(text: str) -> Set[str]:
    normalized = _normalize_umlauts((text or "").lower())
    tokens = set(re.findall(r"[a-z0-9]{3,}", normalized))
    return {tok for tok in tokens if not tok.isdigit()}


def _normalize_plan_horizon(horizon: str) -> str:
    raw = (horizon or "").strip().lower()
    return raw if raw in PLAN_HORIZON_VALUES else PlanHorizon.DAILY


def _normalize_plan_status(status: str) -> str:
    raw = (status or "").strip().lower()
    return raw if raw in PLAN_STATUS_VALUES else PlanStatus.ACTIVE


def _normalize_plan_item_status(status: str) -> str:
    raw = (status or "").strip().lower()
    return raw if raw in PLAN_ITEM_STATUS_VALUES else PlanItemStatus.PLANNED


def _normalize_commitment_status(status: str) -> str:
    raw = (status or "").strip().lower()
    return raw if raw in COMMITMENT_STATUS_VALUES else CommitmentStatus.PENDING


def _normalize_replan_trigger(trigger: str) -> str:
    raw = (trigger or "").strip().lower()
    return raw if raw in REPLAN_TRIGGER_VALUES else ReplanTrigger.GOAL_DRIFT


def _normalize_replan_event_status(status: str) -> str:
    raw = (status or "").strip().lower()
    return raw if raw in REPLAN_EVENT_STATUS_VALUES else ReplanEventStatus.DETECTED


def _normalize_commitment_review_status(status: str) -> str:
    raw = (status or "").strip().lower()
    return raw if raw in COMMITMENT_REVIEW_STATUS_VALUES else CommitmentReviewStatus.SCHEDULED


def _normalize_self_healing_incident_status(status: str) -> str:
    raw = (status or "").strip().lower()
    return raw if raw in SELF_HEALING_INCIDENT_STATUS_VALUES else SelfHealingIncidentStatus.OPEN


def _normalize_self_healing_circuit_breaker_state(state: str) -> str:
    raw = (state or "").strip().lower()
    return raw if raw in SELF_HEALING_CIRCUIT_BREAKER_STATE_VALUES else SelfHealingCircuitBreakerState.CLOSED


def _normalize_self_healing_degrade_mode(mode: str) -> str:
    raw = (mode or "").strip().lower()
    return raw if raw in SELF_HEALING_DEGRADE_MODE_VALUES else SelfHealingDegradeMode.NORMAL


def _parse_iso_datetime(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
        if parsed.tzinfo is not None:
            return parsed.astimezone().replace(tzinfo=None)
        return parsed
    except Exception:
        return None


def _review_interval_for_horizon(horizon: str) -> timedelta:
    norm = _normalize_plan_horizon(horizon)
    if norm == PlanHorizon.DAILY:
        return timedelta(hours=6)
    if norm == PlanHorizon.WEEKLY:
        return timedelta(hours=24)
    return timedelta(hours=72)


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
    goal_id      TEXT,
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

CREATE INDEX IF NOT EXISTS idx_tasks_goal_id
    ON tasks (goal_id, status);

CREATE TABLE IF NOT EXISTS goals (
    id             TEXT PRIMARY KEY,
    title          TEXT NOT NULL,
    description    TEXT,
    source         TEXT NOT NULL DEFAULT 'manual',
    priority_score REAL NOT NULL DEFAULT 0.0,
    status         TEXT NOT NULL DEFAULT 'active',
    created_at     TEXT NOT NULL,
    updated_at     TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_goals_status_priority
    ON goals (status, priority_score DESC, created_at DESC);

CREATE TABLE IF NOT EXISTS goal_edges (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    parent_goal_id TEXT NOT NULL,
    child_goal_id  TEXT NOT NULL,
    edge_type      TEXT NOT NULL DEFAULT 'parent_child',
    weight         REAL NOT NULL DEFAULT 1.0,
    created_at     TEXT NOT NULL,
    UNIQUE(parent_goal_id, child_goal_id, edge_type)
);

CREATE INDEX IF NOT EXISTS idx_goal_edges_parent
    ON goal_edges (parent_goal_id, edge_type);

CREATE INDEX IF NOT EXISTS idx_goal_edges_child
    ON goal_edges (child_goal_id, edge_type);

CREATE TABLE IF NOT EXISTS goal_state (
    goal_id       TEXT PRIMARY KEY,
    progress      REAL NOT NULL DEFAULT 0.0,
    last_task_id  TEXT,
    last_event    TEXT,
    metrics_json  TEXT,
    updated_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS plans (
    id           TEXT PRIMARY KEY,
    horizon      TEXT NOT NULL,
    window_start TEXT NOT NULL,
    window_end   TEXT NOT NULL,
    status       TEXT NOT NULL DEFAULT 'active',
    source       TEXT NOT NULL DEFAULT 'autonomy_planner',
    metadata     TEXT,
    created_at   TEXT NOT NULL,
    updated_at   TEXT NOT NULL,
    UNIQUE(horizon, window_start, window_end)
);

CREATE INDEX IF NOT EXISTS idx_plans_horizon_status
    ON plans (horizon, status, window_start DESC);

CREATE TABLE IF NOT EXISTS plan_items (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    plan_id        TEXT NOT NULL,
    goal_id        TEXT,
    title          TEXT NOT NULL,
    owner_agent    TEXT,
    deadline       TEXT,
    success_metric TEXT,
    priority_score REAL NOT NULL DEFAULT 0.0,
    status         TEXT NOT NULL DEFAULT 'planned',
    created_at     TEXT NOT NULL,
    updated_at     TEXT NOT NULL,
    UNIQUE(plan_id, goal_id, title)
);

CREATE INDEX IF NOT EXISTS idx_plan_items_plan_status
    ON plan_items (plan_id, status, priority_score DESC);

CREATE TABLE IF NOT EXISTS commitments (
    id             TEXT PRIMARY KEY,
    plan_id        TEXT,
    goal_id        TEXT,
    title          TEXT NOT NULL,
    owner_agent    TEXT NOT NULL DEFAULT 'meta',
    deadline       TEXT NOT NULL,
    success_metric TEXT NOT NULL,
    status         TEXT NOT NULL DEFAULT 'pending',
    progress       REAL NOT NULL DEFAULT 0.0,
    metadata       TEXT,
    created_at     TEXT NOT NULL,
    updated_at     TEXT NOT NULL,
    UNIQUE(plan_id, goal_id, title, deadline)
);

CREATE INDEX IF NOT EXISTS idx_commitments_status_deadline
    ON commitments (status, deadline);

CREATE TABLE IF NOT EXISTS replan_events (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    event_key     TEXT NOT NULL UNIQUE,
    commitment_id TEXT NOT NULL,
    goal_id       TEXT,
    trigger_type  TEXT NOT NULL,
    severity      TEXT NOT NULL DEFAULT 'medium',
    status        TEXT NOT NULL DEFAULT 'detected',
    action        TEXT,
    details       TEXT,
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_replan_events_status_trigger
    ON replan_events (status, trigger_type, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_replan_events_commitment
    ON replan_events (commitment_id, created_at DESC);

CREATE TABLE IF NOT EXISTS commitment_reviews (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    commitment_id     TEXT NOT NULL,
    plan_id           TEXT,
    goal_id           TEXT,
    horizon           TEXT,
    review_due_at     TEXT NOT NULL,
    reviewed_at       TEXT,
    review_type       TEXT NOT NULL DEFAULT 'checkpoint',
    status            TEXT NOT NULL DEFAULT 'scheduled',
    expected_progress REAL,
    observed_progress REAL,
    progress_gap      REAL,
    risk_level        TEXT NOT NULL DEFAULT 'low',
    notes             TEXT,
    metadata          TEXT,
    created_at        TEXT NOT NULL,
    updated_at        TEXT NOT NULL,
    UNIQUE(commitment_id, review_due_at, review_type)
);

CREATE INDEX IF NOT EXISTS idx_commitment_reviews_status_due
    ON commitment_reviews (status, review_due_at);

CREATE INDEX IF NOT EXISTS idx_commitment_reviews_commitment
    ON commitment_reviews (commitment_id, review_due_at DESC);

CREATE TABLE IF NOT EXISTS self_healing_incidents (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    incident_key     TEXT NOT NULL UNIQUE,
    component        TEXT NOT NULL,
    signal           TEXT NOT NULL,
    severity         TEXT NOT NULL DEFAULT 'medium',
    status           TEXT NOT NULL DEFAULT 'open',
    title            TEXT,
    details          TEXT,
    recovery_action  TEXT,
    recovery_status  TEXT,
    first_seen_at    TEXT NOT NULL,
    last_seen_at     TEXT NOT NULL,
    recovered_at     TEXT,
    created_at       TEXT NOT NULL,
    updated_at       TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_self_healing_status_component
    ON self_healing_incidents (status, component, last_seen_at DESC);

CREATE INDEX IF NOT EXISTS idx_self_healing_signal
    ON self_healing_incidents (signal, status);

CREATE TABLE IF NOT EXISTS self_healing_circuit_breakers (
    breaker_key       TEXT PRIMARY KEY,
    component         TEXT NOT NULL,
    signal            TEXT NOT NULL,
    state             TEXT NOT NULL DEFAULT 'closed',
    failure_streak    INTEGER NOT NULL DEFAULT 0,
    trip_count        INTEGER NOT NULL DEFAULT 0,
    cooldown_seconds  INTEGER NOT NULL DEFAULT 600,
    opened_until      TEXT,
    last_failure_at   TEXT,
    last_success_at   TEXT,
    metadata          TEXT,
    created_at        TEXT NOT NULL,
    updated_at        TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_self_healing_cb_state
    ON self_healing_circuit_breakers (state, component, updated_at DESC);

CREATE TABLE IF NOT EXISTS self_healing_runtime_state (
    state_key   TEXT PRIMARY KEY,
    state_value TEXT NOT NULL,
    metadata    TEXT,
    updated_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS policy_decisions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    gate            TEXT NOT NULL,
    source          TEXT,
    subject         TEXT,
    action          TEXT NOT NULL,
    blocked         INTEGER NOT NULL DEFAULT 0,
    strict_mode     INTEGER NOT NULL DEFAULT 0,
    reason          TEXT,
    violations      TEXT,
    payload         TEXT,
    canary_percent  INTEGER NOT NULL DEFAULT 0,
    canary_bucket   INTEGER,
    canary_enforced INTEGER NOT NULL DEFAULT 1,
    created_at      TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_policy_decisions_created
    ON policy_decisions (created_at DESC);

CREATE INDEX IF NOT EXISTS idx_policy_decisions_gate
    ON policy_decisions (gate, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_policy_decisions_blocked
    ON policy_decisions (blocked, created_at DESC);

CREATE TABLE IF NOT EXISTS policy_runtime_state (
    state_key   TEXT PRIMARY KEY,
    state_value TEXT NOT NULL,
    metadata    TEXT,
    updated_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS autonomy_scorecard_snapshots (
    id                        INTEGER PRIMARY KEY AUTOINCREMENT,
    overall_score             REAL NOT NULL,
    overall_score_10          REAL NOT NULL,
    autonomy_level            TEXT NOT NULL,
    ready_for_very_high       INTEGER NOT NULL DEFAULT 0,
    window_hours              INTEGER NOT NULL DEFAULT 24,
    pillars                   TEXT,
    control_state             TEXT,
    created_at                TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_scorecard_snapshots_created
    ON autonomy_scorecard_snapshots (created_at DESC);

CREATE INDEX IF NOT EXISTS idx_scorecard_snapshots_score
    ON autonomy_scorecard_snapshots (overall_score, created_at DESC);

CREATE TABLE IF NOT EXISTS autonomy_change_requests (
    id              TEXT PRIMARY KEY,
    audit_id        TEXT NOT NULL UNIQUE,
    source          TEXT NOT NULL,
    recommendation  TEXT NOT NULL,
    status          TEXT NOT NULL,
    action          TEXT,
    reason          TEXT,
    report_path     TEXT,
    payload         TEXT,
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL,
    applied_at      TEXT
);

CREATE INDEX IF NOT EXISTS idx_change_requests_status
    ON autonomy_change_requests (status, updated_at DESC);

CREATE INDEX IF NOT EXISTS idx_change_requests_created
    ON autonomy_change_requests (created_at DESC);

-- ── M10: Proaktive Trigger ──────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS proactive_triggers (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    time_of_day TEXT NOT NULL,
    days_of_week TEXT DEFAULT '[]',
    action_query TEXT NOT NULL,
    target_agent TEXT DEFAULT 'meta',
    enabled INTEGER DEFAULT 1,
    last_fired_at TEXT DEFAULT ''
);

-- ── M12: Tool-Analytics ─────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS tool_analytics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tool_name TEXT NOT NULL,
    agent TEXT NOT NULL,
    task_type TEXT DEFAULT '',
    success INTEGER NOT NULL DEFAULT 1,
    duration_ms INTEGER DEFAULT 0,
    timestamp TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_tool_analytics_agent
    ON tool_analytics (agent, timestamp DESC);

-- ── M12: Routing-Analytics ──────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS routing_analytics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_hash TEXT NOT NULL,
    chosen_agent TEXT NOT NULL,
    outcome TEXT NOT NULL DEFAULT 'success',
    confidence REAL DEFAULT 0.5,
    timestamp TEXT NOT NULL
);

-- ── M12: Improvement-Suggestions ────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS improvement_suggestions_m12 (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    type TEXT NOT NULL,
    target TEXT NOT NULL,
    finding TEXT NOT NULL,
    suggestion TEXT NOT NULL,
    confidence REAL DEFAULT 0.5,
    severity TEXT DEFAULT 'medium',
    applied INTEGER DEFAULT 0,
    created_at TEXT NOT NULL
);
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
            # Migration VOR executescript: fehlende Spalten zuerst hinzufügen,
            # damit idx_tasks_goal_id im SCHEMA nicht wegen fehlender Spalte scheitert.
            existing_cols = {row[1] for row in conn.execute("PRAGMA table_info(tasks)")}
            for col, definition in [("run_at", "TEXT"), ("goal_id", "TEXT")]:
                if existing_cols and col not in existing_cols:
                    conn.execute(f"ALTER TABLE tasks ADD COLUMN {col} {definition}")
                    log.info(f"Migration: Spalte '{col}' hinzugefügt")
            conn.executescript(SCHEMA)
        log.info(f"TaskQueue initialisiert: {self.db_path}")

    # ------------------------------------------------------------------
    # Goal-Graph (M1)
    # ------------------------------------------------------------------

    def create_goal(
        self,
        title: str,
        description: Optional[str] = None,
        source: str = "manual",
        priority_score: float = 0.0,
        status: str = GoalStatus.ACTIVE,
        goal_id: Optional[str] = None,
    ) -> str:
        clean_title = (title or "").strip()
        if not clean_title:
            raise ValueError("Goal title darf nicht leer sein")
        status = _normalize_goal_status(status)

        new_goal_id = goal_id or str(uuid.uuid4())
        now = datetime.now().isoformat()
        with self._conn() as conn:
            conn.execute(
                """INSERT INTO goals
                   (id, title, description, source, priority_score, status, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(id) DO UPDATE SET
                       title=excluded.title,
                       description=excluded.description,
                       source=excluded.source,
                       priority_score=excluded.priority_score,
                       status=excluded.status,
                       updated_at=excluded.updated_at""",
                (
                    new_goal_id,
                    clean_title,
                    (description or "").strip() or None,
                    source,
                    float(priority_score),
                    status,
                    now,
                    now,
                ),
            )
            conn.execute(
                """INSERT INTO goal_state (goal_id, progress, updated_at)
                   VALUES (?, 0.0, ?)
                   ON CONFLICT(goal_id) DO NOTHING""",
                (new_goal_id, now),
            )
        return new_goal_id

    def link_goals(
        self,
        parent_goal_id: str,
        child_goal_id: str,
        edge_type: str = "parent_child",
        weight: float = 1.0,
    ) -> None:
        if not parent_goal_id or not child_goal_id:
            raise ValueError("parent_goal_id und child_goal_id sind Pflicht")
        if parent_goal_id == child_goal_id:
            raise ValueError("Ein Goal kann nicht auf sich selbst zeigen")
        now = datetime.now().isoformat()
        with self._conn() as conn:
            conn.execute(
                """INSERT OR IGNORE INTO goal_edges
                   (parent_goal_id, child_goal_id, edge_type, weight, created_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (parent_goal_id, child_goal_id, edge_type, float(weight), now),
            )

    def get_goal(self, goal_id: str) -> Optional[dict]:
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM goals WHERE id=?", (goal_id,)).fetchone()
            return dict(row) if row else None

    def get_goal_state(self, goal_id: str) -> Optional[dict]:
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM goal_state WHERE goal_id=?", (goal_id,)).fetchone()
            if not row:
                return None
            payload = dict(row)
            raw_metrics = payload.get("metrics_json")
            if raw_metrics:
                try:
                    payload["metrics"] = json.loads(raw_metrics)
                except Exception:
                    payload["metrics"] = {}
            else:
                payload["metrics"] = {}
            return payload

    def list_goals(self, status: Optional[str] = None, limit: int = 50) -> List[dict]:
        with self._conn() as conn:
            if status:
                rows = conn.execute(
                    """SELECT * FROM goals
                       WHERE status=?
                       ORDER BY priority_score DESC, created_at DESC
                       LIMIT ?""",
                    (status, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    """SELECT * FROM goals
                       ORDER BY priority_score DESC, created_at DESC
                       LIMIT ?""",
                    (limit,),
                ).fetchall()
            return [dict(r) for r in rows]

    def upsert_goal_from_signal(
        self,
        title: str,
        *,
        source: str = "signal",
        description: Optional[str] = None,
        priority_score: float = 0.5,
        status: str = GoalStatus.ACTIVE,
    ) -> str:
        clean_title = (title or "").strip()
        if not clean_title:
            raise ValueError("Goal title darf nicht leer sein")
        status = _normalize_goal_status(status)

        now = datetime.now().isoformat()
        existing_goal_id: Optional[str] = None
        with self._conn() as conn:
            existing = conn.execute(
                """SELECT id, priority_score, description
                   FROM goals
                   WHERE status IN (?, ?) AND title=?
                   ORDER BY updated_at DESC
                   LIMIT 1""",
                (GoalStatus.ACTIVE, GoalStatus.BLOCKED, clean_title),
            ).fetchone()

            if existing:
                goal_id = str(existing["id"])
                existing_goal_id = goal_id
                new_priority = max(float(existing["priority_score"] or 0.0), float(priority_score))
                merged_description = existing["description"] or ((description or "").strip() or None)
                conn.execute(
                    """UPDATE goals
                       SET priority_score=?, updated_at=?, description=?
                       WHERE id=?""",
                    (new_priority, now, merged_description, goal_id),
                )
                conn.execute(
                    """INSERT INTO goal_state (goal_id, progress, updated_at)
                       VALUES (?, 0.0, ?)
                       ON CONFLICT(goal_id) DO NOTHING""",
                    (goal_id, now),
                )
        if existing_goal_id:
            self.transition_goal_status(existing_goal_id, status, reason="signal_upsert")
            return existing_goal_id

        return self.create_goal(
            title=clean_title,
            description=description,
            source=source,
            priority_score=priority_score,
            status=status,
        )

    def assign_task_goal(
        self,
        task_id: str,
        goal_id: str,
        *,
        refresh_progress: bool = True,
    ) -> bool:
        if not task_id or not goal_id:
            return False

        old_goal: Optional[str] = None
        with self._conn() as conn:
            row = conn.execute("SELECT goal_id FROM tasks WHERE id=?", (task_id,)).fetchone()
            if not row:
                return False
            old_goal = row["goal_id"]
            conn.execute("UPDATE tasks SET goal_id=? WHERE id=?", (goal_id, task_id))

        if refresh_progress:
            if old_goal and old_goal != goal_id:
                self.refresh_goal_progress(old_goal, last_task_id=task_id, last_event="task_goal_reassigned")
            self.refresh_goal_progress(goal_id, last_task_id=task_id, last_event="task_goal_assigned")
        return True

    def get_unassigned_triggered_tasks(self, limit: int = 20) -> List[dict]:
        with self._conn() as conn:
            rows = conn.execute(
                """SELECT * FROM tasks
                   WHERE task_type=?
                     AND status IN (?, ?)
                     AND (goal_id IS NULL OR goal_id='')
                   ORDER BY created_at DESC
                   LIMIT ?""",
                (TaskType.TRIGGERED, TaskStatus.PENDING, TaskStatus.IN_PROGRESS, limit),
            ).fetchall()
            return [dict(r) for r in rows]

    def transition_goal_status(
        self,
        goal_id: str,
        target_status: str,
        *,
        reason: str = "",
    ) -> bool:
        if not goal_id:
            return False
        target = _normalize_goal_status(target_status)
        now = datetime.now().isoformat()

        with self._conn() as conn:
            row = conn.execute("SELECT status FROM goals WHERE id=?", (goal_id,)).fetchone()
            if not row:
                return False
            current = _normalize_goal_status(str(row["status"] or ""))
            if not _is_goal_transition_allowed(current, target):
                log.warning(
                    "Goal-Transition abgelehnt [%s]: %s -> %s",
                    goal_id[:8],
                    current,
                    target,
                )
                return False

            if current != target:
                conn.execute(
                    "UPDATE goals SET status=?, updated_at=? WHERE id=?",
                    (target, now, goal_id),
                )

            conn.execute(
                """INSERT INTO goal_state (goal_id, progress, updated_at)
                   VALUES (?, 0.0, ?)
                   ON CONFLICT(goal_id) DO NOTHING""",
                (goal_id, now),
            )
            event = f"status_transition:{current}->{target}"
            if reason:
                event += f":{reason[:120]}"
            conn.execute(
                "UPDATE goal_state SET last_event=?, updated_at=? WHERE goal_id=?",
                (event, now, goal_id),
            )
            return True

    def _conflict_reason(self, title_a: str, title_b: str) -> Optional[str]:
        a_norm = _normalize_umlauts((title_a or "").lower())
        b_norm = _normalize_umlauts((title_b or "").lower())
        tokens_a = _goal_tokens(a_norm)
        tokens_b = _goal_tokens(b_norm)
        overlap = tokens_a & tokens_b
        if len(overlap) < 2:
            return None

        for pos, neg in _CONFLICT_ANTONYM_PAIRS:
            if (pos in a_norm and neg in b_norm) or (neg in a_norm and pos in b_norm):
                return f"antonym:{pos}/{neg}"

        a_neg = any(tok in tokens_a for tok in _NEGATION_TOKENS)
        b_neg = any(tok in tokens_b for tok in _NEGATION_TOKENS)
        if a_neg != b_neg and len(overlap) >= 3:
            return "negation_overlap"
        return None

    def detect_goal_conflicts(
        self,
        statuses: Optional[List[str]] = None,
        limit: int = 80,
    ) -> List[dict]:
        status_values = statuses or [GoalStatus.ACTIVE, GoalStatus.BLOCKED]
        norm_statuses = [_normalize_goal_status(s) for s in status_values]
        placeholders = ",".join("?" for _ in norm_statuses)

        with self._conn() as conn:
            rows = conn.execute(
                f"""SELECT id, title, status, priority_score
                    FROM goals
                    WHERE status IN ({placeholders})
                    ORDER BY priority_score DESC, created_at DESC
                    LIMIT ?""",
                (*norm_statuses, max(2, int(limit))),
            ).fetchall()

        goals = [dict(r) for r in rows]
        conflicts: List[dict] = []
        for left, right in combinations(goals, 2):
            reason = self._conflict_reason(str(left.get("title", "")), str(right.get("title", "")))
            if not reason:
                continue
            overlap = sorted(
                list(_goal_tokens(str(left.get("title", ""))) & _goal_tokens(str(right.get("title", ""))))
            )
            severity = round(
                (
                    float(left.get("priority_score") or 0.0)
                    + float(right.get("priority_score") or 0.0)
                )
                / 2.0,
                3,
            )
            conflicts.append(
                {
                    "goal_a_id": str(left.get("id")),
                    "goal_a_title": str(left.get("title", "")),
                    "goal_a_status": str(left.get("status", "")),
                    "goal_a_priority": float(left.get("priority_score") or 0.0),
                    "goal_b_id": str(right.get("id")),
                    "goal_b_title": str(right.get("title", "")),
                    "goal_b_status": str(right.get("status", "")),
                    "goal_b_priority": float(right.get("priority_score") or 0.0),
                    "reason": reason,
                    "shared_terms": overlap[:8],
                    "severity": severity,
                }
            )

        conflicts.sort(key=lambda item: item.get("severity", 0.0), reverse=True)
        return conflicts

    def sync_goal_conflicts(
        self,
        *,
        auto_block: bool = False,
        max_pairs: int = 80,
    ) -> Dict[str, Any]:
        conflicts = self.detect_goal_conflicts(limit=max_pairs)
        inserted_edges = 0
        blocked_goals = 0
        now = datetime.now().isoformat()

        with self._conn() as conn:
            for conflict in conflicts:
                left = str(conflict.get("goal_a_id", ""))
                right = str(conflict.get("goal_b_id", ""))
                if not left or not right:
                    continue
                parent, child = sorted([left, right])
                cursor = conn.execute(
                    """INSERT OR IGNORE INTO goal_edges
                       (parent_goal_id, child_goal_id, edge_type, weight, created_at)
                       VALUES (?, ?, 'conflicts_with', ?, ?)""",
                    (parent, child, float(conflict.get("severity") or 0.5), now),
                )
                if cursor.rowcount:
                    inserted_edges += 1

        if auto_block:
            for conflict in conflicts:
                left_id = str(conflict.get("goal_a_id", ""))
                right_id = str(conflict.get("goal_b_id", ""))
                left_status = _normalize_goal_status(str(conflict.get("goal_a_status", "")))
                right_status = _normalize_goal_status(str(conflict.get("goal_b_status", "")))
                if left_status != GoalStatus.ACTIVE and right_status != GoalStatus.ACTIVE:
                    continue
                left_prio = float(conflict.get("goal_a_priority") or 0.0)
                right_prio = float(conflict.get("goal_b_priority") or 0.0)
                target = left_id if left_prio <= right_prio else right_id
                ok = self.transition_goal_status(
                    target,
                    GoalStatus.BLOCKED,
                    reason=f"conflict:{str(conflict.get('reason', 'unknown'))}",
                )
                if ok:
                    blocked_goals += 1

        return {
            "conflicts_detected": len(conflicts),
            "conflict_edges_inserted": inserted_edges,
            "goals_blocked": blocked_goals,
            "top_conflicts": conflicts[:5],
        }

    def get_goal_alignment_metrics(self, include_conflicts: bool = True) -> Dict[str, Any]:
        with self._conn() as conn:
            totals_row = conn.execute(
                """SELECT
                       COUNT(*) AS total_all,
                       SUM(CASE WHEN status IN ('pending','in_progress') THEN 1 ELSE 0 END) AS total_open,
                       SUM(CASE WHEN status IN ('pending','in_progress','completed','failed') THEN 1 ELSE 0 END) AS total_trackable,
                       SUM(CASE WHEN status IN ('pending','in_progress') AND goal_id IS NOT NULL AND goal_id != '' THEN 1 ELSE 0 END) AS aligned_open,
                       SUM(CASE WHEN status IN ('pending','in_progress','completed','failed') AND goal_id IS NOT NULL AND goal_id != '' THEN 1 ELSE 0 END) AS aligned_trackable,
                       SUM(CASE WHEN task_type='triggered' AND status IN ('pending','in_progress') AND (goal_id IS NULL OR goal_id='') THEN 1 ELSE 0 END) AS orphan_triggered
                   FROM tasks"""
            ).fetchone()

            goal_rows = conn.execute(
                "SELECT status, COUNT(*) AS n FROM goals GROUP BY status"
            ).fetchall()

        status_counts = {str(r["status"]): int(r["n"]) for r in goal_rows}
        total_open = int((totals_row["total_open"] if totals_row else 0) or 0)
        aligned_open = int((totals_row["aligned_open"] if totals_row else 0) or 0)
        total_trackable = int((totals_row["total_trackable"] if totals_row else 0) or 0)
        aligned_trackable = int((totals_row["aligned_trackable"] if totals_row else 0) or 0)
        total_all = int((totals_row["total_all"] if totals_row else 0) or 0)
        orphan_triggered = int((totals_row["orphan_triggered"] if totals_row else 0) or 0)

        open_rate = 100.0 if total_open == 0 else round((aligned_open / total_open) * 100.0, 2)
        trackable_rate = (
            100.0 if total_trackable == 0 else round((aligned_trackable / total_trackable) * 100.0, 2)
        )

        conflict_count = 0
        if include_conflicts:
            conflict_count = len(self.detect_goal_conflicts(limit=60))

        return {
            "total_tasks": total_all,
            "open_tasks": total_open,
            "open_aligned_tasks": aligned_open,
            "open_alignment_rate": open_rate,
            "trackable_tasks": total_trackable,
            "aligned_trackable_tasks": aligned_trackable,
            "goal_alignment_rate": trackable_rate,
            "orphan_triggered_tasks": orphan_triggered,
            "goal_counts": {
                "active": status_counts.get(GoalStatus.ACTIVE, 0),
                "blocked": status_counts.get(GoalStatus.BLOCKED, 0),
                "completed": status_counts.get(GoalStatus.COMPLETED, 0),
                "cancelled": status_counts.get(GoalStatus.CANCELLED, 0),
                "total": sum(status_counts.values()),
            },
            "conflict_count": conflict_count,
        }

    # ------------------------------------------------------------------
    # Langzeitplanung (M2)
    # ------------------------------------------------------------------

    def create_or_get_plan(
        self,
        horizon: str,
        window_start: str,
        window_end: str,
        *,
        source: str = "autonomy_planner",
        metadata: Optional[Dict[str, Any]] = None,
        status: str = PlanStatus.ACTIVE,
        plan_id: Optional[str] = None,
    ) -> str:
        horizon = _normalize_plan_horizon(horizon)
        status = _normalize_plan_status(status)
        now = datetime.now().isoformat()
        metadata_json = json.dumps(metadata or {}, ensure_ascii=True) if metadata is not None else None

        with self._conn() as conn:
            existing = conn.execute(
                "SELECT id FROM plans WHERE horizon=? AND window_start=? AND window_end=?",
                (horizon, window_start, window_end),
            ).fetchone()
            if existing:
                pid = str(existing["id"])
                conn.execute(
                    "UPDATE plans SET status=?, source=?, metadata=COALESCE(?, metadata), updated_at=? WHERE id=?",
                    (status, source, metadata_json, now, pid),
                )
                return pid

            pid = plan_id or str(uuid.uuid4())
            conn.execute(
                """INSERT INTO plans
                   (id, horizon, window_start, window_end, status, source, metadata, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (pid, horizon, window_start, window_end, status, source, metadata_json, now, now),
            )
            return pid

    def list_plans(
        self,
        *,
        horizon: Optional[str] = None,
        status: Optional[str] = PlanStatus.ACTIVE,
        limit: int = 50,
    ) -> List[dict]:
        with self._conn() as conn:
            if horizon and status:
                rows = conn.execute(
                    """SELECT * FROM plans
                       WHERE horizon=? AND status=?
                       ORDER BY window_start DESC
                       LIMIT ?""",
                    (_normalize_plan_horizon(horizon), _normalize_plan_status(status), limit),
                ).fetchall()
            elif horizon:
                rows = conn.execute(
                    """SELECT * FROM plans
                       WHERE horizon=?
                       ORDER BY window_start DESC
                       LIMIT ?""",
                    (_normalize_plan_horizon(horizon), limit),
                ).fetchall()
            elif status:
                rows = conn.execute(
                    """SELECT * FROM plans
                       WHERE status=?
                       ORDER BY window_start DESC
                       LIMIT ?""",
                    (_normalize_plan_status(status), limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    """SELECT * FROM plans
                       ORDER BY window_start DESC
                       LIMIT ?""",
                    (limit,),
                ).fetchall()

        out: List[dict] = []
        for row in rows:
            payload = dict(row)
            raw_meta = payload.get("metadata")
            if raw_meta:
                try:
                    payload["metadata"] = json.loads(raw_meta)
                except Exception:
                    payload["metadata"] = {}
            else:
                payload["metadata"] = {}
            out.append(payload)
        return out

    def get_plan(self, plan_id: str) -> Optional[dict]:
        if not plan_id:
            return None
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM plans WHERE id=?", (plan_id,)).fetchone()
        if not row:
            return None
        payload = dict(row)
        raw_meta = payload.get("metadata")
        if raw_meta:
            try:
                payload["metadata"] = json.loads(raw_meta)
            except Exception:
                payload["metadata"] = {}
        else:
            payload["metadata"] = {}
        return payload

    def infer_goal_owner_agent(self, goal_id: str, default: str = "meta") -> str:
        if not goal_id:
            return default
        with self._conn() as conn:
            row = conn.execute(
                """SELECT target_agent, COUNT(*) AS n
                   FROM tasks
                   WHERE goal_id=? AND target_agent IS NOT NULL AND target_agent != ''
                   GROUP BY target_agent
                   ORDER BY n DESC
                   LIMIT 1""",
                (goal_id,),
            ).fetchone()
            if row and row["target_agent"]:
                return str(row["target_agent"])
        return default

    def add_plan_item(
        self,
        plan_id: str,
        title: str,
        *,
        goal_id: Optional[str] = None,
        owner_agent: Optional[str] = None,
        deadline: Optional[str] = None,
        success_metric: Optional[str] = None,
        priority_score: float = 0.0,
        status: str = PlanItemStatus.PLANNED,
    ) -> int:
        if not plan_id:
            raise ValueError("plan_id ist Pflicht")
        clean_title = (title or "").strip()
        if not clean_title:
            raise ValueError("title ist Pflicht")
        now = datetime.now().isoformat()
        owner = owner_agent or (self.infer_goal_owner_agent(goal_id or "", default="meta"))
        status = _normalize_plan_item_status(status)

        with self._conn() as conn:
            existing = conn.execute(
                """SELECT id FROM plan_items
                   WHERE plan_id=? AND COALESCE(goal_id,'')=COALESCE(?, '') AND title=?
                   LIMIT 1""",
                (plan_id, goal_id, clean_title),
            ).fetchone()
            if existing:
                item_id = int(existing["id"])
                conn.execute(
                    """UPDATE plan_items
                       SET owner_agent=?, deadline=?, success_metric=?, priority_score=?, status=?, updated_at=?
                       WHERE id=?""",
                    (owner, deadline, success_metric, float(priority_score), status, now, item_id),
                )
                return item_id

            cursor = conn.execute(
                """INSERT INTO plan_items
                   (plan_id, goal_id, title, owner_agent, deadline, success_metric, priority_score, status, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    plan_id,
                    goal_id,
                    clean_title,
                    owner,
                    deadline,
                    success_metric,
                    float(priority_score),
                    status,
                    now,
                    now,
                ),
            )
            return int(cursor.lastrowid)

    def list_plan_items(
        self,
        plan_id: str,
        *,
        status: Optional[str] = None,
        limit: int = 200,
    ) -> List[dict]:
        with self._conn() as conn:
            if status:
                rows = conn.execute(
                    """SELECT * FROM plan_items
                       WHERE plan_id=? AND status=?
                       ORDER BY priority_score DESC, created_at ASC
                       LIMIT ?""",
                    (plan_id, _normalize_plan_item_status(status), limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    """SELECT * FROM plan_items
                       WHERE plan_id=?
                       ORDER BY priority_score DESC, created_at ASC
                       LIMIT ?""",
                    (plan_id, limit),
                ).fetchall()
        return [dict(r) for r in rows]

    def create_commitment(
        self,
        *,
        plan_id: str,
        goal_id: Optional[str],
        title: str,
        owner_agent: str,
        deadline: str,
        success_metric: str,
        status: str = CommitmentStatus.PENDING,
        progress: float = 0.0,
        metadata: Optional[Dict[str, Any]] = None,
        commitment_id: Optional[str] = None,
    ) -> str:
        if not plan_id:
            raise ValueError("plan_id ist Pflicht")
        clean_title = (title or "").strip()
        if not clean_title:
            raise ValueError("title ist Pflicht")
        owner = (owner_agent or "").strip() or "meta"
        if not deadline:
            raise ValueError("deadline ist Pflicht")
        metric = (success_metric or "").strip() or "delivery_done"
        status = _normalize_commitment_status(status)
        now = datetime.now().isoformat()
        payload = json.dumps(metadata or {}, ensure_ascii=True) if metadata is not None else None

        with self._conn() as conn:
            existing = conn.execute(
                """SELECT id FROM commitments
                   WHERE plan_id=? AND COALESCE(goal_id,'')=COALESCE(?, '') AND title=? AND deadline=?
                   LIMIT 1""",
                (plan_id, goal_id, clean_title, deadline),
            ).fetchone()
            if existing:
                cid = str(existing["id"])
                conn.execute(
                    """UPDATE commitments
                       SET owner_agent=?, success_metric=?, status=?, progress=?, metadata=COALESCE(?, metadata), updated_at=?
                       WHERE id=?""",
                    (owner, metric, status, max(0.0, min(100.0, float(progress))), payload, now, cid),
                )
                return cid

            cid = commitment_id or str(uuid.uuid4())
            conn.execute(
                """INSERT INTO commitments
                   (id, plan_id, goal_id, title, owner_agent, deadline, success_metric, status, progress, metadata, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    cid,
                    plan_id,
                    goal_id,
                    clean_title,
                    owner,
                    deadline,
                    metric,
                    status,
                    max(0.0, min(100.0, float(progress))),
                    payload,
                    now,
                    now,
                ),
            )
            return cid

    def list_commitments(
        self,
        *,
        statuses: Optional[List[str]] = None,
        horizon: Optional[str] = None,
        limit: int = 200,
    ) -> List[dict]:
        with self._conn() as conn:
            if statuses:
                norm = [_normalize_commitment_status(s) for s in statuses]
                placeholders = ",".join("?" for _ in norm)
                if horizon:
                    rows = conn.execute(
                        f"""SELECT c.*
                            FROM commitments c
                            JOIN plans p ON p.id = c.plan_id
                            WHERE c.status IN ({placeholders}) AND p.horizon=?
                            ORDER BY c.deadline ASC
                            LIMIT ?""",
                        (*norm, _normalize_plan_horizon(horizon), limit),
                    ).fetchall()
                else:
                    rows = conn.execute(
                        f"""SELECT * FROM commitments
                            WHERE status IN ({placeholders})
                            ORDER BY deadline ASC
                            LIMIT ?""",
                        (*norm, limit),
                    ).fetchall()
            elif horizon:
                rows = conn.execute(
                    """SELECT c.*
                       FROM commitments c
                       JOIN plans p ON p.id = c.plan_id
                       WHERE p.horizon=?
                       ORDER BY c.deadline ASC
                       LIMIT ?""",
                    (_normalize_plan_horizon(horizon), limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    """SELECT * FROM commitments
                       ORDER BY deadline ASC
                       LIMIT ?""",
                    (limit,),
                ).fetchall()

        out: List[dict] = []
        for row in rows:
            payload = dict(row)
            raw_meta = payload.get("metadata")
            if raw_meta:
                try:
                    payload["metadata"] = json.loads(raw_meta)
                except Exception:
                    payload["metadata"] = {}
            else:
                payload["metadata"] = {}
            out.append(payload)
        return out

    def get_commitment(self, commitment_id: str) -> Optional[dict]:
        if not commitment_id:
            return None
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM commitments WHERE id=?", (commitment_id,)).fetchone()
        if not row:
            return None
        payload = dict(row)
        raw_meta = payload.get("metadata")
        if raw_meta:
            try:
                payload["metadata"] = json.loads(raw_meta)
            except Exception:
                payload["metadata"] = {}
        else:
            payload["metadata"] = {}
        return payload

    def update_commitment_status(
        self,
        commitment_id: str,
        status: str,
        *,
        progress: Optional[float] = None,
        metadata_update: Optional[Dict[str, Any]] = None,
    ) -> bool:
        if not commitment_id:
            return False
        now = datetime.now().isoformat()
        target = _normalize_commitment_status(status)

        with self._conn() as conn:
            row = conn.execute(
                "SELECT progress, metadata FROM commitments WHERE id=?",
                (commitment_id,),
            ).fetchone()
            if not row:
                return False

            new_progress = float(row["progress"] or 0.0)
            if progress is not None:
                new_progress = max(0.0, min(100.0, float(progress)))

            new_meta = row["metadata"]
            if metadata_update is not None:
                base: Dict[str, Any] = {}
                if row["metadata"]:
                    try:
                        loaded = json.loads(row["metadata"])
                        if isinstance(loaded, dict):
                            base = loaded
                    except Exception:
                        base = {}
                base.update(metadata_update)
                new_meta = json.dumps(base, ensure_ascii=True)

            conn.execute(
                """UPDATE commitments
                   SET status=?, progress=?, metadata=?, updated_at=?
                   WHERE id=?""",
                (target, new_progress, new_meta, now, commitment_id),
            )
            return True

    def get_commitment_progress_snapshot(self) -> Dict[str, Any]:
        now = datetime.now()
        due_24h_limit = now + timedelta(hours=24)
        partial_cutoff = now - timedelta(hours=24)
        drift_cutoff = now - timedelta(hours=48)
        open_statuses = {
            CommitmentStatus.PENDING,
            CommitmentStatus.IN_PROGRESS,
            CommitmentStatus.BLOCKED,
        }
        active_statuses = {
            CommitmentStatus.PENDING,
            CommitmentStatus.IN_PROGRESS,
        }
        horizon_health: Dict[str, Dict[str, Any]] = {
            PlanHorizon.DAILY: {
                "total": 0,
                "open": 0,
                "overdue_open": 0,
                "progress_sum_open": 0.0,
                "progress_samples_open": 0,
                "deviation_sum": 0.0,
                "deviation_samples": 0,
            },
            PlanHorizon.WEEKLY: {
                "total": 0,
                "open": 0,
                "overdue_open": 0,
                "progress_sum_open": 0.0,
                "progress_samples_open": 0,
                "deviation_sum": 0.0,
                "deviation_samples": 0,
            },
            PlanHorizon.MONTHLY: {
                "total": 0,
                "open": 0,
                "overdue_open": 0,
                "progress_sum_open": 0.0,
                "progress_samples_open": 0,
                "deviation_sum": 0.0,
                "deviation_samples": 0,
            },
        }

        with self._conn() as conn:
            rows = conn.execute(
                """SELECT c.id, c.status, c.progress, c.deadline, c.created_at, c.updated_at,
                          c.plan_id, p.horizon, p.window_start, p.window_end
                   FROM commitments c
                   LEFT JOIN plans p ON p.id = c.plan_id"""
            ).fetchall()

        total = 0
        open_total = 0
        closed_total = 0
        completed_total = 0
        blocked_open = 0
        overdue_open = 0
        due_24h_open = 0
        partial_stagnation_open = 0
        drift_open = 0
        progress_sum_open = 0.0
        progress_samples_open = 0
        deviation_sum = 0.0
        deviation_samples = 0

        for row in rows:
            payload = dict(row)
            total += 1
            status = _normalize_commitment_status(str(payload.get("status") or ""))
            progress = max(0.0, min(100.0, float(payload.get("progress") or 0.0)))
            deadline_dt = _parse_iso_datetime(str(payload.get("deadline") or ""))
            updated_dt = _parse_iso_datetime(str(payload.get("updated_at") or ""))
            created_dt = _parse_iso_datetime(str(payload.get("created_at") or ""))
            last_change = updated_dt or created_dt
            is_open = status in open_statuses
            is_active = status in active_statuses

            if status in {CommitmentStatus.COMPLETED, CommitmentStatus.FAILED, CommitmentStatus.CANCELLED}:
                closed_total += 1
            if status == CommitmentStatus.COMPLETED:
                completed_total += 1

            if is_open:
                open_total += 1
                progress_sum_open += progress
                progress_samples_open += 1
                if status == CommitmentStatus.BLOCKED:
                    blocked_open += 1

                if deadline_dt:
                    if deadline_dt < now:
                        overdue_open += 1
                    elif deadline_dt <= due_24h_limit:
                        due_24h_open += 1

                if is_active and last_change and last_change < partial_cutoff and 0.0 < progress < 100.0:
                    partial_stagnation_open += 1
                if is_active and last_change and last_change < drift_cutoff and progress <= 0.0:
                    drift_open += 1

            horizon = str(payload.get("horizon") or "")
            if horizon in horizon_health:
                target = horizon_health[horizon]
                target["total"] += 1
                if is_open:
                    target["open"] += 1
                    target["progress_sum_open"] += progress
                    target["progress_samples_open"] += 1
                    if deadline_dt and deadline_dt < now:
                        target["overdue_open"] += 1

                window_start = _parse_iso_datetime(str(payload.get("window_start") or ""))
                window_end = _parse_iso_datetime(str(payload.get("window_end") or ""))
                if is_open and window_start and window_end and window_end > window_start:
                    elapsed = (now - window_start).total_seconds()
                    total_window = (window_end - window_start).total_seconds()
                    if total_window > 0:
                        elapsed_ratio = max(0.0, min(1.0, elapsed / total_window))
                        expected_progress = elapsed_ratio * 100.0
                        gap = max(0.0, expected_progress - progress)
                        target["deviation_sum"] += gap
                        target["deviation_samples"] += 1
                        deviation_sum += gap
                        deviation_samples += 1

        completion_rate = 100.0 if total == 0 else round((completed_total / total) * 100.0, 2)
        avg_progress_open = (
            0.0 if progress_samples_open == 0 else round(progress_sum_open / progress_samples_open, 2)
        )
        blocked_rate_open = (
            0.0 if open_total == 0 else round((blocked_open / open_total) * 100.0, 2)
        )
        plan_deviation_score = (
            0.0 if deviation_samples == 0 else round(deviation_sum / deviation_samples, 2)
        )

        horizon_out: Dict[str, Dict[str, Any]] = {}
        for horizon, stats in horizon_health.items():
            progress_avg = (
                0.0
                if stats["progress_samples_open"] == 0
                else round(stats["progress_sum_open"] / stats["progress_samples_open"], 2)
            )
            deviation_avg = (
                0.0
                if stats["deviation_samples"] == 0
                else round(stats["deviation_sum"] / stats["deviation_samples"], 2)
            )
            horizon_out[horizon] = {
                "total": int(stats["total"]),
                "open": int(stats["open"]),
                "overdue_open": int(stats["overdue_open"]),
                "avg_progress_open": progress_avg,
                "deviation_score": deviation_avg,
            }

        return {
            "commitments_total": total,
            "open_commitments": open_total,
            "closed_commitments": closed_total,
            "completion_rate": completion_rate,
            "avg_progress_open": avg_progress_open,
            "blocked_open": blocked_open,
            "blocked_rate_open": blocked_rate_open,
            "overdue_open": overdue_open,
            "due_24h_open": due_24h_open,
            "partial_stagnation_open": partial_stagnation_open,
            "drift_open": drift_open,
            "plan_deviation_score": plan_deviation_score,
            "horizon_health": horizon_out,
        }

    def list_replanning_candidates(
        self,
        *,
        limit: int = 40,
        include_blocked: bool = True,
    ) -> List[dict]:
        statuses = [CommitmentStatus.PENDING, CommitmentStatus.IN_PROGRESS]
        if include_blocked:
            statuses.append(CommitmentStatus.BLOCKED)
        placeholders = ",".join("?" for _ in statuses)
        scan_limit = max(int(limit) * 6, 80)
        now = datetime.now()
        due_24h_limit = now + timedelta(hours=24)
        partial_cutoff = now - timedelta(hours=24)
        drift_cutoff = now - timedelta(hours=48)

        with self._conn() as conn:
            rows = conn.execute(
                f"""SELECT c.*, p.horizon, p.window_start, p.window_end, g.status AS goal_status
                    FROM commitments c
                    LEFT JOIN plans p ON p.id = c.plan_id
                    LEFT JOIN goals g ON g.id = c.goal_id
                    WHERE c.status IN ({placeholders})
                    ORDER BY c.deadline ASC, c.updated_at ASC
                    LIMIT ?""",
                (*statuses, scan_limit),
            ).fetchall()

        conflicts = self.detect_goal_conflicts(limit=120)
        conflict_goal_ids: Set[str] = set()
        for item in conflicts:
            left = str(item.get("goal_a_id") or "")
            right = str(item.get("goal_b_id") or "")
            if left:
                conflict_goal_ids.add(left)
            if right:
                conflict_goal_ids.add(right)

        candidates: List[dict] = []
        for row in rows:
            payload = dict(row)
            raw_meta = payload.get("metadata")
            if raw_meta:
                try:
                    payload["metadata"] = json.loads(raw_meta)
                except Exception:
                    payload["metadata"] = {}
            else:
                payload["metadata"] = {}

            status = _normalize_commitment_status(str(payload.get("status") or ""))
            progress = max(0.0, min(100.0, float(payload.get("progress") or 0.0)))
            deadline_dt = _parse_iso_datetime(str(payload.get("deadline") or ""))
            updated_dt = _parse_iso_datetime(str(payload.get("updated_at") or ""))
            created_dt = _parse_iso_datetime(str(payload.get("created_at") or ""))
            last_change = updated_dt or created_dt

            score = 0.0
            reasons: List[str] = []
            if deadline_dt:
                if deadline_dt < now:
                    overdue_hours = max(0.0, (now - deadline_dt).total_seconds() / 3600.0)
                    score += 4.0 + min(3.0, overdue_hours / 24.0)
                    reasons.append("overdue")
                elif deadline_dt <= due_24h_limit:
                    score += 1.2
                    reasons.append("due_24h")

            if status == CommitmentStatus.BLOCKED:
                score += 2.5
                reasons.append("blocked")

            goal_id = str(payload.get("goal_id") or "")
            goal_status = _normalize_goal_status(str(payload.get("goal_status") or ""))
            if goal_id and (goal_id in conflict_goal_ids or goal_status == GoalStatus.BLOCKED):
                score += 2.2
                reasons.append("goal_conflict")

            if status in {CommitmentStatus.PENDING, CommitmentStatus.IN_PROGRESS} and last_change:
                if 0.0 < progress < 100.0 and last_change < partial_cutoff:
                    stall_hours = max(0.0, (now - last_change).total_seconds() / 3600.0)
                    score += 1.6 + min(1.4, stall_hours / 72.0)
                    reasons.append("partial_stagnation")
                if progress <= 0.0 and last_change < drift_cutoff:
                    drift_hours = max(0.0, (now - last_change).total_seconds() / 3600.0)
                    score += 1.8 + min(1.5, drift_hours / 96.0)
                    reasons.append("goal_drift")

            horizon_raw = str(payload.get("horizon") or payload.get("metadata", {}).get("horizon") or "")
            horizon = _normalize_plan_horizon(horizon_raw) if horizon_raw else ""
            if horizon == PlanHorizon.DAILY:
                score += 0.6
                reasons.append("daily_horizon")
            elif horizon == PlanHorizon.WEEKLY:
                score += 0.25
                reasons.append("weekly_horizon")

            window_start = _parse_iso_datetime(str(payload.get("window_start") or ""))
            window_end = _parse_iso_datetime(str(payload.get("window_end") or ""))
            if (
                status in {CommitmentStatus.PENDING, CommitmentStatus.IN_PROGRESS, CommitmentStatus.BLOCKED}
                and window_start
                and window_end
                and window_end > window_start
            ):
                elapsed = (now - window_start).total_seconds()
                total_window = (window_end - window_start).total_seconds()
                if total_window > 0:
                    elapsed_ratio = max(0.0, min(1.0, elapsed / total_window))
                    expected_progress = elapsed_ratio * 100.0
                    progress_gap = max(0.0, expected_progress - progress)
                    payload["progress_gap"] = round(progress_gap, 2)
                    if progress_gap >= 20.0:
                        score += min(2.5, progress_gap / 20.0)
                        reasons.append("progress_gap")

            if score <= 0.0 and status in {CommitmentStatus.PENDING, CommitmentStatus.IN_PROGRESS}:
                score = 0.1
                reasons.append("baseline")

            payload["priority_score"] = round(score, 3)
            payload["priority_reasons"] = reasons[:6]
            payload["horizon"] = horizon or payload.get("horizon")
            candidates.append(payload)

        def _deadline_key(item: dict) -> datetime:
            parsed = _parse_iso_datetime(str(item.get("deadline") or ""))
            return parsed or datetime.max

        candidates.sort(
            key=lambda item: (
                -float(item.get("priority_score") or 0.0),
                _deadline_key(item),
                str(item.get("id") or ""),
            )
        )
        return candidates[: max(1, int(limit))]

    def get_planning_metrics(self) -> Dict[str, Any]:
        with self._conn() as conn:
            plans_total = int(
                (conn.execute("SELECT COUNT(*) FROM plans").fetchone() or [0])[0]
            )
            active_plans = int(
                (
                    conn.execute(
                        "SELECT COUNT(*) FROM plans WHERE status=?",
                        (PlanStatus.ACTIVE,),
                    ).fetchone()
                    or [0]
                )[0]
            )
            plan_rows = conn.execute(
                "SELECT horizon, COUNT(*) AS n FROM plans WHERE status=? GROUP BY horizon",
                (PlanStatus.ACTIVE,),
            ).fetchall()
            horizon_counts = {str(r["horizon"]): int(r["n"]) for r in plan_rows}

            commitments_total = int(
                (conn.execute("SELECT COUNT(*) FROM commitments").fetchone() or [0])[0]
            )
            c_rows = conn.execute(
                "SELECT status, COUNT(*) AS n FROM commitments GROUP BY status"
            ).fetchall()
            commitment_counts = {str(r["status"]): int(r["n"]) for r in c_rows}

            now_iso = datetime.now().isoformat()
            overdue = int(
                (
                    conn.execute(
                        """SELECT COUNT(*) FROM commitments
                           WHERE deadline < ?
                             AND status IN (?, ?, ?)""",
                        (now_iso, CommitmentStatus.PENDING, CommitmentStatus.IN_PROGRESS, CommitmentStatus.BLOCKED),
                    ).fetchone()
                    or [0]
                )[0]
            )

        snapshot = self.get_commitment_progress_snapshot()
        review_metrics = self.get_commitment_review_metrics()
        return {
            "plans_total": plans_total,
            "active_plans": active_plans,
            "horizon_counts": {
                PlanHorizon.DAILY: horizon_counts.get(PlanHorizon.DAILY, 0),
                PlanHorizon.WEEKLY: horizon_counts.get(PlanHorizon.WEEKLY, 0),
                PlanHorizon.MONTHLY: horizon_counts.get(PlanHorizon.MONTHLY, 0),
            },
            "commitments_total": commitments_total,
            "commitment_counts": commitment_counts,
            "overdue_commitments": overdue,
            "due_24h_commitments": snapshot.get("due_24h_open", 0),
            "blocked_open_commitments": snapshot.get("blocked_open", 0),
            "avg_progress_open": snapshot.get("avg_progress_open", 0.0),
            "plan_deviation_score": snapshot.get("plan_deviation_score", 0.0),
            "due_reviews": review_metrics.get("due_reviews", 0),
            "scheduled_reviews": review_metrics.get("scheduled_reviews", 0),
            "escalated_reviews_7d": review_metrics.get("escalated_last_7d", 0),
            "avg_review_gap_7d": review_metrics.get("avg_gap_last_7d", 0.0),
        }

    def cancel_overdue_commitments(
        self,
        overdue_threshold_hours: float = 2.0,
    ) -> Dict[str, Any]:
        """Bricht Commitments ab, deren Deadline oder Plan-Fenster abgelaufen ist.

        Bedingungen (ODER-verknüpft, threshold_hours Toleranz):
          1. commitment.deadline < now - threshold_hours
          2. plan.window_end   < now - threshold_hours  (treibt plan_deviation_score)

        Betrifft nur Status: pending, in_progress, blocked.
        Trägt den Grund in die Metadaten ein.
        """
        cutoff = (datetime.now() - timedelta(hours=overdue_threshold_hours)).isoformat()
        now = datetime.now().isoformat()
        cancelled_ids: list = []

        with self._conn() as conn:
            rows = conn.execute(
                """SELECT c.id,
                          CASE
                            WHEN c.deadline IS NOT NULL AND c.deadline < ? THEN 'deadline_expired'
                            ELSE 'plan_window_expired'
                          END AS cancel_reason
                   FROM commitments c
                   LEFT JOIN plans p ON p.id = c.plan_id
                   WHERE c.status IN (?, ?, ?)
                     AND (
                       (c.deadline IS NOT NULL AND c.deadline < ?)
                       OR
                       (p.window_end IS NOT NULL AND p.window_end < ?)
                     )""",
                (
                    cutoff,
                    CommitmentStatus.PENDING, CommitmentStatus.IN_PROGRESS, CommitmentStatus.BLOCKED,
                    cutoff, cutoff,
                ),
            ).fetchall()

            for row in rows:
                cid = str(row["id"])
                meta_update = json.dumps(
                    {"cancelled_reason": row["cancel_reason"], "cancelled_at": now},
                    ensure_ascii=True,
                )
                conn.execute(
                    """UPDATE commitments
                       SET status=?, updated_at=?,
                           metadata=json_patch(COALESCE(metadata, '{}'), ?)
                       WHERE id=?""",
                    (CommitmentStatus.CANCELLED, now, meta_update, cid),
                )
                cancelled_ids.append(cid)

        return {"cancelled": len(cancelled_ids), "ids": cancelled_ids}

    def close_stale_escalated_reviews(
        self,
        stale_after_hours: float = 48.0,
    ) -> Dict[str, Any]:
        """Schließt eskalierte Commitment-Reviews die älter als stale_after_hours sind.

        Verhindert dass escalated_reviews_7d den Planning-Score dauerhaft drückt.
        Eskalierte Reviews, die durch den Self-Healing-Zyklus nie manuell geschlossen
        wurden (z.B. weil das zugehörige Commitment bereits abgebrochen wurde),
        werden automatisch auf 'closed' gesetzt.
        """
        cutoff = (datetime.now() - timedelta(hours=stale_after_hours)).isoformat()
        now = datetime.now().isoformat()

        with self._conn() as conn:
            result = conn.execute(
                """UPDATE commitment_reviews
                   SET status='closed', updated_at=?
                   WHERE status='escalated' AND created_at < ?""",
                (now, cutoff),
            )
            closed = result.rowcount

        return {"closed": closed}

    def log_replan_event(
        self,
        *,
        event_key: str,
        commitment_id: str,
        trigger_type: str,
        goal_id: Optional[str] = None,
        severity: str = "medium",
        status: str = ReplanEventStatus.DETECTED,
        action: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        clean_key = (event_key or "").strip()
        if not clean_key:
            raise ValueError("event_key ist Pflicht")
        if not commitment_id:
            raise ValueError("commitment_id ist Pflicht")

        now = datetime.now().isoformat()
        trigger = _normalize_replan_trigger(trigger_type)
        event_status = _normalize_replan_event_status(status)
        severity_norm = (severity or "medium").strip().lower() or "medium"
        details_json = json.dumps(details or {}, ensure_ascii=True) if details is not None else None

        with self._conn() as conn:
            existing = conn.execute(
                "SELECT id, status, action, details FROM replan_events WHERE event_key=?",
                (clean_key,),
            ).fetchone()
            if existing:
                merged_details = existing["details"]
                if details is not None:
                    base: Dict[str, Any] = {}
                    if existing["details"]:
                        try:
                            loaded = json.loads(existing["details"])
                            if isinstance(loaded, dict):
                                base = loaded
                        except Exception:
                            base = {}
                    base.update(details)
                    merged_details = json.dumps(base, ensure_ascii=True)

                existing_status = _normalize_replan_event_status(str(existing["status"] or ""))
                target_status = (
                    existing_status
                    if existing_status in {ReplanEventStatus.APPLIED, ReplanEventStatus.FAILED}
                    else event_status
                )
                conn.execute(
                    """UPDATE replan_events
                       SET status=?, action=?, details=?, updated_at=?
                       WHERE id=?""",
                    (
                        target_status,
                        action if action is not None else existing["action"],
                        merged_details if merged_details is not None else details_json,
                        now,
                        int(existing["id"]),
                    ),
                )
                return {"id": int(existing["id"]), "created": False}

            cursor = conn.execute(
                """INSERT INTO replan_events
                   (event_key, commitment_id, goal_id, trigger_type, severity, status, action, details, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    clean_key,
                    commitment_id,
                    goal_id,
                    trigger,
                    severity_norm,
                    event_status,
                    action,
                    details_json,
                    now,
                    now,
                ),
            )
            return {"id": int(cursor.lastrowid), "created": True}

    def update_replan_event_status(
        self,
        event_id: int,
        status: str,
        *,
        action: Optional[str] = None,
        details_update: Optional[Dict[str, Any]] = None,
    ) -> bool:
        if not event_id:
            return False
        target = _normalize_replan_event_status(status)
        now = datetime.now().isoformat()

        with self._conn() as conn:
            row = conn.execute(
                "SELECT action, details FROM replan_events WHERE id=?",
                (int(event_id),),
            ).fetchone()
            if not row:
                return False

            merged_details = row["details"]
            if details_update is not None:
                base: Dict[str, Any] = {}
                if row["details"]:
                    try:
                        loaded = json.loads(row["details"])
                        if isinstance(loaded, dict):
                            base = loaded
                    except Exception:
                        base = {}
                base.update(details_update)
                merged_details = json.dumps(base, ensure_ascii=True)

            conn.execute(
                """UPDATE replan_events
                   SET status=?, action=?, details=?, updated_at=?
                   WHERE id=?""",
                (
                    target,
                    action if action is not None else row["action"],
                    merged_details,
                    now,
                    int(event_id),
                ),
            )
            return True

    def list_replan_events(
        self,
        *,
        statuses: Optional[List[str]] = None,
        trigger_types: Optional[List[str]] = None,
        limit: int = 100,
    ) -> List[dict]:
        clauses: List[str] = []
        params: List[Any] = []
        if statuses:
            norm_statuses = [_normalize_replan_event_status(s) for s in statuses]
            placeholders = ",".join("?" for _ in norm_statuses)
            clauses.append(f"status IN ({placeholders})")
            params.extend(norm_statuses)
        if trigger_types:
            norm_triggers = [_normalize_replan_trigger(t) for t in trigger_types]
            placeholders = ",".join("?" for _ in norm_triggers)
            clauses.append(f"trigger_type IN ({placeholders})")
            params.extend(norm_triggers)

        query = "SELECT * FROM replan_events"
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)

        with self._conn() as conn:
            rows = conn.execute(query, tuple(params)).fetchall()

        out: List[dict] = []
        for row in rows:
            payload = dict(row)
            raw_details = payload.get("details")
            if raw_details:
                try:
                    payload["details"] = json.loads(raw_details)
                except Exception:
                    payload["details"] = {}
            else:
                payload["details"] = {}
            out.append(payload)
        return out

    def get_replanning_metrics(self) -> Dict[str, Any]:
        now = datetime.now()
        now_iso = now.isoformat()
        since_24h = (now - timedelta(hours=24)).isoformat()
        since_partial = (now - timedelta(hours=24)).isoformat()
        since_drift = (now - timedelta(hours=48)).isoformat()

        with self._conn() as conn:
            events_total = int(
                (conn.execute("SELECT COUNT(*) FROM replan_events").fetchone() or [0])[0]
            )
            trigger_rows = conn.execute(
                "SELECT trigger_type, COUNT(*) AS n FROM replan_events GROUP BY trigger_type"
            ).fetchall()
            trigger_counts = {str(r["trigger_type"]): int(r["n"]) for r in trigger_rows}

            status_rows = conn.execute(
                "SELECT status, COUNT(*) AS n FROM replan_events GROUP BY status"
            ).fetchall()
            status_counts = {str(r["status"]): int(r["n"]) for r in status_rows}

            events_last_24h = int(
                (
                    conn.execute(
                        "SELECT COUNT(*) FROM replan_events WHERE created_at >= ?",
                        (since_24h,),
                    ).fetchone()
                    or [0]
                )[0]
            )
            applied_last_24h = int(
                (
                    conn.execute(
                        "SELECT COUNT(*) FROM replan_events WHERE status=? AND created_at >= ?",
                        (ReplanEventStatus.APPLIED, since_24h),
                    ).fetchone()
                    or [0]
                )[0]
            )

            overdue_candidates = int(
                (
                    conn.execute(
                        """SELECT COUNT(*) FROM commitments
                           WHERE deadline < ?
                             AND status IN (?, ?, ?)""",
                        (now_iso, CommitmentStatus.PENDING, CommitmentStatus.IN_PROGRESS, CommitmentStatus.BLOCKED),
                    ).fetchone()
                    or [0]
                )[0]
            )
            partial_stall_candidates = int(
                (
                    conn.execute(
                        """SELECT COUNT(*) FROM commitments
                           WHERE progress > 0
                             AND progress < 100
                             AND updated_at < ?
                             AND status IN (?, ?)""",
                        (since_partial, CommitmentStatus.PENDING, CommitmentStatus.IN_PROGRESS),
                    ).fetchone()
                    or [0]
                )[0]
            )
            drift_candidates = int(
                (
                    conn.execute(
                        """SELECT COUNT(*) FROM commitments
                           WHERE progress <= 0
                             AND updated_at < ?
                            AND status IN (?, ?)""",
                        (since_drift, CommitmentStatus.PENDING, CommitmentStatus.IN_PROGRESS),
                    ).fetchone()
                    or [0]
                )[0]
            )

        top_candidates = self.list_replanning_candidates(limit=5, include_blocked=True)
        top_candidate_summary = [
            {
                "id": str(c.get("id", "")),
                "title": str(c.get("title", ""))[:120],
                "status": str(c.get("status", "")),
                "deadline": str(c.get("deadline", "")),
                "horizon": str(c.get("horizon", "")),
                "priority_score": float(c.get("priority_score") or 0.0),
                "priority_reasons": list(c.get("priority_reasons") or []),
            }
            for c in top_candidates
        ]

        return {
            "events_total": events_total,
            "events_last_24h": events_last_24h,
            "applied_last_24h": applied_last_24h,
            "trigger_counts": trigger_counts,
            "status_counts": status_counts,
            "overdue_candidates": overdue_candidates,
            "partial_stall_candidates": partial_stall_candidates,
            "drift_candidates": drift_candidates,
            "top_priority_score": (
                float(top_candidate_summary[0]["priority_score"]) if top_candidate_summary else 0.0
            ),
            "top_candidates": top_candidate_summary,
        }

    def upsert_commitment_review(
        self,
        *,
        commitment_id: str,
        review_due_at: str,
        review_type: str = "checkpoint",
        status: str = CommitmentReviewStatus.SCHEDULED,
        plan_id: Optional[str] = None,
        goal_id: Optional[str] = None,
        horizon: Optional[str] = None,
        expected_progress: Optional[float] = None,
        observed_progress: Optional[float] = None,
        progress_gap: Optional[float] = None,
        risk_level: str = "low",
        notes: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        reviewed_at: Optional[str] = None,
    ) -> Dict[str, Any]:
        if not commitment_id:
            raise ValueError("commitment_id ist Pflicht")
        due_dt = _parse_iso_datetime(review_due_at)
        if due_dt is None:
            raise ValueError("review_due_at muss ISO-8601 sein")
        rtype = (review_type or "checkpoint").strip().lower() or "checkpoint"
        state = _normalize_commitment_review_status(status)
        risk = (risk_level or "low").strip().lower() or "low"
        now = datetime.now().isoformat()
        payload = json.dumps(metadata or {}, ensure_ascii=True) if metadata is not None else None

        expected_norm = None if expected_progress is None else max(0.0, min(100.0, float(expected_progress)))
        observed_norm = None if observed_progress is None else max(0.0, min(100.0, float(observed_progress)))
        if progress_gap is None and expected_norm is not None and observed_norm is not None:
            gap_norm = round(expected_norm - observed_norm, 2)
        elif progress_gap is None:
            gap_norm = None
        else:
            gap_norm = float(progress_gap)

        with self._conn() as conn:
            existing = conn.execute(
                """SELECT id, status, metadata
                   FROM commitment_reviews
                   WHERE commitment_id=? AND review_due_at=? AND review_type=?
                   LIMIT 1""",
                (commitment_id, due_dt.isoformat(), rtype),
            ).fetchone()
            if existing:
                merged_meta = existing["metadata"]
                if metadata is not None:
                    base: Dict[str, Any] = {}
                    if existing["metadata"]:
                        try:
                            loaded = json.loads(existing["metadata"])
                            if isinstance(loaded, dict):
                                base = loaded
                        except Exception:
                            base = {}
                    base.update(metadata)
                    merged_meta = json.dumps(base, ensure_ascii=True)
                existing_status = _normalize_commitment_review_status(str(existing["status"] or ""))
                target_status = state
                if state == CommitmentReviewStatus.SCHEDULED and existing_status in {
                    CommitmentReviewStatus.COMPLETED,
                    CommitmentReviewStatus.ESCALATED,
                    CommitmentReviewStatus.SKIPPED,
                }:
                    target_status = existing_status
                conn.execute(
                    """UPDATE commitment_reviews
                       SET status=?, plan_id=?, goal_id=?, horizon=?, expected_progress=?, observed_progress=?,
                           progress_gap=?, risk_level=?, notes=?, metadata=?, reviewed_at=?, updated_at=?
                       WHERE id=?""",
                    (
                        target_status,
                        plan_id,
                        goal_id,
                        (_normalize_plan_horizon(horizon) if horizon else None),
                        expected_norm,
                        observed_norm,
                        gap_norm,
                        risk,
                        notes,
                        merged_meta if merged_meta is not None else payload,
                        reviewed_at,
                        now,
                        int(existing["id"]),
                    ),
                )
                return {"id": int(existing["id"]), "created": False}

            cursor = conn.execute(
                """INSERT INTO commitment_reviews
                   (commitment_id, plan_id, goal_id, horizon, review_due_at, reviewed_at, review_type, status,
                    expected_progress, observed_progress, progress_gap, risk_level, notes, metadata, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    commitment_id,
                    plan_id,
                    goal_id,
                    (_normalize_plan_horizon(horizon) if horizon else None),
                    due_dt.isoformat(),
                    reviewed_at,
                    rtype,
                    state,
                    expected_norm,
                    observed_norm,
                    gap_norm,
                    risk,
                    notes,
                    payload,
                    now,
                    now,
                ),
            )
            return {"id": int(cursor.lastrowid), "created": True}

    def list_commitment_reviews(
        self,
        *,
        statuses: Optional[List[str]] = None,
        commitment_id: Optional[str] = None,
        due_only: bool = False,
        limit: int = 200,
    ) -> List[dict]:
        clauses: List[str] = []
        params: List[Any] = []
        if statuses:
            norm = [_normalize_commitment_review_status(s) for s in statuses]
            placeholders = ",".join("?" for _ in norm)
            clauses.append(f"status IN ({placeholders})")
            params.extend(norm)
        if commitment_id:
            clauses.append("commitment_id=?")
            params.append(commitment_id)
        if due_only:
            clauses.append("review_due_at <= ?")
            params.append(datetime.now().isoformat())

        query = "SELECT * FROM commitment_reviews"
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        query += " ORDER BY review_due_at ASC LIMIT ?"
        params.append(max(1, int(limit)))

        with self._conn() as conn:
            rows = conn.execute(query, tuple(params)).fetchall()

        out: List[dict] = []
        for row in rows:
            payload = dict(row)
            raw_meta = payload.get("metadata")
            if raw_meta:
                try:
                    payload["metadata"] = json.loads(raw_meta)
                except Exception:
                    payload["metadata"] = {}
            else:
                payload["metadata"] = {}
            out.append(payload)
        return out

    def update_commitment_review(
        self,
        review_id: int,
        *,
        status: Optional[str] = None,
        expected_progress: Optional[float] = None,
        observed_progress: Optional[float] = None,
        progress_gap: Optional[float] = None,
        risk_level: Optional[str] = None,
        notes: Optional[str] = None,
        reviewed_at: Optional[str] = None,
        metadata_update: Optional[Dict[str, Any]] = None,
    ) -> bool:
        if not review_id:
            return False
        now = datetime.now().isoformat()
        with self._conn() as conn:
            row = conn.execute(
                """SELECT status, expected_progress, observed_progress, progress_gap, risk_level, notes, metadata
                   FROM commitment_reviews WHERE id=?""",
                (int(review_id),),
            ).fetchone()
            if not row:
                return False

            target_status = (
                _normalize_commitment_review_status(status)
                if status is not None
                else _normalize_commitment_review_status(str(row["status"] or ""))
            )
            expected_norm = (
                max(0.0, min(100.0, float(expected_progress)))
                if expected_progress is not None
                else (float(row["expected_progress"]) if row["expected_progress"] is not None else None)
            )
            observed_norm = (
                max(0.0, min(100.0, float(observed_progress)))
                if observed_progress is not None
                else (float(row["observed_progress"]) if row["observed_progress"] is not None else None)
            )
            if progress_gap is not None:
                gap_norm = float(progress_gap)
            elif expected_norm is not None and observed_norm is not None:
                gap_norm = round(expected_norm - observed_norm, 2)
            else:
                gap_norm = float(row["progress_gap"]) if row["progress_gap"] is not None else None

            risk_norm = (risk_level or str(row["risk_level"] or "low")).strip().lower() or "low"
            merged_notes = notes if notes is not None else row["notes"]
            reviewed_at_value = reviewed_at
            if reviewed_at_value is None and target_status in {
                CommitmentReviewStatus.COMPLETED,
                CommitmentReviewStatus.ESCALATED,
                CommitmentReviewStatus.SKIPPED,
            }:
                reviewed_at_value = now

            merged_meta = row["metadata"]
            if metadata_update is not None:
                base: Dict[str, Any] = {}
                if row["metadata"]:
                    try:
                        loaded = json.loads(row["metadata"])
                        if isinstance(loaded, dict):
                            base = loaded
                    except Exception:
                        base = {}
                base.update(metadata_update)
                merged_meta = json.dumps(base, ensure_ascii=True)

            conn.execute(
                """UPDATE commitment_reviews
                   SET status=?, expected_progress=?, observed_progress=?, progress_gap=?,
                       risk_level=?, notes=?, reviewed_at=?, metadata=?, updated_at=?
                   WHERE id=?""",
                (
                    target_status,
                    expected_norm,
                    observed_norm,
                    gap_norm,
                    risk_norm,
                    merged_notes,
                    reviewed_at_value,
                    merged_meta,
                    now,
                    int(review_id),
                ),
            )
            return True

    def sync_commitment_review_checkpoints(
        self,
        *,
        limit: int = 240,
    ) -> Dict[str, Any]:
        now = datetime.now()
        created = 0
        updated = 0
        scanned = 0

        with self._conn() as conn:
            rows = conn.execute(
                """SELECT c.id, c.plan_id, c.goal_id, c.status, c.progress, c.deadline, c.created_at, c.updated_at,
                          p.horizon, p.window_start, p.window_end
                   FROM commitments c
                   LEFT JOIN plans p ON p.id = c.plan_id
                   WHERE c.status IN (?, ?, ?)
                   ORDER BY c.deadline ASC
                   LIMIT ?""",
                (
                    CommitmentStatus.PENDING,
                    CommitmentStatus.IN_PROGRESS,
                    CommitmentStatus.BLOCKED,
                    max(1, int(limit)),
                ),
            ).fetchall()

        for row in rows:
            scanned += 1
            payload = dict(row)
            commitment_id = str(payload.get("id", ""))
            deadline_dt = _parse_iso_datetime(str(payload.get("deadline") or ""))
            if not commitment_id or deadline_dt is None:
                continue

            horizon_raw = str(payload.get("horizon") or "")
            horizon = _normalize_plan_horizon(horizon_raw) if horizon_raw else PlanHorizon.WEEKLY
            interval = _review_interval_for_horizon(horizon)

            with self._conn() as conn:
                last = conn.execute(
                    """SELECT review_due_at
                       FROM commitment_reviews
                       WHERE commitment_id=? AND review_type='checkpoint'
                       ORDER BY review_due_at DESC
                       LIMIT 1""",
                    (commitment_id,),
                ).fetchone()
            if last and last["review_due_at"]:
                seed = _parse_iso_datetime(str(last["review_due_at"])) or now
                if seed >= deadline_dt:
                    continue
                next_due = seed + interval
            else:
                base = _parse_iso_datetime(str(payload.get("updated_at") or "")) or _parse_iso_datetime(
                    str(payload.get("created_at") or "")
                ) or now
                next_due = base + interval

            if next_due > deadline_dt:
                next_due = deadline_dt
            if next_due < now - interval:
                next_due = now

            expected_progress = None
            start_dt = _parse_iso_datetime(str(payload.get("window_start") or ""))
            end_dt = _parse_iso_datetime(str(payload.get("window_end") or ""))
            if start_dt and end_dt and end_dt > start_dt:
                total_window = (end_dt - start_dt).total_seconds()
                elapsed = (next_due - start_dt).total_seconds()
                if total_window > 0:
                    expected_progress = max(0.0, min(100.0, (elapsed / total_window) * 100.0))

            res = self.upsert_commitment_review(
                commitment_id=commitment_id,
                plan_id=str(payload.get("plan_id") or "") or None,
                goal_id=str(payload.get("goal_id") or "") or None,
                horizon=horizon,
                review_due_at=next_due.isoformat(),
                review_type="checkpoint",
                status=CommitmentReviewStatus.SCHEDULED,
                expected_progress=expected_progress,
                risk_level="low",
                notes="auto_checkpoint",
                metadata={"source": "sync_commitment_review_checkpoints"},
            )
            if res.get("created"):
                created += 1
            else:
                updated += 1

        return {
            "status": "ok",
            "commitments_scanned": scanned,
            "reviews_created": created,
            "reviews_updated": updated,
        }

    def get_commitment_review_metrics(self) -> Dict[str, Any]:
        now = datetime.now()
        now_iso = now.isoformat()
        since_24h = (now - timedelta(hours=24)).isoformat()
        since_7d = (now - timedelta(days=7)).isoformat()

        with self._conn() as conn:
            total = int((conn.execute("SELECT COUNT(*) FROM commitment_reviews").fetchone() or [0])[0])
            status_rows = conn.execute(
                "SELECT status, COUNT(*) AS n FROM commitment_reviews GROUP BY status"
            ).fetchall()
            status_counts = {str(r["status"]): int(r["n"]) for r in status_rows}

            due_reviews = int(
                (
                    conn.execute(
                        """SELECT COUNT(*) FROM commitment_reviews
                           WHERE status=? AND review_due_at <= ?""",
                        (CommitmentReviewStatus.SCHEDULED, now_iso),
                    ).fetchone()
                    or [0]
                )[0]
            )
            next_due_row = conn.execute(
                """SELECT review_due_at FROM commitment_reviews
                   WHERE status=?
                   ORDER BY review_due_at ASC
                   LIMIT 1""",
                (CommitmentReviewStatus.SCHEDULED,),
            ).fetchone()
            next_due_at = str(next_due_row["review_due_at"]) if next_due_row else None

            completed_last_24h = int(
                (
                    conn.execute(
                        """SELECT COUNT(*) FROM commitment_reviews
                           WHERE status=? AND reviewed_at >= ?""",
                        (CommitmentReviewStatus.COMPLETED, since_24h),
                    ).fetchone()
                    or [0]
                )[0]
            )
            escalated_last_7d = int(
                (
                    conn.execute(
                        """SELECT COUNT(*) FROM commitment_reviews
                           WHERE status=? AND reviewed_at >= ?""",
                        (CommitmentReviewStatus.ESCALATED, since_7d),
                    ).fetchone()
                    or [0]
                )[0]
            )
            avg_gap_last_7d_row = conn.execute(
                """SELECT AVG(progress_gap) AS v
                   FROM commitment_reviews
                   WHERE reviewed_at >= ? AND progress_gap IS NOT NULL""",
                (since_7d,),
            ).fetchone()
            avg_gap_last_7d = float(avg_gap_last_7d_row["v"] or 0.0) if avg_gap_last_7d_row else 0.0

            risk_rows = conn.execute(
                """SELECT risk_level, COUNT(*) AS n
                   FROM commitment_reviews
                   WHERE reviewed_at >= ?
                   GROUP BY risk_level""",
                (since_7d,),
            ).fetchall()
            risk_counts = {str(r["risk_level"]): int(r["n"]) for r in risk_rows}

        return {
            "reviews_total": total,
            "status_counts": status_counts,
            "scheduled_reviews": status_counts.get(CommitmentReviewStatus.SCHEDULED, 0),
            "due_reviews": due_reviews,
            "completed_last_24h": completed_last_24h,
            "escalated_last_7d": escalated_last_7d,
            "avg_gap_last_7d": round(avg_gap_last_7d, 2),
            "risk_counts": risk_counts,
            "next_due_at": next_due_at,
        }

    def get_self_healing_incident(self, incident_key: str) -> Optional[dict]:
        key = (incident_key or "").strip()
        if not key:
            return None
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM self_healing_incidents WHERE incident_key=?",
                (key,),
            ).fetchone()
        if not row:
            return None
        payload = dict(row)
        raw_details = payload.get("details")
        if raw_details:
            try:
                payload["details"] = json.loads(raw_details)
            except Exception:
                payload["details"] = {}
        else:
            payload["details"] = {}
        return payload

    def upsert_self_healing_incident(
        self,
        *,
        incident_key: str,
        component: str,
        signal: str,
        severity: str = "medium",
        status: str = SelfHealingIncidentStatus.OPEN,
        title: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        recovery_action: Optional[str] = None,
        recovery_status: Optional[str] = None,
        observed_at: Optional[str] = None,
    ) -> Dict[str, Any]:
        key = (incident_key or "").strip()
        if not key:
            raise ValueError("incident_key ist Pflicht")
        comp = (component or "").strip().lower()
        sig = (signal or "").strip().lower()
        if not comp or not sig:
            raise ValueError("component und signal sind Pflicht")
        target_status = _normalize_self_healing_incident_status(status)
        sev = (severity or "medium").strip().lower() or "medium"
        now = (_parse_iso_datetime(observed_at) or datetime.now()).isoformat()
        details_json = json.dumps(details or {}, ensure_ascii=True) if details is not None else None

        with self._conn() as conn:
            existing = conn.execute(
                """SELECT id, status, details, first_seen_at
                   FROM self_healing_incidents
                   WHERE incident_key=?""",
                (key,),
            ).fetchone()
            if existing:
                existing_status = _normalize_self_healing_incident_status(str(existing["status"] or ""))
                reopened = (
                    existing_status != SelfHealingIncidentStatus.OPEN
                    and target_status == SelfHealingIncidentStatus.OPEN
                )

                merged_details = existing["details"]
                if details is not None:
                    base: Dict[str, Any] = {}
                    if existing["details"]:
                        try:
                            loaded = json.loads(existing["details"])
                            if isinstance(loaded, dict):
                                base = loaded
                        except Exception:
                            base = {}
                    base.update(details)
                    merged_details = json.dumps(base, ensure_ascii=True)

                conn.execute(
                    """UPDATE self_healing_incidents
                       SET component=?, signal=?, severity=?, status=?, title=?,
                           details=?, recovery_action=COALESCE(?, recovery_action),
                           recovery_status=COALESCE(?, recovery_status),
                           last_seen_at=?, recovered_at=?, updated_at=?
                       WHERE id=?""",
                    (
                        comp,
                        sig,
                        sev,
                        target_status,
                        title,
                        merged_details if merged_details is not None else details_json,
                        recovery_action,
                        recovery_status,
                        now,
                        (None if target_status == SelfHealingIncidentStatus.OPEN else now),
                        now,
                        int(existing["id"]),
                    ),
                )
                return {"id": int(existing["id"]), "created": False, "reopened": reopened}

            cursor = conn.execute(
                """INSERT INTO self_healing_incidents
                   (incident_key, component, signal, severity, status, title, details,
                    recovery_action, recovery_status, first_seen_at, last_seen_at, recovered_at, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    key,
                    comp,
                    sig,
                    sev,
                    target_status,
                    title,
                    details_json,
                    recovery_action,
                    recovery_status,
                    now,
                    now,
                    (None if target_status == SelfHealingIncidentStatus.OPEN else now),
                    now,
                    now,
                ),
            )
            return {"id": int(cursor.lastrowid), "created": True, "reopened": False}

    def resolve_self_healing_incident(
        self,
        incident_key: str,
        *,
        status: str = SelfHealingIncidentStatus.RECOVERED,
        recovery_action: Optional[str] = None,
        recovery_status: Optional[str] = "ok",
        details_update: Optional[Dict[str, Any]] = None,
        observed_at: Optional[str] = None,
    ) -> bool:
        key = (incident_key or "").strip()
        if not key:
            return False
        target_status = _normalize_self_healing_incident_status(status)
        now = (_parse_iso_datetime(observed_at) or datetime.now()).isoformat()
        with self._conn() as conn:
            row = conn.execute(
                "SELECT details, recovery_action, recovery_status FROM self_healing_incidents WHERE incident_key=?",
                (key,),
            ).fetchone()
            if not row:
                return False

            merged_details = row["details"]
            if details_update is not None:
                base: Dict[str, Any] = {}
                if row["details"]:
                    try:
                        loaded = json.loads(row["details"])
                        if isinstance(loaded, dict):
                            base = loaded
                    except Exception:
                        base = {}
                base.update(details_update)
                merged_details = json.dumps(base, ensure_ascii=True)

            conn.execute(
                """UPDATE self_healing_incidents
                   SET status=?, details=?, recovery_action=?, recovery_status=?,
                       last_seen_at=?, recovered_at=?, updated_at=?
                   WHERE incident_key=?""",
                (
                    target_status,
                    merged_details,
                    recovery_action if recovery_action is not None else row["recovery_action"],
                    recovery_status if recovery_status is not None else row["recovery_status"],
                    now,
                    now,
                    now,
                    key,
                ),
            )
            return True

    def list_self_healing_incidents(
        self,
        *,
        statuses: Optional[List[str]] = None,
        component: Optional[str] = None,
        limit: int = 100,
    ) -> List[dict]:
        clauses: List[str] = []
        params: List[Any] = []
        if statuses:
            norm = [_normalize_self_healing_incident_status(s) for s in statuses]
            placeholders = ",".join("?" for _ in norm)
            clauses.append(f"status IN ({placeholders})")
            params.extend(norm)
        if component:
            clauses.append("component=?")
            params.append(component.strip().lower())

        query = "SELECT * FROM self_healing_incidents"
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        query += " ORDER BY last_seen_at DESC LIMIT ?"
        params.append(max(1, int(limit)))

        with self._conn() as conn:
            rows = conn.execute(query, tuple(params)).fetchall()

        out: List[dict] = []
        for row in rows:
            payload = dict(row)
            raw_details = payload.get("details")
            if raw_details:
                try:
                    payload["details"] = json.loads(raw_details)
                except Exception:
                    payload["details"] = {}
            else:
                payload["details"] = {}
            out.append(payload)
        return out

    def get_self_healing_metrics(self) -> Dict[str, Any]:
        now = datetime.now()
        since_24h = (now - timedelta(hours=24)).isoformat()
        since_7d = (now - timedelta(days=7)).isoformat()
        with self._conn() as conn:
            total = int((conn.execute("SELECT COUNT(*) FROM self_healing_incidents").fetchone() or [0])[0])
            status_rows = conn.execute(
                "SELECT status, COUNT(*) AS n FROM self_healing_incidents GROUP BY status"
            ).fetchall()
            status_counts = {str(r["status"]): int(r["n"]) for r in status_rows}

            component_rows = conn.execute(
                "SELECT component, COUNT(*) AS n FROM self_healing_incidents WHERE status=? GROUP BY component",
                (SelfHealingIncidentStatus.OPEN,),
            ).fetchall()
            open_by_component = {str(r["component"]): int(r["n"]) for r in component_rows}

            severity_rows = conn.execute(
                "SELECT severity, COUNT(*) AS n FROM self_healing_incidents WHERE status=? GROUP BY severity",
                (SelfHealingIncidentStatus.OPEN,),
            ).fetchall()
            open_by_severity = {str(r["severity"]): int(r["n"]) for r in severity_rows}

            created_last_24h = int(
                (
                    conn.execute(
                        "SELECT COUNT(*) FROM self_healing_incidents WHERE created_at >= ?",
                        (since_24h,),
                    ).fetchone()
                    or [0]
                )[0]
            )
            recovered_last_24h = int(
                (
                    conn.execute(
                        """SELECT COUNT(*) FROM self_healing_incidents
                           WHERE status=? AND recovered_at IS NOT NULL AND recovered_at >= ?""",
                        (SelfHealingIncidentStatus.RECOVERED, since_24h),
                    ).fetchone()
                    or [0]
                )[0]
            )
            failed_last_7d = int(
                (
                    conn.execute(
                        """SELECT COUNT(*) FROM self_healing_incidents
                           WHERE status=? AND updated_at >= ?""",
                        (SelfHealingIncidentStatus.FAILED, since_7d),
                    ).fetchone()
                    or [0]
                )[0]
            )
            last_open_row = conn.execute(
                """SELECT incident_key, component, signal, severity, last_seen_at
                   FROM self_healing_incidents
                   WHERE status=?
                   ORDER BY last_seen_at DESC
                   LIMIT 1""",
                (SelfHealingIncidentStatus.OPEN,),
            ).fetchone()
            last_open = dict(last_open_row) if last_open_row else None
            open_rows = conn.execute(
                "SELECT details, first_seen_at FROM self_healing_incidents WHERE status=?",
                (SelfHealingIncidentStatus.OPEN,),
            ).fetchall()

            runtime_row = conn.execute(
                "SELECT state_value, metadata, updated_at FROM self_healing_runtime_state WHERE state_key=?",
                ("degrade_mode",),
            ).fetchone()

        degrade_mode = SelfHealingDegradeMode.NORMAL
        degrade_reason: Optional[str] = None
        degrade_updated_at: Optional[str] = None
        if runtime_row:
            degrade_mode = _normalize_self_healing_degrade_mode(str(runtime_row["state_value"] or ""))
            degrade_updated_at = str(runtime_row["updated_at"] or "") or None
            raw_meta = runtime_row["metadata"]
            if raw_meta:
                try:
                    loaded = json.loads(raw_meta)
                    if isinstance(loaded, dict):
                        degrade_reason = str(
                            loaded.get("reason")
                            or loaded.get("reason_code")
                            or loaded.get("primary_reason")
                            or ""
                        ).strip() or None
                except Exception:
                    degrade_reason = None

        open_escalated_incidents = 0
        max_open_incident_age_min = 0.0
        for row in open_rows:
            details = {}
            raw_details = row["details"]
            if raw_details:
                try:
                    loaded = json.loads(raw_details)
                    if isinstance(loaded, dict):
                        details = loaded
                except Exception:
                    details = {}
            if bool(details.get("escalated")):
                open_escalated_incidents += 1
            first_seen = _parse_iso_datetime(str(row["first_seen_at"] or ""))
            if first_seen is None:
                continue
            age_min = max(0.0, (now - first_seen).total_seconds() / 60.0)
            if age_min > max_open_incident_age_min:
                max_open_incident_age_min = age_min

        open_total = status_counts.get(SelfHealingIncidentStatus.OPEN, 0)
        recovery_rate_24h = (
            100.0
            if created_last_24h == 0
            else round((recovered_last_24h / created_last_24h) * 100.0, 2)
        )
        circuit_metrics = self.get_self_healing_circuit_breaker_metrics()
        return {
            "incidents_total": total,
            "status_counts": status_counts,
            "open_incidents": open_total,
            "open_by_component": open_by_component,
            "open_by_severity": open_by_severity,
            "created_last_24h": created_last_24h,
            "recovered_last_24h": recovered_last_24h,
            "failed_last_7d": failed_last_7d,
            "recovery_rate_24h": recovery_rate_24h,
            "last_open_incident": last_open,
            "open_escalated_incidents": open_escalated_incidents,
            "max_open_incident_age_min": round(max_open_incident_age_min, 2),
            "circuit_breakers_total": circuit_metrics.get("breakers_total", 0),
            "circuit_breakers_open": circuit_metrics.get("open_breakers", 0),
            "circuit_breaker_state_counts": circuit_metrics.get("state_counts", {}),
            "degrade_mode": degrade_mode,
            "degrade_reason": degrade_reason,
            "degrade_updated_at": degrade_updated_at,
        }

    def record_policy_decision(
        self,
        decision: Dict[str, Any],
        *,
        observed_at: Optional[str] = None,
    ) -> int:
        if not isinstance(decision, dict):
            raise ValueError("decision muss ein dict sein")

        gate = str(decision.get("gate") or "unknown").strip().lower() or "unknown"
        source = str(decision.get("source") or "").strip() or None
        subject = str(decision.get("subject") or "").strip() or None
        action = str(decision.get("action") or "allow").strip().lower() or "allow"
        blocked = 1 if bool(decision.get("blocked")) else 0
        strict_mode = 1 if bool(decision.get("strict_mode")) else 0
        reason = str(decision.get("reason") or "").strip() or None

        violations = decision.get("violations")
        if not isinstance(violations, list):
            violations = []
        violations_json = json.dumps(violations, ensure_ascii=True)

        payload = decision.get("payload")
        payload_json = json.dumps(payload if isinstance(payload, dict) else {}, ensure_ascii=True)

        try:
            canary_percent = int(decision.get("canary_percent", 0) or 0)
        except Exception:
            canary_percent = 0
        canary_percent = max(0, min(100, canary_percent))

        try:
            canary_bucket_raw = decision.get("canary_bucket")
            canary_bucket = None if canary_bucket_raw is None else int(canary_bucket_raw)
        except Exception:
            canary_bucket = None

        canary_enforced = 1 if bool(decision.get("canary_enforced", True)) else 0

        created_at = (
            _parse_iso_datetime(observed_at)
            or _parse_iso_datetime(str(decision.get("timestamp") or ""))
            or datetime.now()
        ).isoformat()

        with self._conn() as conn:
            cursor = conn.execute(
                """INSERT INTO policy_decisions
                   (gate, source, subject, action, blocked, strict_mode, reason, violations, payload,
                    canary_percent, canary_bucket, canary_enforced, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    gate,
                    source,
                    subject,
                    action,
                    blocked,
                    strict_mode,
                    reason,
                    violations_json,
                    payload_json,
                    canary_percent,
                    canary_bucket,
                    canary_enforced,
                    created_at,
                ),
            )
        return int(cursor.lastrowid)

    def list_policy_decisions(
        self,
        *,
        window_hours: int = 24,
        gate: Optional[str] = None,
        source: Optional[str] = None,
        limit: int = 200,
    ) -> List[Dict[str, Any]]:
        window = max(1, int(window_hours))
        since = (datetime.now() - timedelta(hours=window)).isoformat()
        clauses = ["created_at >= ?"]
        params: List[Any] = [since]
        if gate:
            clauses.append("gate = ?")
            params.append(gate.strip().lower())
        if source:
            clauses.append("source = ?")
            params.append(source.strip())
        params.append(max(1, int(limit)))

        query = (
            "SELECT * FROM policy_decisions "
            f"WHERE {' AND '.join(clauses)} "
            "ORDER BY created_at DESC LIMIT ?"
        )
        with self._conn() as conn:
            rows = conn.execute(query, tuple(params)).fetchall()

        out: List[Dict[str, Any]] = []
        for row in rows:
            payload = dict(row)
            raw_violations = payload.get("violations")
            if raw_violations:
                try:
                    loaded = json.loads(raw_violations)
                    payload["violations"] = loaded if isinstance(loaded, list) else []
                except Exception:
                    payload["violations"] = []
            else:
                payload["violations"] = []

            raw_payload = payload.get("payload")
            if raw_payload:
                try:
                    loaded = json.loads(raw_payload)
                    payload["payload"] = loaded if isinstance(loaded, dict) else {}
                except Exception:
                    payload["payload"] = {}
            else:
                payload["payload"] = {}

            payload["blocked"] = bool(int(payload.get("blocked", 0) or 0))
            payload["strict_mode"] = bool(int(payload.get("strict_mode", 0) or 0))
            payload["canary_enforced"] = bool(int(payload.get("canary_enforced", 1) or 0))
            out.append(payload)
        return out

    def set_policy_runtime_state(
        self,
        state_key: str,
        state_value: str,
        *,
        metadata_update: Optional[Dict[str, Any]] = None,
        observed_at: Optional[str] = None,
    ) -> Dict[str, Any]:
        key = (state_key or "").strip().lower()
        value = (state_value or "").strip()
        if not key:
            raise ValueError("state_key darf nicht leer sein")
        if not value:
            raise ValueError("state_value darf nicht leer sein")

        now = _parse_iso_datetime(observed_at) or datetime.now()
        now_iso = now.isoformat()
        meta_payload: Dict[str, Any] = {}
        created = False

        with self._conn() as conn:
            row = conn.execute(
                "SELECT metadata FROM policy_runtime_state WHERE state_key=?",
                (key,),
            ).fetchone()
            if row is None:
                created = True
            elif row["metadata"]:
                try:
                    loaded = json.loads(row["metadata"])
                    if isinstance(loaded, dict):
                        meta_payload = loaded
                except Exception:
                    meta_payload = {}

            meta_payload.update(metadata_update or {})
            metadata_json = json.dumps(meta_payload, ensure_ascii=True) if meta_payload else None

            conn.execute(
                """INSERT INTO policy_runtime_state (state_key, state_value, metadata, updated_at)
                   VALUES (?, ?, ?, ?)
                   ON CONFLICT(state_key) DO UPDATE SET
                       state_value=excluded.state_value,
                       metadata=excluded.metadata,
                       updated_at=excluded.updated_at""",
                (key, value, metadata_json, now_iso),
            )

        return {
            "state_key": key,
            "state_value": value,
            "metadata": meta_payload,
            "updated_at": now_iso,
            "created": created,
        }

    def get_policy_runtime_state(self, state_key: str) -> Optional[Dict[str, Any]]:
        key = (state_key or "").strip().lower()
        if not key:
            return None
        with self._conn() as conn:
            row = conn.execute(
                "SELECT state_key, state_value, metadata, updated_at FROM policy_runtime_state WHERE state_key=?",
                (key,),
            ).fetchone()
        if not row:
            return None
        payload = dict(row)
        raw_meta = payload.get("metadata")
        if raw_meta:
            try:
                payload["metadata"] = json.loads(raw_meta)
            except Exception:
                payload["metadata"] = {}
        else:
            payload["metadata"] = {}
        payload["state_value"] = str(payload.get("state_value") or "")
        return payload

    def get_policy_decision_metrics(self, *, window_hours: int = 24) -> Dict[str, Any]:
        now = datetime.now()
        window = max(1, int(window_hours))
        since = (now - timedelta(hours=window)).isoformat()

        with self._conn() as conn:
            total = int(
                (
                    conn.execute(
                        "SELECT COUNT(*) FROM policy_decisions WHERE created_at >= ?",
                        (since,),
                    ).fetchone()
                    or [0]
                )[0]
            )
            blocked_total = int(
                (
                    conn.execute(
                        "SELECT COUNT(*) FROM policy_decisions WHERE created_at >= ? AND blocked = 1",
                        (since,),
                    ).fetchone()
                    or [0]
                )[0]
            )
            observed_total = int(
                (
                    conn.execute(
                        "SELECT COUNT(*) FROM policy_decisions WHERE created_at >= ? AND action = 'observe'",
                        (since,),
                    ).fetchone()
                    or [0]
                )[0]
            )
            allowed_total = int(
                (
                    conn.execute(
                        "SELECT COUNT(*) FROM policy_decisions WHERE created_at >= ? AND action = 'allow'",
                        (since,),
                    ).fetchone()
                    or [0]
                )[0]
            )
            strict_decisions = int(
                (
                    conn.execute(
                        "SELECT COUNT(*) FROM policy_decisions WHERE created_at >= ? AND strict_mode = 1",
                        (since,),
                    ).fetchone()
                    or [0]
                )[0]
            )
            canary_deferred_total = int(
                (
                    conn.execute(
                        """SELECT COUNT(*) FROM policy_decisions
                           WHERE created_at >= ? AND strict_mode = 1 AND canary_enforced = 0""",
                        (since,),
                    ).fetchone()
                    or [0]
                )[0]
            )

            gate_rows = conn.execute(
                """SELECT gate, COUNT(*) AS n
                   FROM policy_decisions
                   WHERE created_at >= ?
                   GROUP BY gate""",
                (since,),
            ).fetchall()
            by_gate = {str(r["gate"]): int(r["n"]) for r in gate_rows}

            source_rows = conn.execute(
                """SELECT source, COUNT(*) AS n
                   FROM policy_decisions
                   WHERE created_at >= ?
                   GROUP BY source""",
                (since,),
            ).fetchall()
            by_source = {str(r["source"] or "unknown"): int(r["n"]) for r in source_rows}

            last_blocked_row = conn.execute(
                """SELECT created_at, gate, source, reason
                   FROM policy_decisions
                   WHERE created_at >= ? AND blocked = 1
                   ORDER BY created_at DESC
                   LIMIT 1""",
                (since,),
            ).fetchone()
            last_blocked = dict(last_blocked_row) if last_blocked_row else None

            runtime_rows = conn.execute(
                """SELECT state_key, state_value, metadata, updated_at
                   FROM policy_runtime_state
                   WHERE state_key IN (
                       'strict_force_off',
                       'canary_percent_override',
                       'rollout_last_action',
                       'scorecard_governance_state'
                   )"""
            ).fetchall()

        runtime: Dict[str, Dict[str, Any]] = {}
        strict_force_off = False
        canary_override: Optional[int] = None
        scorecard_governance_state: Optional[str] = None
        for row in runtime_rows:
            entry = dict(row)
            key = str(entry.get("state_key") or "")
            raw_meta = entry.get("metadata")
            if raw_meta:
                try:
                    loaded = json.loads(raw_meta)
                    entry["metadata"] = loaded if isinstance(loaded, dict) else {}
                except Exception:
                    entry["metadata"] = {}
            else:
                entry["metadata"] = {}
            runtime[key] = entry

        strict_entry = runtime.get("strict_force_off")
        if strict_entry:
            strict_force_off = str(strict_entry.get("state_value") or "").strip().lower() in {"1", "true", "yes", "on"}

        canary_entry = runtime.get("canary_percent_override")
        if canary_entry:
            try:
                canary_override = int(str(canary_entry.get("state_value") or "").strip())
            except Exception:
                canary_override = None
        governance_entry = runtime.get("scorecard_governance_state")
        if governance_entry:
            scorecard_governance_state = str(governance_entry.get("state_value") or "").strip() or None

        return {
            "window_hours": window,
            "decisions_total": total,
            "blocked_total": blocked_total,
            "observed_total": observed_total,
            "allowed_total": allowed_total,
            "strict_decisions": strict_decisions,
            "canary_deferred_total": canary_deferred_total,
            "by_gate": by_gate,
            "by_source": by_source,
            "last_blocked": last_blocked,
            "runtime_overrides": runtime,
            "strict_force_off": strict_force_off,
            "canary_percent_override": canary_override,
            "scorecard_governance_state": scorecard_governance_state,
        }

    def record_autonomy_scorecard_snapshot(
        self,
        scorecard: Dict[str, Any],
        *,
        observed_at: Optional[str] = None,
    ) -> int:
        if not isinstance(scorecard, dict):
            raise ValueError("scorecard muss ein dict sein")

        overall_score = float(scorecard.get("overall_score", 0.0) or 0.0)
        overall_score_10 = float(scorecard.get("overall_score_10", overall_score / 10.0) or 0.0)
        autonomy_level = str(scorecard.get("autonomy_level", "low") or "low").strip().lower() or "low"
        ready = 1 if bool(scorecard.get("ready_for_very_high_autonomy", False)) else 0
        window_hours = max(1, int(scorecard.get("window_hours", 24) or 24))

        pillars_raw = scorecard.get("pillars")
        control_raw = scorecard.get("control")
        pillars_json = json.dumps(pillars_raw if isinstance(pillars_raw, dict) else {}, ensure_ascii=True)
        control_json = json.dumps(control_raw if isinstance(control_raw, dict) else {}, ensure_ascii=True)
        created_at = (_parse_iso_datetime(observed_at) or datetime.now()).isoformat()

        with self._conn() as conn:
            cursor = conn.execute(
                """INSERT INTO autonomy_scorecard_snapshots
                   (overall_score, overall_score_10, autonomy_level, ready_for_very_high,
                    window_hours, pillars, control_state, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    overall_score,
                    overall_score_10,
                    autonomy_level,
                    ready,
                    window_hours,
                    pillars_json,
                    control_json,
                    created_at,
                ),
            )
        return int(cursor.lastrowid)

    def list_autonomy_scorecard_snapshots(
        self,
        *,
        window_hours: int = 24,
        limit: int = 200,
    ) -> List[Dict[str, Any]]:
        window = max(1, int(window_hours))
        since = (datetime.now() - timedelta(hours=window)).isoformat()
        with self._conn() as conn:
            rows = conn.execute(
                """SELECT *
                   FROM autonomy_scorecard_snapshots
                   WHERE created_at >= ?
                   ORDER BY created_at DESC
                   LIMIT ?""",
                (since, max(1, int(limit))),
            ).fetchall()

        out: List[Dict[str, Any]] = []
        for row in rows:
            payload = dict(row)
            raw_pillars = payload.get("pillars")
            if raw_pillars:
                try:
                    loaded = json.loads(raw_pillars)
                    payload["pillars"] = loaded if isinstance(loaded, dict) else {}
                except Exception:
                    payload["pillars"] = {}
            else:
                payload["pillars"] = {}

            raw_control = payload.get("control_state")
            if raw_control:
                try:
                    loaded = json.loads(raw_control)
                    payload["control_state"] = loaded if isinstance(loaded, dict) else {}
                except Exception:
                    payload["control_state"] = {}
            else:
                payload["control_state"] = {}
            payload["ready_for_very_high"] = bool(int(payload.get("ready_for_very_high", 0) or 0))
            out.append(payload)
        return out

    def get_autonomy_scorecard_trends(
        self,
        *,
        window_hours: int = 24,
        baseline_days: int = 30,
    ) -> Dict[str, Any]:
        window = max(1, int(window_hours))
        baseline = max(2, int(baseline_days))
        now = datetime.now()
        since_window = (now - timedelta(hours=window)).isoformat()
        since_baseline = (now - timedelta(days=baseline)).isoformat()

        with self._conn() as conn:
            window_rows = conn.execute(
                """SELECT overall_score, created_at
                   FROM autonomy_scorecard_snapshots
                   WHERE created_at >= ?
                   ORDER BY created_at ASC""",
                (since_window,),
            ).fetchall()
            baseline_rows = conn.execute(
                """SELECT overall_score, created_at
                   FROM autonomy_scorecard_snapshots
                   WHERE created_at >= ?
                   ORDER BY created_at ASC""",
                (since_baseline,),
            ).fetchall()

        window_scores = [float(r["overall_score"]) for r in window_rows]
        baseline_scores = [float(r["overall_score"]) for r in baseline_rows]

        def _avg(values: List[float]) -> float:
            if not values:
                return 0.0
            return float(sum(values) / len(values))

        def _stdev(values: List[float], avg: float) -> float:
            if len(values) < 2:
                return 0.0
            variance = sum((v - avg) ** 2 for v in values) / len(values)
            return math.sqrt(variance)

        avg_window = _avg(window_scores)
        avg_baseline = _avg(baseline_scores)
        volatility_window = _stdev(window_scores, avg_window)
        trend_delta = avg_window - avg_baseline if baseline_scores else 0.0

        earliest_window_score = window_scores[0] if window_scores else 0.0
        latest_score = window_scores[-1] if window_scores else (baseline_scores[-1] if baseline_scores else 0.0)

        window_days = max(1.0 / 24.0, window / 24.0)
        slope_per_day = (
            ((latest_score - earliest_window_score) / window_days)
            if len(window_scores) >= 2
            else 0.0
        )

        if trend_delta >= 3.0:
            trend_direction = "improving"
        elif trend_delta <= -3.0:
            trend_direction = "declining"
        else:
            trend_direction = "stable"

        return {
            "window_hours": window,
            "baseline_days": baseline,
            "samples_window": len(window_scores),
            "samples_baseline": len(baseline_scores),
            "avg_score_window": round(avg_window, 2),
            "avg_score_baseline": round(avg_baseline, 2),
            "min_score_window": round(min(window_scores), 2) if window_scores else 0.0,
            "max_score_window": round(max(window_scores), 2) if window_scores else 0.0,
            "latest_score": round(latest_score, 2),
            "earliest_window_score": round(earliest_window_score, 2) if window_scores else 0.0,
            "volatility_window": round(volatility_window, 2),
            "trend_delta": round(trend_delta, 2),
            "trend_direction": trend_direction,
            "slope_per_day": round(slope_per_day, 2),
        }

    def create_autonomy_change_request(
        self,
        *,
        audit_id: str,
        recommendation: str,
        source: str = "autonomy_audit",
        report_path: Optional[str] = None,
        payload: Optional[Dict[str, Any]] = None,
        status: str = "proposed",
        reason: Optional[str] = None,
        request_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        aid = (audit_id or "").strip()
        if not aid:
            raise ValueError("audit_id ist Pflicht")
        rec = (recommendation or "hold").strip().lower() or "hold"
        src = (source or "autonomy_audit").strip().lower() or "autonomy_audit"
        req_status = (status or "proposed").strip().lower() or "proposed"
        rid = request_id or str(uuid.uuid4())
        now = datetime.now().isoformat()
        payload_json = json.dumps(payload or {}, ensure_ascii=True)

        with self._conn() as conn:
            existing = conn.execute(
                """SELECT * FROM autonomy_change_requests
                   WHERE audit_id=?
                   LIMIT 1""",
                (aid,),
            ).fetchone()
            if existing:
                out = dict(existing)
                raw_payload = out.get("payload")
                if raw_payload:
                    try:
                        out["payload"] = json.loads(raw_payload)
                    except Exception:
                        out["payload"] = {}
                else:
                    out["payload"] = {}
                out["created"] = False
                return out

            conn.execute(
                """INSERT INTO autonomy_change_requests
                   (id, audit_id, source, recommendation, status, action, reason, report_path, payload, created_at, updated_at, applied_at)
                   VALUES (?, ?, ?, ?, ?, NULL, ?, ?, ?, ?, ?, NULL)""",
                (
                    rid,
                    aid,
                    src,
                    rec,
                    req_status,
                    reason,
                    report_path,
                    payload_json,
                    now,
                    now,
                ),
            )

        return {
            "id": rid,
            "audit_id": aid,
            "source": src,
            "recommendation": rec,
            "status": req_status,
            "action": None,
            "reason": reason,
            "report_path": report_path,
            "payload": payload or {},
            "created_at": now,
            "updated_at": now,
            "applied_at": None,
            "created": True,
        }

    def get_autonomy_change_request(self, request_id: str) -> Optional[Dict[str, Any]]:
        rid = (request_id or "").strip()
        if not rid:
            return None
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM autonomy_change_requests WHERE id=?",
                (rid,),
            ).fetchone()
        if not row:
            return None
        out = dict(row)
        raw_payload = out.get("payload")
        if raw_payload:
            try:
                out["payload"] = json.loads(raw_payload)
            except Exception:
                out["payload"] = {}
        else:
            out["payload"] = {}
        return out

    def get_autonomy_change_request_by_audit_id(self, audit_id: str) -> Optional[Dict[str, Any]]:
        aid = (audit_id or "").strip()
        if not aid:
            return None
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM autonomy_change_requests WHERE audit_id=?",
                (aid,),
            ).fetchone()
        if not row:
            return None
        out = dict(row)
        raw_payload = out.get("payload")
        if raw_payload:
            try:
                out["payload"] = json.loads(raw_payload)
            except Exception:
                out["payload"] = {}
        else:
            out["payload"] = {}
        return out

    def update_autonomy_change_request(
        self,
        request_id: str,
        *,
        status: Optional[str] = None,
        action: Optional[str] = None,
        reason: Optional[str] = None,
        payload_update: Optional[Dict[str, Any]] = None,
        applied_at: Optional[str] = None,
    ) -> bool:
        rid = (request_id or "").strip()
        if not rid:
            return False
        now = datetime.now().isoformat()
        with self._conn() as conn:
            row = conn.execute(
                """SELECT status, action, reason, payload, applied_at
                   FROM autonomy_change_requests
                   WHERE id=?""",
                (rid,),
            ).fetchone()
            if not row:
                return False

            merged_payload = row["payload"]
            if payload_update is not None:
                base: Dict[str, Any] = {}
                if row["payload"]:
                    try:
                        loaded = json.loads(row["payload"])
                        if isinstance(loaded, dict):
                            base = loaded
                    except Exception:
                        base = {}
                base.update(payload_update)
                merged_payload = json.dumps(base, ensure_ascii=True)

            conn.execute(
                """UPDATE autonomy_change_requests
                   SET status=?, action=?, reason=?, payload=?, updated_at=?, applied_at=?
                   WHERE id=?""",
                (
                    (status or str(row["status"] or "proposed")).strip().lower(),
                    action if action is not None else row["action"],
                    reason if reason is not None else row["reason"],
                    merged_payload,
                    now,
                    applied_at if applied_at is not None else row["applied_at"],
                    rid,
                ),
            )
            return True

    def list_autonomy_change_requests(
        self,
        *,
        statuses: Optional[List[str]] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        clauses: List[str] = []
        params: List[Any] = []
        if statuses:
            norm = [str(s or "").strip().lower() for s in statuses if str(s or "").strip()]
            if norm:
                placeholders = ",".join("?" for _ in norm)
                clauses.append(f"status IN ({placeholders})")
                params.extend(norm)

        query = "SELECT * FROM autonomy_change_requests"
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        query += " ORDER BY updated_at DESC LIMIT ?"
        params.append(max(1, int(limit)))

        with self._conn() as conn:
            rows = conn.execute(query, tuple(params)).fetchall()

        out: List[Dict[str, Any]] = []
        for row in rows:
            payload = dict(row)
            raw_payload = payload.get("payload")
            if raw_payload:
                try:
                    payload["payload"] = json.loads(raw_payload)
                except Exception:
                    payload["payload"] = {}
            else:
                payload["payload"] = {}
            out.append(payload)
        return out

    def set_self_healing_runtime_state(
        self,
        state_key: str,
        state_value: str,
        *,
        metadata_update: Optional[Dict[str, Any]] = None,
        observed_at: Optional[str] = None,
    ) -> Dict[str, Any]:
        key = (state_key or "").strip().lower()
        value = (state_value or "").strip()
        if not key:
            raise ValueError("state_key darf nicht leer sein")
        if not value:
            raise ValueError("state_value darf nicht leer sein")

        now = _parse_iso_datetime(observed_at) or datetime.now()
        now_iso = now.isoformat()
        meta_payload: Dict[str, Any] = {}
        created = False
        with self._conn() as conn:
            row = conn.execute(
                "SELECT metadata FROM self_healing_runtime_state WHERE state_key=?",
                (key,),
            ).fetchone()
            if row is None:
                created = True
            elif row["metadata"]:
                try:
                    loaded = json.loads(row["metadata"])
                    if isinstance(loaded, dict):
                        meta_payload = loaded
                except Exception:
                    meta_payload = {}

            meta_payload.update(metadata_update or {})
            metadata_json = json.dumps(meta_payload, ensure_ascii=True) if meta_payload else None

            conn.execute(
                """INSERT INTO self_healing_runtime_state (state_key, state_value, metadata, updated_at)
                   VALUES (?, ?, ?, ?)
                   ON CONFLICT(state_key) DO UPDATE SET
                       state_value=excluded.state_value,
                       metadata=excluded.metadata,
                       updated_at=excluded.updated_at""",
                (key, value, metadata_json, now_iso),
            )

        return {
            "state_key": key,
            "state_value": value,
            "metadata": meta_payload,
            "updated_at": now_iso,
            "created": created,
        }

    def get_self_healing_runtime_state(self, state_key: str) -> Optional[Dict[str, Any]]:
        key = (state_key or "").strip().lower()
        if not key:
            return None
        with self._conn() as conn:
            row = conn.execute(
                "SELECT state_key, state_value, metadata, updated_at FROM self_healing_runtime_state WHERE state_key=?",
                (key,),
            ).fetchone()
        if not row:
            return None
        payload = dict(row)
        raw_meta = payload.get("metadata")
        if raw_meta:
            try:
                payload["metadata"] = json.loads(raw_meta)
            except Exception:
                payload["metadata"] = {}
        else:
            payload["metadata"] = {}
        payload["state_value"] = str(payload.get("state_value") or "")
        return payload

    def get_self_healing_circuit_breaker(
        self,
        breaker_key: str,
    ) -> Optional[dict]:
        key = (breaker_key or "").strip()
        if not key:
            return None
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM self_healing_circuit_breakers WHERE breaker_key=?",
                (key,),
            ).fetchone()
        if not row:
            return None
        payload = dict(row)
        raw_meta = payload.get("metadata")
        if raw_meta:
            try:
                payload["metadata"] = json.loads(raw_meta)
            except Exception:
                payload["metadata"] = {}
        else:
            payload["metadata"] = {}
        return payload

    def record_self_healing_circuit_breaker_result(
        self,
        *,
        breaker_key: str,
        component: str,
        signal: str,
        success: bool,
        failure_threshold: int = 3,
        cooldown_seconds: int = 600,
        metadata_update: Optional[Dict[str, Any]] = None,
        observed_at: Optional[str] = None,
    ) -> Dict[str, Any]:
        key = (breaker_key or "").strip()
        comp = (component or "").strip().lower()
        sig = (signal or "").strip().lower()
        if not key or not comp or not sig:
            raise ValueError("breaker_key, component und signal sind Pflicht")
        threshold = max(1, int(failure_threshold))
        cooldown = max(1, int(cooldown_seconds))
        now = _parse_iso_datetime(observed_at) or datetime.now()
        now_iso = now.isoformat()

        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM self_healing_circuit_breakers WHERE breaker_key=?",
                (key,),
            ).fetchone()

            created = False
            if row is None:
                created = True
                base_state = SelfHealingCircuitBreakerState.CLOSED
                failure_streak = 0
                trip_count = 0
                opened_until = None
                last_failure_at = None
                last_success_at = None
                base_meta: Dict[str, Any] = {}
            else:
                base_state = _normalize_self_healing_circuit_breaker_state(str(row["state"] or ""))
                failure_streak = int(row["failure_streak"] or 0)
                trip_count = int(row["trip_count"] or 0)
                opened_until = str(row["opened_until"] or "") or None
                last_failure_at = str(row["last_failure_at"] or "") or None
                last_success_at = str(row["last_success_at"] or "") or None
                base_meta = {}
                if row["metadata"]:
                    try:
                        loaded = json.loads(row["metadata"])
                        if isinstance(loaded, dict):
                            base_meta = loaded
                    except Exception:
                        base_meta = {}

            tripped = False
            recovered = False
            cooldown_active = False
            opened_until_dt = _parse_iso_datetime(opened_until)

            if success:
                if base_state == SelfHealingCircuitBreakerState.OPEN:
                    recovered = True
                new_state = SelfHealingCircuitBreakerState.CLOSED
                failure_streak = 0
                opened_until = None
                last_success_at = now_iso
            else:
                within_open_window = (
                    base_state == SelfHealingCircuitBreakerState.OPEN
                    and opened_until_dt is not None
                    and now < opened_until_dt
                )
                if within_open_window:
                    new_state = SelfHealingCircuitBreakerState.OPEN
                    cooldown_active = True
                else:
                    failure_streak = max(0, failure_streak) + 1
                    last_failure_at = now_iso
                    if failure_streak >= threshold:
                        new_state = SelfHealingCircuitBreakerState.OPEN
                        opened_until = (now + timedelta(seconds=cooldown)).isoformat()
                        trip_count += 1
                        tripped = True
                    else:
                        new_state = SelfHealingCircuitBreakerState.CLOSED
                        opened_until = None

            base_meta.update(metadata_update or {})
            metadata_json = json.dumps(base_meta, ensure_ascii=True)

            if row is None:
                conn.execute(
                    """INSERT INTO self_healing_circuit_breakers
                       (breaker_key, component, signal, state, failure_streak, trip_count, cooldown_seconds,
                        opened_until, last_failure_at, last_success_at, metadata, created_at, updated_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        key,
                        comp,
                        sig,
                        new_state,
                        failure_streak,
                        trip_count,
                        cooldown,
                        opened_until,
                        last_failure_at,
                        last_success_at,
                        metadata_json,
                        now_iso,
                        now_iso,
                    ),
                )
            else:
                conn.execute(
                    """UPDATE self_healing_circuit_breakers
                       SET component=?, signal=?, state=?, failure_streak=?, trip_count=?, cooldown_seconds=?,
                           opened_until=?, last_failure_at=?, last_success_at=?, metadata=?, updated_at=?
                       WHERE breaker_key=?""",
                    (
                        comp,
                        sig,
                        new_state,
                        failure_streak,
                        trip_count,
                        cooldown,
                        opened_until,
                        last_failure_at,
                        last_success_at,
                        metadata_json,
                        now_iso,
                        key,
                    ),
                )

        return {
            "breaker_key": key,
            "state": new_state,
            "failure_streak": failure_streak,
            "trip_count": trip_count,
            "opened_until": opened_until,
            "tripped": tripped,
            "recovered": recovered,
            "cooldown_active": cooldown_active,
            "created": created,
        }

    def list_self_healing_circuit_breakers(
        self,
        *,
        states: Optional[List[str]] = None,
        component: Optional[str] = None,
        limit: int = 100,
    ) -> List[dict]:
        clauses: List[str] = []
        params: List[Any] = []
        if states:
            norm = [_normalize_self_healing_circuit_breaker_state(s) for s in states]
            placeholders = ",".join("?" for _ in norm)
            clauses.append(f"state IN ({placeholders})")
            params.extend(norm)
        if component:
            clauses.append("component=?")
            params.append(component.strip().lower())

        query = "SELECT * FROM self_healing_circuit_breakers"
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        query += " ORDER BY updated_at DESC LIMIT ?"
        params.append(max(1, int(limit)))

        with self._conn() as conn:
            rows = conn.execute(query, tuple(params)).fetchall()

        out: List[dict] = []
        for row in rows:
            payload = dict(row)
            raw_meta = payload.get("metadata")
            if raw_meta:
                try:
                    payload["metadata"] = json.loads(raw_meta)
                except Exception:
                    payload["metadata"] = {}
            else:
                payload["metadata"] = {}
            out.append(payload)
        return out

    def get_self_healing_circuit_breaker_metrics(self) -> Dict[str, Any]:
        with self._conn() as conn:
            total = int((conn.execute("SELECT COUNT(*) FROM self_healing_circuit_breakers").fetchone() or [0])[0])
            state_rows = conn.execute(
                "SELECT state, COUNT(*) AS n FROM self_healing_circuit_breakers GROUP BY state"
            ).fetchall()
            state_counts = {str(r["state"]): int(r["n"]) for r in state_rows}

            component_rows = conn.execute(
                """SELECT component, COUNT(*) AS n
                   FROM self_healing_circuit_breakers
                   WHERE state=?
                   GROUP BY component""",
                (SelfHealingCircuitBreakerState.OPEN,),
            ).fetchall()
            open_by_component = {str(r["component"]): int(r["n"]) for r in component_rows}

            top_trip_rows = conn.execute(
                """SELECT breaker_key, component, signal, state, failure_streak, trip_count, opened_until, updated_at
                   FROM self_healing_circuit_breakers
                   ORDER BY trip_count DESC, updated_at DESC
                   LIMIT 5"""
            ).fetchall()
            top_tripped = [dict(r) for r in top_trip_rows]

        return {
            "breakers_total": total,
            "state_counts": state_counts,
            "open_breakers": state_counts.get(SelfHealingCircuitBreakerState.OPEN, 0),
            "open_by_component": open_by_component,
            "top_tripped": top_tripped,
        }

    def update_goal_state(
        self,
        goal_id: str,
        *,
        progress: Optional[float] = None,
        last_task_id: Optional[str] = None,
        last_event: Optional[str] = None,
        metrics: Optional[Dict[str, Any]] = None,
        status: Optional[str] = None,
    ) -> None:
        now = datetime.now().isoformat()
        target_status: Optional[str] = None
        with self._conn() as conn:
            # Row sicherstellen
            conn.execute(
                """INSERT INTO goal_state (goal_id, progress, updated_at)
                   VALUES (?, 0.0, ?)
                   ON CONFLICT(goal_id) DO NOTHING""",
                (goal_id, now),
            )
            current = conn.execute(
                "SELECT progress, last_task_id, last_event, metrics_json FROM goal_state WHERE goal_id=?",
                (goal_id,),
            ).fetchone()
            if not current:
                return

            new_progress = float(current["progress"])
            if progress is not None:
                new_progress = max(0.0, min(100.0, float(progress)))

            if metrics is None:
                metrics_json = current["metrics_json"]
            else:
                metrics_json = json.dumps(metrics, ensure_ascii=True)

            conn.execute(
                """UPDATE goal_state
                   SET progress=?, last_task_id=?, last_event=?, metrics_json=?, updated_at=?
                   WHERE goal_id=?""",
                (
                    new_progress,
                    last_task_id if last_task_id is not None else current["last_task_id"],
                    last_event if last_event is not None else current["last_event"],
                    metrics_json,
                    now,
                    goal_id,
                ),
            )

            if status is not None:
                target_status = _normalize_goal_status(status)
            elif progress is not None and new_progress >= 100.0:
                target_status = GoalStatus.COMPLETED

        if target_status is not None:
            self.transition_goal_status(goal_id, target_status, reason="update_goal_state")
            if last_event is not None:
                with self._conn() as conn:
                    conn.execute(
                        "UPDATE goal_state SET last_event=?, updated_at=? WHERE goal_id=?",
                        (last_event, datetime.now().isoformat(), goal_id),
                    )

    def refresh_goal_progress(
        self,
        goal_id: str,
        last_task_id: Optional[str] = None,
        last_event: str = "task_status_update",
    ) -> Optional[float]:
        if not goal_id:
            return None
        with self._conn() as conn:
            row = conn.execute(
                """SELECT COUNT(*) as total,
                          SUM(CASE WHEN status='completed' THEN 1 ELSE 0 END) as done
                   FROM tasks
                   WHERE goal_id=?""",
                (goal_id,),
            ).fetchone()
        if not row:
            return None

        total = int(row["total"] or 0)
        done = int(row["done"] or 0)
        progress = 0.0 if total == 0 else round((done / total) * 100.0, 2)
        metrics = {"tasks_total": total, "tasks_completed": done}
        self.update_goal_state(
            goal_id,
            progress=progress,
            last_task_id=last_task_id,
            last_event=last_event,
            metrics=metrics,
        )
        return progress

    def _ensure_goal_for_task(
        self,
        description: str,
        source: str = "task_queue_auto",
    ) -> Optional[str]:
        clean = (description or "").strip()
        if not clean:
            return None
        title = clean if len(clean) <= 140 else f"{clean[:137].rstrip()}..."
        return self.upsert_goal_from_signal(
            title=title,
            source=source,
            priority_score=0.5,
            status=GoalStatus.ACTIVE,
        )

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
        goal_id: Optional[str] = None,
    ) -> str:
        """
        Fügt einen Task hinzu. Gibt die Task-ID zurück.
        run_at: ISO-8601 Zeitpunkt (z.B. '2026-02-22T09:00:00') für Erinnerungen.
                Tasks mit run_at werden erst ab diesem Zeitpunkt ausgeführt.
        """
        if goal_id is None and _goals_feature_enabled():
            goal_id = self._ensure_goal_for_task(description)

        task_id = str(uuid.uuid4())
        now = datetime.now().isoformat()
        with self._conn() as conn:
            conn.execute(
                """INSERT INTO tasks
                   (id, description, priority, task_type, target_agent, goal_id,
                    status, retry_count, max_retries, created_at, run_at, metadata)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    task_id,
                    description,
                    priority,
                    task_type,
                    target_agent,
                    goal_id,
                    TaskStatus.PENDING,
                    0,
                    max_retries,
                    now,
                    run_at,
                    metadata,
                ),
            )
        when = f" | fällig: {run_at[:16]}" if run_at else ""
        goal_txt = f" | goal={goal_id[:8]}" if goal_id else ""
        log.info(f"Task hinzugefügt [{task_id[:8]}] prio={priority}{when}{goal_txt}: {description[:60]}")
        if goal_id:
            self.refresh_goal_progress(goal_id, last_task_id=task_id, last_event="task_created")
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

def migrate_from_json(queue: TaskQueue, json_path: Path = Path(__file__).parent.parent / "tasks.json") -> int:
    """
    Importiert bestehende tasks.json-Einträge in die SQLite-Queue.
    Überspringt bereits vorhandene IDs. Gibt Anzahl migrierter Tasks zurück.
    """
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
                       (id, description, priority, task_type, target_agent, goal_id,
                        status, retry_count, max_retries, created_at,
                        completed_at, result, error)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        task_id,
                        t.get("description", ""),
                        priority,
                        TaskType.MANUAL,
                        t.get("target_agent"),
                        t.get("goal_id"),
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
