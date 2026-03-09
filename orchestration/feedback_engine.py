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
from typing import Any, Dict, List, Optional

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

CREATE TABLE IF NOT EXISTS feedback_requests (
    token             TEXT PRIMARY KEY,
    action_id         TEXT NOT NULL,
    hook_names        TEXT NOT NULL DEFAULT '[]',
    context           TEXT NOT NULL DEFAULT '{}',
    feedback_targets  TEXT NOT NULL DEFAULT '[]',
    created_at        TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_feedback_requests_action ON feedback_requests(action_id);

CREATE TABLE IF NOT EXISTS feedback_target_scores (
    namespace      TEXT NOT NULL,
    target_key     TEXT NOT NULL,
    score          REAL NOT NULL DEFAULT 1.0,
    positive_count INTEGER NOT NULL DEFAULT 0,
    negative_count INTEGER NOT NULL DEFAULT 0,
    neutral_count  INTEGER NOT NULL DEFAULT 0,
    updated_at     TEXT NOT NULL,
    PRIMARY KEY (namespace, target_key)
);
"""

VALID_FEEDBACK_SIGNALS = {"positive", "negative", "neutral"}
FEEDBACK_TARGET_MIN = 0.1
FEEDBACK_TARGET_MAX = 3.0
FEEDBACK_TARGET_DELTA = 0.1
FEEDBACK_EFFECTIVE_MIN_EVIDENCE = 5
RUNTIME_FEEDBACK_TARGET_DELTA = float(os.getenv("M16_RUNTIME_FEEDBACK_DELTA", "0.05"))


def clamp_feedback_target_score(value: float) -> float:
    """Clamped Score fuer Dispatcher-/Curiosity-/Visual-/Reflection-Ziele."""
    return max(FEEDBACK_TARGET_MIN, min(FEEDBACK_TARGET_MAX, float(value)))


def next_feedback_target_score(current: float, signal: str, delta: float = FEEDBACK_TARGET_DELTA) -> float:
    """Berechnet den naechsten Zielscore aus aktuellem Score + Signal."""
    safe_delta = max(0.0, float(delta))
    if signal == "positive":
        return clamp_feedback_target_score(current + safe_delta)
    if signal == "negative":
        return clamp_feedback_target_score(current - safe_delta)
    return clamp_feedback_target_score(current)


def feedback_evidence_confidence(evidence_count: int, min_evidence: int = FEEDBACK_EFFECTIVE_MIN_EVIDENCE) -> float:
    """Normalisiert Feedback-Evidenz auf [0,1] fuer konservative Runtime-Biases."""
    safe_min = max(1, int(min_evidence))
    safe_count = max(0, int(evidence_count))
    return min(1.0, safe_count / safe_min)


def normalize_feedback_target(namespace: str, key: str) -> tuple[str, str]:
    """Normalisiert Feedback-Zielnamen fuer DB-Keys und Vergleiche."""
    normalized_namespace = str(namespace or "").strip().lower()[:64]
    normalized_key = str(key or "").strip().lower()[:160]
    return normalized_namespace, normalized_key


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


@dataclass
class FeedbackRequest:
    token: str
    action_id: str
    hook_names: List[str] = field(default_factory=list)
    context: Dict[str, Any] = field(default_factory=dict)
    feedback_targets: List[Dict[str, str]] = field(default_factory=list)
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
        feedback_targets: Optional[List[Dict[str, str]]] = None,
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
        if signal not in VALID_FEEDBACK_SIGNALS:
            raise ValueError(f"Ungültiges Signal: {signal!r}. Erlaubt: positive, negative, neutral")

        merged_context = dict(context or {})
        normalized_targets = self._normalize_feedback_targets(feedback_targets or merged_context.get("feedback_targets"))
        if normalized_targets:
            merged_context["feedback_targets"] = normalized_targets

        event = FeedbackEvent(
            id=str(uuid.uuid4()),
            action_id=action_id,
            signal=signal,
            hook_names=hook_names or [],
            context=merged_context,
        )

        self._save(event)
        log.info("Feedback gespeichert: action=%s signal=%s hooks=%s", action_id, signal, event.hook_names)

        # Hook-Weights aktualisieren (nur wenn hooks angegeben)
        if signal != "neutral" and event.hook_names:
            self._apply_to_hooks(event.hook_names, signal)
        self._apply_to_targets(event)

        return event

    def record_runtime_outcome(
        self,
        action_id: str,
        *,
        success: Optional[bool],
        hook_names: Optional[List[str]] = None,
        context: Optional[Dict[str, Any]] = None,
        feedback_targets: Optional[List[Dict[str, str]]] = None,
    ) -> FeedbackEvent:
        """Speichert gedämpftes implizites Runtime-Feedback aus echten Outcomes."""
        merged_context = dict(context or {})
        merged_context.setdefault("feedback_source", "runtime_outcome")
        merged_context.setdefault("feedback_weight", RUNTIME_FEEDBACK_TARGET_DELTA)
        if success is True:
            signal = "positive"
        elif success is False:
            signal = "negative"
        else:
            signal = "neutral"
        return self.record_signal(
            action_id=action_id,
            signal=signal,
            hook_names=hook_names,
            context=merged_context,
            feedback_targets=feedback_targets,
        )

    def register_feedback_request(
        self,
        action_id: str,
        hook_names: Optional[List[str]] = None,
        context: Optional[Dict[str, Any]] = None,
        feedback_targets: Optional[List[Dict[str, str]]] = None,
    ) -> str:
        """Registriert serverseitige Feedback-Payload und gibt kurzes Token zurueck."""
        request = FeedbackRequest(
            token=uuid.uuid4().hex[:12],
            action_id=str(action_id or "unknown"),
            hook_names=list(hook_names or []),
            context=dict(context or {}),
            feedback_targets=self._normalize_feedback_targets(feedback_targets or []),
        )
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO feedback_requests "
                "(token, action_id, hook_names, context, feedback_targets, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    request.token,
                    request.action_id,
                    json.dumps(request.hook_names, ensure_ascii=False),
                    json.dumps(request.context, ensure_ascii=False),
                    json.dumps(request.feedback_targets, ensure_ascii=False),
                    request.created_at,
                ),
            )
            conn.commit()
        return request.token

    def resolve_feedback_request(self, token: str) -> Optional[FeedbackRequest]:
        """Loest ein kurzes Telegram-Feedback-Token in die volle Payload auf."""
        if not token:
            return None
        try:
            with sqlite3.connect(str(self.db_path)) as conn:
                row = conn.execute(
                    "SELECT token, action_id, hook_names, context, feedback_targets, created_at "
                    "FROM feedback_requests WHERE token = ?",
                    (str(token).strip(),),
                ).fetchone()
            if not row:
                return None
            return FeedbackRequest(
                token=row[0],
                action_id=row[1],
                hook_names=json.loads(row[2] or "[]"),
                context=json.loads(row[3] or "{}"),
                feedback_targets=json.loads(row[4] or "[]"),
                created_at=row[5],
            )
        except Exception as e:
            log.error("resolve_feedback_request fehlgeschlagen: %s", e)
            return None

    def get_target_score(self, namespace: str, target_key: str, default: float = 1.0) -> float:
        """Gibt den aggregierten Feedback-Score fuer ein Zielsystem zurück."""
        ns, key = normalize_feedback_target(namespace, target_key)
        if not ns or not key:
            return clamp_feedback_target_score(default)
        try:
            with sqlite3.connect(str(self.db_path)) as conn:
                row = conn.execute(
                    "SELECT score FROM feedback_target_scores WHERE namespace = ? AND target_key = ?",
                    (ns, key),
                ).fetchone()
            if not row:
                return clamp_feedback_target_score(default)
            return clamp_feedback_target_score(float(row[0]))
        except Exception as e:
            log.error("get_target_score fehlgeschlagen: %s", e)
            return clamp_feedback_target_score(default)

    def get_target_stats(self, namespace: str, target_key: str, default: float = 1.0) -> Dict[str, Any]:
        """Liefert Score + Evidenz fuer ein Zielsystem."""
        ns, key = normalize_feedback_target(namespace, target_key)
        baseline = {
            "namespace": ns,
            "target_key": key,
            "score": clamp_feedback_target_score(default),
            "positive_count": 0,
            "negative_count": 0,
            "neutral_count": 0,
            "evidence_count": 0,
            "updated_at": None,
        }
        if not ns or not key:
            return baseline
        try:
            with sqlite3.connect(str(self.db_path)) as conn:
                row = conn.execute(
                    "SELECT score, positive_count, negative_count, neutral_count, updated_at "
                    "FROM feedback_target_scores WHERE namespace = ? AND target_key = ?",
                    (ns, key),
                ).fetchone()
            if not row:
                return baseline
            pos_count = int(row[1] or 0)
            neg_count = int(row[2] or 0)
            neutral_count = int(row[3] or 0)
            return {
                "namespace": ns,
                "target_key": key,
                "score": clamp_feedback_target_score(float(row[0])),
                "positive_count": pos_count,
                "negative_count": neg_count,
                "neutral_count": neutral_count,
                "evidence_count": pos_count + neg_count + neutral_count,
                "updated_at": row[4],
            }
        except Exception as e:
            log.error("get_target_stats fehlgeschlagen: %s", e)
            return baseline

    def get_effective_target_score(
        self,
        namespace: str,
        target_key: str,
        *,
        default: float = 1.0,
        min_evidence: int = FEEDBACK_EFFECTIVE_MIN_EVIDENCE,
    ) -> float:
        """Daempft rohe Feedback-Scores bis ausreichend Evidenz vorliegt."""
        stats = self.get_target_stats(namespace, target_key, default=default)
        confidence = feedback_evidence_confidence(stats["evidence_count"], min_evidence=min_evidence)
        base = clamp_feedback_target_score(default)
        effective = base + (float(stats["score"]) - base) * confidence
        return clamp_feedback_target_score(effective)

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
                top_rows = conn.execute(
                    "SELECT namespace, target_key, score, positive_count, negative_count, neutral_count "
                    "FROM feedback_target_scores "
                    "ORDER BY ABS(score - 1.0) DESC, updated_at DESC LIMIT 3"
                ).fetchall()
            if top_rows:
                highlights = ", ".join(
                    f"{ns}:{key}={float(score):.2f} (+{int(pos)}/-{int(neg)}/~{int(neutral)})"
                    for ns, key, score, pos, neg, neutral in top_rows
                )
                log.debug("M16 Runtime-Feedback: %s", highlights)
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

    def _normalize_feedback_targets(self, feedback_targets: Optional[List[Dict[str, Any]]]) -> List[Dict[str, str]]:
        normalized: List[Dict[str, str]] = []
        for item in feedback_targets or []:
            if not isinstance(item, dict):
                continue
            namespace, key = normalize_feedback_target(item.get("namespace", ""), item.get("key", ""))
            if not namespace or not key:
                continue
            normalized.append({"namespace": namespace, "key": key})
        return normalized

    def _extract_feedback_targets(self, event: FeedbackEvent) -> List[Dict[str, str]]:
        context = event.context if isinstance(event.context, dict) else {}
        derived: List[Dict[str, str]] = []

        explicit = self._normalize_feedback_targets(context.get("feedback_targets"))
        if explicit:
            derived.extend(explicit)

        topic = context.get("topic")
        if topic:
            namespace, key = normalize_feedback_target("curiosity_topic", str(topic))
            if namespace and key:
                derived.append({"namespace": namespace, "key": key})

        dispatcher_agent = (
            context.get("dispatcher_agent")
            or context.get("selected_agent")
            or context.get("agent")
        )
        if dispatcher_agent:
            namespace, key = normalize_feedback_target("dispatcher_agent", str(dispatcher_agent))
            if namespace and key:
                derived.append({"namespace": namespace, "key": key})

        visual_strategy = context.get("visual_strategy")
        if visual_strategy:
            namespace, key = normalize_feedback_target("visual_strategy", str(visual_strategy))
            if namespace and key:
                derived.append({"namespace": namespace, "key": key})

        reflection_pattern = context.get("reflection_pattern") or context.get("pattern")
        if reflection_pattern:
            namespace, key = normalize_feedback_target("reflection_pattern", str(reflection_pattern))
            if namespace and key:
                derived.append({"namespace": namespace, "key": key})

        unique: dict[tuple[str, str], Dict[str, str]] = {}
        for item in derived:
            unique[(item["namespace"], item["key"])] = item
        return list(unique.values())

    def _apply_to_targets(self, event: FeedbackEvent) -> None:
        if event.signal not in VALID_FEEDBACK_SIGNALS:
            return
        try:
            with sqlite3.connect(str(self.db_path)) as conn:
                now = datetime.now().isoformat()
                context = event.context if isinstance(event.context, dict) else {}
                delta = float(context.get("feedback_weight", FEEDBACK_TARGET_DELTA) or FEEDBACK_TARGET_DELTA)
                for item in self._extract_feedback_targets(event):
                    namespace = item["namespace"]
                    key = item["key"]
                    row = conn.execute(
                        "SELECT score, positive_count, negative_count, neutral_count "
                        "FROM feedback_target_scores WHERE namespace = ? AND target_key = ?",
                        (namespace, key),
                    ).fetchone()
                    current = float(row[0]) if row else 1.0
                    pos_count = int(row[1]) if row else 0
                    neg_count = int(row[2]) if row else 0
                    neutral_count = int(row[3]) if row else 0

                    next_score = next_feedback_target_score(current, event.signal, delta=delta)
                    if event.signal == "positive":
                        pos_count += 1
                    elif event.signal == "negative":
                        neg_count += 1
                    else:
                        neutral_count += 1

                    conn.execute(
                        "INSERT OR REPLACE INTO feedback_target_scores "
                        "(namespace, target_key, score, positive_count, negative_count, neutral_count, updated_at) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?)",
                        (namespace, key, next_score, pos_count, neg_count, neutral_count, now),
                    )
                conn.commit()
        except Exception as e:
            log.warning("Zielsystem-Feedback konnte nicht angewendet werden: %s", e)


# ------------------------------------------------------------------
# Singleton
# ------------------------------------------------------------------

_engine: Optional[FeedbackEngine] = None


def get_feedback_engine() -> FeedbackEngine:
    global _engine
    if _engine is None:
        _engine = FeedbackEngine()
    return _engine
