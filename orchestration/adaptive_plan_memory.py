"""Persistent learned-chain memory for goal-first adaptive planning."""

from __future__ import annotations

import json
import os
import sqlite3
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

MEMORY_DB_PATH = Path(
    os.getenv(
        "ADAPTIVE_PLAN_MEMORY_DB_PATH",
        str(Path(__file__).resolve().parents[1] / "data" / "timus_memory.db"),
    )
)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS adaptive_plan_outcomes (
    id                     TEXT PRIMARY KEY,
    goal_signature         TEXT NOT NULL,
    task_type              TEXT NOT NULL DEFAULT '',
    site_kind              TEXT NOT NULL DEFAULT '',
    recipe_id              TEXT NOT NULL DEFAULT '',
    recommended_chain      TEXT NOT NULL DEFAULT '[]',
    final_chain            TEXT NOT NULL DEFAULT '[]',
    success                INTEGER NOT NULL DEFAULT 0,
    runtime_gap_insertions TEXT NOT NULL DEFAULT '[]',
    duration_ms            INTEGER NOT NULL DEFAULT 0,
    confidence             REAL NOT NULL DEFAULT 0.0,
    failure_stage_id       TEXT NOT NULL DEFAULT '',
    switch_reason          TEXT NOT NULL DEFAULT '',
    created_at             TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_adaptive_plan_goal_signature
    ON adaptive_plan_outcomes(goal_signature, created_at DESC);
"""


def normalize_chain(chain: Iterable[str]) -> Tuple[str, ...]:
    cleaned: List[str] = []
    for item in chain:
        agent = str(item or "").strip().lower()
        if agent and agent not in cleaned:
            cleaned.append(agent)
    return tuple(cleaned)


def normalize_runtime_gap_insertions(values: Iterable[str]) -> Tuple[str, ...]:
    cleaned: List[str] = []
    for item in values:
        reason = str(item or "").strip().lower()
        if reason and reason not in cleaned:
            cleaned.append(reason)
    return tuple(cleaned)


def learned_chain_confidence(evidence_count: int) -> float:
    safe_count = max(0, int(evidence_count))
    return min(1.0, safe_count / 3.0)


def learned_chain_bias(
    success_count: int,
    failure_count: int,
    runtime_gap_count: int,
    evidence_count: int,
) -> float:
    safe_evidence = max(0, int(evidence_count))
    if safe_evidence <= 0:
        return 0.0
    safe_success = max(0, int(success_count))
    safe_failure = max(0, int(failure_count))
    safe_gap = max(0, int(runtime_gap_count))
    confidence = learned_chain_confidence(safe_evidence)
    balance = (safe_success - safe_failure) / safe_evidence
    gap_penalty = min(0.04, (safe_gap / safe_evidence) * 0.04)
    raw = (0.18 * balance * confidence) - gap_penalty
    return max(-0.22, min(0.22, raw))


def _ensure_tables(db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(str(db_path)) as conn:
        conn.executescript(_SCHEMA)
        conn.commit()


@dataclass
class AdaptivePlanOutcome:
    goal_signature: str
    task_type: str = ""
    site_kind: str = ""
    recipe_id: str = ""
    recommended_chain: Tuple[str, ...] = field(default_factory=tuple)
    final_chain: Tuple[str, ...] = field(default_factory=tuple)
    success: bool = False
    runtime_gap_insertions: Tuple[str, ...] = field(default_factory=tuple)
    duration_ms: int = 0
    confidence: float = 0.0
    failure_stage_id: str = ""
    switch_reason: str = ""
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    id: str = field(default_factory=lambda: str(uuid.uuid4()))


class AdaptivePlanMemory:
    def __init__(self, db_path: Path = MEMORY_DB_PATH):
        self.db_path = Path(db_path)

    def record_outcome(
        self,
        *,
        goal_signature: str,
        task_type: str = "",
        site_kind: str = "",
        recipe_id: str = "",
        recommended_chain: Iterable[str] = (),
        final_chain: Iterable[str] = (),
        success: bool,
        runtime_gap_insertions: Iterable[str] = (),
        duration_ms: int = 0,
        confidence: float = 0.0,
        failure_stage_id: str = "",
        switch_reason: str = "",
    ) -> AdaptivePlanOutcome:
        _ensure_tables(self.db_path)
        outcome = AdaptivePlanOutcome(
            goal_signature=str(goal_signature or "").strip()[:160],
            task_type=str(task_type or "").strip().lower()[:80],
            site_kind=str(site_kind or "").strip().lower()[:40],
            recipe_id=str(recipe_id or "").strip().lower()[:80],
            recommended_chain=normalize_chain(recommended_chain),
            final_chain=normalize_chain(final_chain),
            success=bool(success),
            runtime_gap_insertions=normalize_runtime_gap_insertions(runtime_gap_insertions),
            duration_ms=max(0, int(duration_ms)),
            confidence=max(0.0, min(0.99, float(confidence or 0.0))),
            failure_stage_id=str(failure_stage_id or "").strip().lower()[:80],
            switch_reason=str(switch_reason or "").strip()[:120],
        )
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.execute(
                """
                INSERT INTO adaptive_plan_outcomes (
                    id,
                    goal_signature,
                    task_type,
                    site_kind,
                    recipe_id,
                    recommended_chain,
                    final_chain,
                    success,
                    runtime_gap_insertions,
                    duration_ms,
                    confidence,
                    failure_stage_id,
                    switch_reason,
                    created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    outcome.id,
                    outcome.goal_signature,
                    outcome.task_type,
                    outcome.site_kind,
                    outcome.recipe_id,
                    json.dumps(list(outcome.recommended_chain), ensure_ascii=True),
                    json.dumps(list(outcome.final_chain), ensure_ascii=True),
                    1 if outcome.success else 0,
                    json.dumps(list(outcome.runtime_gap_insertions), ensure_ascii=True),
                    outcome.duration_ms,
                    outcome.confidence,
                    outcome.failure_stage_id,
                    outcome.switch_reason,
                    outcome.created_at,
                ),
            )
            conn.commit()
        return outcome

    def get_goal_chain_stats(self, goal_signature: str, *, limit: int = 6) -> List[Dict[str, Any]]:
        normalized_signature = str(goal_signature or "").strip()
        if not normalized_signature or not self.db_path.exists():
            return []
        try:
            with sqlite3.connect(str(self.db_path)) as conn:
                conn.row_factory = sqlite3.Row
                rows = conn.execute(
                    """
                    SELECT final_chain, success, runtime_gap_insertions, duration_ms, created_at
                    FROM adaptive_plan_outcomes
                    WHERE goal_signature = ?
                    ORDER BY created_at DESC
                    LIMIT 200
                    """,
                    (normalized_signature,),
                ).fetchall()
        except sqlite3.OperationalError:
            return []

        aggregates: Dict[Tuple[str, ...], Dict[str, Any]] = {}
        for row in rows:
            try:
                chain = normalize_chain(json.loads(row["final_chain"] or "[]"))
            except Exception:
                chain = ()
            if not chain:
                continue
            bucket = aggregates.setdefault(
                chain,
                {
                    "chain": list(chain),
                    "evidence_count": 0,
                    "success_count": 0,
                    "failure_count": 0,
                    "runtime_gap_count": 0,
                    "duration_sum_ms": 0,
                    "last_seen_at": "",
                },
            )
            bucket["evidence_count"] += 1
            if int(row["success"] or 0):
                bucket["success_count"] += 1
            else:
                bucket["failure_count"] += 1
            try:
                bucket["runtime_gap_count"] += len(json.loads(row["runtime_gap_insertions"] or "[]"))
            except Exception:
                bucket["runtime_gap_count"] += 0
            bucket["duration_sum_ms"] += max(0, int(row["duration_ms"] or 0))
            bucket["last_seen_at"] = max(str(bucket["last_seen_at"] or ""), str(row["created_at"] or ""))

        results: List[Dict[str, Any]] = []
        for bucket in aggregates.values():
            evidence_count = int(bucket["evidence_count"])
            success_count = int(bucket["success_count"])
            failure_count = int(bucket["failure_count"])
            runtime_gap_count = int(bucket["runtime_gap_count"])
            learned_bias_value = learned_chain_bias(
                success_count=success_count,
                failure_count=failure_count,
                runtime_gap_count=runtime_gap_count,
                evidence_count=evidence_count,
            )
            results.append(
                {
                    "chain": list(bucket["chain"]),
                    "evidence_count": evidence_count,
                    "success_count": success_count,
                    "failure_count": failure_count,
                    "success_rate": round(success_count / max(1, evidence_count), 2),
                    "runtime_gap_rate": round(runtime_gap_count / max(1, evidence_count), 2),
                    "avg_duration_ms": int(bucket["duration_sum_ms"] / max(1, evidence_count)),
                    "learned_confidence": round(learned_chain_confidence(evidence_count), 2),
                    "learned_bias": round(learned_bias_value, 2),
                    "last_seen_at": bucket["last_seen_at"],
                }
            )
        results.sort(
            key=lambda item: (
                -float(item["learned_bias"]),
                -float(item["success_rate"]),
                -int(item["evidence_count"]),
                len(item["chain"]),
                tuple(item["chain"]),
            )
        )
        return results[: max(1, int(limit))]


_adaptive_plan_memory_instance: Optional[AdaptivePlanMemory] = None


def get_adaptive_plan_memory() -> AdaptivePlanMemory:
    global _adaptive_plan_memory_instance
    if _adaptive_plan_memory_instance is None:
        _adaptive_plan_memory_instance = AdaptivePlanMemory()
    return _adaptive_plan_memory_instance
