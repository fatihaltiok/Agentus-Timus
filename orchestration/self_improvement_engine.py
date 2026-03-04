"""
orchestration/self_improvement_engine.py — M12: Self-Improvement Engine

Analysiert Tool-Nutzung und Routing-Entscheidungen.
Findet Bottlenecks und schlägt Verbesserungen vor.

Feature-Flag: AUTONOMY_SELF_IMPROVEMENT_ENABLED=false
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

log = logging.getLogger("SelfImprovementEngine")

DB_PATH = Path(__file__).resolve().parents[1] / "data" / "task_queue.db"

MIN_SAMPLES = int(os.getenv("IMPROVEMENT_MIN_SAMPLES", "10"))
ANALYSIS_DAYS = int(os.getenv("SELF_IMPROVEMENT_ANALYSIS_DAYS", "7"))

_SCHEMA_EXTENSION = """
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

CREATE INDEX IF NOT EXISTS idx_tool_analytics_tool
    ON tool_analytics (tool_name, timestamp DESC);

CREATE TABLE IF NOT EXISTS routing_analytics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_hash TEXT NOT NULL,
    chosen_agent TEXT NOT NULL,
    outcome TEXT NOT NULL DEFAULT 'success',
    confidence REAL DEFAULT 0.5,
    timestamp TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_routing_analytics_agent
    ON routing_analytics (chosen_agent, timestamp DESC);

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

CREATE INDEX IF NOT EXISTS idx_improvement_suggestions_severity
    ON improvement_suggestions_m12 (severity, created_at DESC);
"""


def _ensure_tables(db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(str(db_path)) as conn:
        conn.executescript(_SCHEMA_EXTENSION)
        conn.commit()


# ──────────────────────────────────────────────────────────────────
# Dataclasses
# ──────────────────────────────────────────────────────────────────

@dataclass
class ToolUsageRecord:
    tool_name: str
    agent: str
    task_type: str = ""
    success: bool = True
    duration_ms: int = 0
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class RoutingRecord:
    task_hash: str
    chosen_agent: str
    outcome: str = "success"   # "success" | "partial" | "error"
    confidence: float = 0.5
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class ImprovementReport:
    suggestions: List[dict] = field(default_factory=list)
    tool_stats: List[dict] = field(default_factory=list)
    routing_stats: dict = field(default_factory=dict)
    analyzed_at: str = field(default_factory=lambda: datetime.now().isoformat())
    critical_count: int = 0


# ──────────────────────────────────────────────────────────────────
# SelfImprovementEngine
# ──────────────────────────────────────────────────────────────────

class SelfImprovementEngine:
    """
    Analysiert Tool-Nutzung und Routing für kontinuierliche Verbesserung.
    """

    def __init__(self, db_path: Path = DB_PATH):
        self.db_path = db_path
        _ensure_tables(db_path)
        self._last_analysis: Optional[datetime] = None

    # ------------------------------------------------------------------
    # Aufzeichnung
    # ------------------------------------------------------------------

    def record_tool_usage(self, record: ToolUsageRecord) -> None:
        """Speichert einen Tool-Nutzungs-Datenpunkt."""
        try:
            with sqlite3.connect(str(self.db_path)) as conn:
                conn.execute(
                    """INSERT INTO tool_analytics
                       (tool_name, agent, task_type, success, duration_ms, timestamp)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (
                        record.tool_name,
                        record.agent,
                        record.task_type,
                        int(record.success),
                        record.duration_ms,
                        record.timestamp,
                    ),
                )
                conn.commit()
        except Exception as e:
            log.debug("record_tool_usage: %s", e)

    def record_routing(self, record: RoutingRecord) -> None:
        """Speichert eine Routing-Entscheidung."""
        try:
            with sqlite3.connect(str(self.db_path)) as conn:
                conn.execute(
                    """INSERT INTO routing_analytics
                       (task_hash, chosen_agent, outcome, confidence, timestamp)
                       VALUES (?, ?, ?, ?, ?)""",
                    (
                        record.task_hash,
                        record.chosen_agent,
                        record.outcome,
                        record.confidence,
                        record.timestamp,
                    ),
                )
                conn.commit()
        except Exception as e:
            log.debug("record_routing: %s", e)

    # ------------------------------------------------------------------
    # Analyse
    # ------------------------------------------------------------------

    async def run_analysis_cycle(self) -> ImprovementReport:
        """
        Wöchentliche Analyse: Tool-Erfolgsraten, Routing-Konfidenz, Bottlenecks.

        Returns:
            ImprovementReport mit Befunden und Suggestions
        """
        report = ImprovementReport()

        try:
            cutoff = (datetime.now() - timedelta(days=ANALYSIS_DAYS)).isoformat()

            tool_stats = self.get_tool_stats(days=ANALYSIS_DAYS)
            routing_stats = self.get_routing_stats(days=ANALYSIS_DAYS)

            report.tool_stats = tool_stats
            report.routing_stats = routing_stats

            suggestions = []

            # 1. Tool-Erfolgsrate < 70% → Suggestion
            for stat in tool_stats:
                total = stat.get("total", 0)
                if total < MIN_SAMPLES:
                    continue
                success_rate = stat.get("success_rate", 1.0)
                if success_rate < 0.70:
                    suggestions.append({
                        "type": "tool",
                        "target": stat["tool_name"],
                        "finding": (
                            f"Tool '{stat['tool_name']}' bei Agent '{stat['agent']}': "
                            f"Erfolgsrate nur {int(success_rate*100)}% ({total} Aufrufe)"
                        ),
                        "suggestion": (
                            f"Tool '{stat['tool_name']}' überprüfen oder durch Alternative ersetzen. "
                            f"Häufige Fehler analysieren."
                        ),
                        "confidence": 0.8,
                        "severity": "high" if success_rate < 0.50 else "medium",
                    })

            # 2. Routing-Konfidenz < 0.6 für Agent → Suggestion
            agent_confidence = routing_stats.get("by_agent", {})
            for agent, stats in agent_confidence.items():
                total = stats.get("total", 0)
                if total < MIN_SAMPLES:
                    continue
                avg_conf = stats.get("avg_confidence", 1.0)
                if avg_conf < 0.6:
                    suggestions.append({
                        "type": "routing",
                        "target": agent,
                        "finding": (
                            f"Routing zu Agent '{agent}': Ø-Konfidenz nur {avg_conf:.2f} "
                            f"({total} Entscheidungen)"
                        ),
                        "suggestion": (
                            f"Routing-Regeln für '{agent}' verfeinern. "
                            "Keyword-Matching oder LLM-Prompt anpassen."
                        ),
                        "confidence": 0.7,
                        "severity": "medium",
                    })

            # 3. Bottleneck-Tools (>3s Ø-Dauer bei success) → Hinweis
            for stat in tool_stats:
                avg_ms = stat.get("avg_duration_ms", 0)
                if avg_ms > 3000 and stat.get("success_rate", 0) > 0.8:
                    suggestions.append({
                        "type": "tool",
                        "target": stat["tool_name"],
                        "finding": (
                            f"Tool '{stat['tool_name']}': Ø-Laufzeit {avg_ms:.0f}ms "
                            "(möglicher Bottleneck)"
                        ),
                        "suggestion": "Caching, asynchrone Verarbeitung oder Timeout-Optimierung prüfen.",
                        "confidence": 0.6,
                        "severity": "low",
                    })

            # Suggestions speichern
            for s in suggestions:
                self._save_suggestion(s)

            report.suggestions = suggestions
            report.critical_count = sum(1 for s in suggestions if s.get("severity") == "high")

            # Telegram bei kritischen Befunden
            if report.critical_count > 0:
                await self._send_telegram(report)

            self._last_analysis = datetime.now()
            log.info(
                "🔬 Self-Improvement: %d Befunde (%d kritisch)",
                len(suggestions),
                report.critical_count,
            )

        except Exception as e:
            log.warning("run_analysis_cycle: %s", e)

        return report

    def _should_run_analysis(self) -> bool:
        """Prüft ob eine Wochenanalyse fällig ist."""
        if not self._last_analysis:
            return True
        return (datetime.now() - self._last_analysis) > timedelta(days=ANALYSIS_DAYS)

    # ------------------------------------------------------------------
    # Abfragen
    # ------------------------------------------------------------------

    def get_tool_stats(self, agent: Optional[str] = None, days: int = 7) -> List[dict]:
        """Gibt Tool-Statistiken zurück."""
        try:
            cutoff = (datetime.now() - timedelta(days=days)).isoformat()
            with sqlite3.connect(str(self.db_path)) as conn:
                if agent:
                    rows = conn.execute(
                        """SELECT tool_name, agent,
                                  COUNT(*) as total,
                                  AVG(success) as success_rate,
                                  AVG(duration_ms) as avg_duration_ms
                           FROM tool_analytics
                           WHERE agent = ? AND timestamp >= ?
                           GROUP BY tool_name, agent
                           ORDER BY total DESC""",
                        (agent, cutoff),
                    ).fetchall()
                else:
                    rows = conn.execute(
                        """SELECT tool_name, agent,
                                  COUNT(*) as total,
                                  AVG(success) as success_rate,
                                  AVG(duration_ms) as avg_duration_ms
                           FROM tool_analytics
                           WHERE timestamp >= ?
                           GROUP BY tool_name, agent
                           ORDER BY total DESC""",
                        (cutoff,),
                    ).fetchall()

            return [
                {
                    "tool_name": r[0],
                    "agent": r[1],
                    "total": r[2],
                    "success_rate": round(float(r[3] or 1.0), 3),
                    "avg_duration_ms": round(float(r[4] or 0), 1),
                }
                for r in rows
            ]
        except Exception as e:
            log.debug("get_tool_stats: %s", e)
            return []

    def get_routing_stats(self, days: int = 7) -> dict:
        """Gibt Routing-Statistiken zurück."""
        try:
            cutoff = (datetime.now() - timedelta(days=days)).isoformat()
            with sqlite3.connect(str(self.db_path)) as conn:
                rows = conn.execute(
                    """SELECT chosen_agent,
                              COUNT(*) as total,
                              AVG(confidence) as avg_confidence,
                              SUM(CASE WHEN outcome = 'success' THEN 1 ELSE 0 END) as successes
                       FROM routing_analytics
                       WHERE timestamp >= ?
                       GROUP BY chosen_agent""",
                    (cutoff,),
                ).fetchall()

                total_row = conn.execute(
                    "SELECT COUNT(*) FROM routing_analytics WHERE timestamp >= ?",
                    (cutoff,),
                ).fetchone()

            by_agent = {}
            for r in rows:
                by_agent[r[0]] = {
                    "total": r[1],
                    "avg_confidence": round(float(r[2] or 0.5), 3),
                    "success_rate": round(r[3] / r[1], 3) if r[1] > 0 else 0.0,
                }

            return {
                "total_decisions": total_row[0] if total_row else 0,
                "by_agent": by_agent,
                "analysis_days": days,
            }
        except Exception as e:
            log.debug("get_routing_stats: %s", e)
            return {"total_decisions": 0, "by_agent": {}, "analysis_days": days}

    def get_suggestions(self, applied: bool = False) -> List[dict]:
        """Gibt Verbesserungsvorschläge zurück."""
        try:
            with sqlite3.connect(str(self.db_path)) as conn:
                rows = conn.execute(
                    """SELECT id, type, target, finding, suggestion,
                              confidence, severity, applied, created_at
                       FROM improvement_suggestions_m12
                       WHERE applied = ?
                       ORDER BY
                           CASE severity WHEN 'high' THEN 0 WHEN 'medium' THEN 1 ELSE 2 END,
                           created_at DESC
                       LIMIT 50""",
                    (int(applied),),
                ).fetchall()
            return [
                {
                    "id": r[0],
                    "type": r[1],
                    "target": r[2],
                    "finding": r[3],
                    "suggestion": r[4],
                    "confidence": r[5],
                    "severity": r[6],
                    "applied": bool(r[7]),
                    "created_at": r[8],
                }
                for r in rows
            ]
        except Exception as e:
            log.debug("get_suggestions: %s", e)
            return []

    # ------------------------------------------------------------------
    # Hilfsmethoden
    # ------------------------------------------------------------------

    def _save_suggestion(self, s: dict) -> None:
        """Speichert Suggestion (kein Duplikat wenn gleicher finding)."""
        try:
            with sqlite3.connect(str(self.db_path)) as conn:
                conn.execute(
                    """INSERT INTO improvement_suggestions_m12
                       (type, target, finding, suggestion, confidence, severity, applied, created_at)
                       VALUES (?, ?, ?, ?, ?, ?, 0, ?)""",
                    (
                        s.get("type", "tool"),
                        s.get("target", ""),
                        s.get("finding", ""),
                        s.get("suggestion", ""),
                        s.get("confidence", 0.5),
                        s.get("severity", "medium"),
                        datetime.now().isoformat(),
                    ),
                )
                conn.commit()
        except Exception as e:
            log.debug("_save_suggestion: %s", e)

    async def _send_telegram(self, report: ImprovementReport) -> None:
        """Telegram-Push bei kritischen Befunden."""
        try:
            lines = [
                f"🔬 *Self-Improvement Analyse*",
                f"{report.critical_count} kritische Befunde",
            ]
            for s in report.suggestions[:3]:
                emoji = "🔴" if s.get("severity") == "high" else "🟡"
                lines.append(f"{emoji} {s.get('finding', '')[:100]}")

            from utils.telegram_notify import send_telegram
            await send_telegram("\n".join(lines))
        except Exception:
            pass


# ──────────────────────────────────────────────────────────────────
# Singleton
# ──────────────────────────────────────────────────────────────────

_engine_instance: Optional[SelfImprovementEngine] = None


def get_improvement_engine(db_path: Path = DB_PATH) -> SelfImprovementEngine:
    global _engine_instance
    if _engine_instance is None:
        _engine_instance = SelfImprovementEngine(db_path)
    return _engine_instance
