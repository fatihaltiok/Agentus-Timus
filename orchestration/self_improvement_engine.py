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

CREATE TABLE IF NOT EXISTS llm_usage_analytics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    trace_id TEXT NOT NULL,
    session_id TEXT DEFAULT '',
    agent TEXT NOT NULL,
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    input_tokens INTEGER NOT NULL DEFAULT 0,
    output_tokens INTEGER NOT NULL DEFAULT 0,
    cached_tokens INTEGER NOT NULL DEFAULT 0,
    cost_usd REAL NOT NULL DEFAULT 0,
    latency_ms INTEGER NOT NULL DEFAULT 0,
    success INTEGER NOT NULL DEFAULT 1,
    timestamp TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_llm_usage_session
    ON llm_usage_analytics (session_id, timestamp DESC);

CREATE INDEX IF NOT EXISTS idx_llm_usage_agent
    ON llm_usage_analytics (agent, timestamp DESC);

CREATE TABLE IF NOT EXISTS conversation_recall_analytics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT DEFAULT '',
    query TEXT NOT NULL,
    source TEXT NOT NULL DEFAULT 'none',
    semantic_candidates INTEGER NOT NULL DEFAULT 0,
    recent_reply_candidates INTEGER NOT NULL DEFAULT 0,
    used_summary INTEGER NOT NULL DEFAULT 0,
    top_agent TEXT DEFAULT '',
    top_role TEXT DEFAULT '',
    top_distance REAL DEFAULT 0.0,
    timestamp TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_conversation_recall_ts
    ON conversation_recall_analytics (timestamp DESC);

CREATE INDEX IF NOT EXISTS idx_conversation_recall_source
    ON conversation_recall_analytics (source, timestamp DESC);
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
    recall_stats: dict = field(default_factory=dict)
    analyzed_at: str = field(default_factory=lambda: datetime.now().isoformat())
    critical_count: int = 0


@dataclass
class LLMUsageRecord:
    trace_id: str
    session_id: str = ""
    agent: str = ""
    provider: str = ""
    model: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    cached_tokens: int = 0
    cost_usd: float = 0.0
    latency_ms: int = 0
    success: bool = True
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class ConversationRecallRecord:
    session_id: str = ""
    query: str = ""
    source: str = "none"  # semantic | recent_assistant | summary | none
    semantic_candidates: int = 0
    recent_reply_candidates: int = 0
    used_summary: bool = False
    top_agent: str = ""
    top_role: str = ""
    top_distance: float = 0.0
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


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

    def record_llm_usage(self, record: LLMUsageRecord) -> None:
        """Speichert LLM-Nutzung fuer Kosten-/Token-Analysen."""
        try:
            with sqlite3.connect(str(self.db_path)) as conn:
                conn.execute(
                    """INSERT INTO llm_usage_analytics
                       (trace_id, session_id, agent, provider, model, input_tokens,
                        output_tokens, cached_tokens, cost_usd, latency_ms, success, timestamp)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        record.trace_id,
                        record.session_id,
                        record.agent,
                        record.provider,
                        record.model,
                        max(int(record.input_tokens or 0), 0),
                        max(int(record.output_tokens or 0), 0),
                        max(int(record.cached_tokens or 0), 0),
                        max(float(record.cost_usd or 0.0), 0.0),
                        max(int(record.latency_ms or 0), 0),
                        int(record.success),
                        record.timestamp,
                    ),
                )
                conn.commit()
        except Exception as e:
            log.debug("record_llm_usage: %s", e)

    def record_conversation_recall(self, record: ConversationRecallRecord) -> None:
        """Speichert Recall-Telemetrie für Folge- und Rückfragen."""
        try:
            with sqlite3.connect(str(self.db_path)) as conn:
                conn.execute(
                    """INSERT INTO conversation_recall_analytics
                       (session_id, query, source, semantic_candidates, recent_reply_candidates,
                        used_summary, top_agent, top_role, top_distance, timestamp)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        record.session_id,
                        record.query,
                        record.source,
                        max(int(record.semantic_candidates or 0), 0),
                        max(int(record.recent_reply_candidates or 0), 0),
                        int(record.used_summary),
                        record.top_agent,
                        record.top_role,
                        max(float(record.top_distance or 0.0), 0.0),
                        record.timestamp,
                    ),
                )
                conn.commit()
        except Exception as e:
            log.debug("record_conversation_recall: %s", e)

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
            recall_stats = self.get_conversation_recall_stats(days=ANALYSIS_DAYS)

            report.tool_stats = tool_stats
            report.routing_stats = routing_stats
            report.recall_stats = recall_stats

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

            # 4. Recall-Qualität (Proxy) -> Suggestion
            total_recall = int(recall_stats.get("total_queries", 0) or 0)
            if total_recall >= MIN_SAMPLES:
                none_rate = float(recall_stats.get("none_rate", 0.0) or 0.0)
                summary_rate = float(recall_stats.get("summary_fallback_rate", 0.0) or 0.0)
                semantic_rate = float(recall_stats.get("semantic_rate", 0.0) or 0.0)
                avg_distance = float(recall_stats.get("avg_top_distance", 0.0) or 0.0)

                if none_rate >= 0.20:
                    suggestions.append({
                        "type": "conversation_recall",
                        "target": "followup_capsule",
                        "finding": (
                            "Konversationeller Recall faellt zu oft komplett aus: "
                            f"{none_rate:.2f} none bei {total_recall} Recall-Queries"
                        ),
                        "suggestion": (
                            "Follow-up Resolver verbreitern und mehr semantische Session-Signale "
                            "in die Recall-Kapsel geben."
                        ),
                        "confidence": 0.78,
                        "severity": "high" if none_rate >= 0.35 else "medium",
                    })
                if summary_rate >= 0.35:
                    suggestions.append({
                        "type": "conversation_recall",
                        "target": "qdrant_ranking",
                        "finding": (
                            "Conversation recall faellt haeufig auf Session-Summary zurueck: "
                            f"{summary_rate:.2f} summary_fallback"
                        ),
                        "suggestion": (
                            "Qdrant-Ranking und Recall-Filter schaerfen, damit fruehere "
                            "Antwortstellen haeufiger vor der generischen Summary landen."
                        ),
                        "confidence": 0.72,
                        "severity": "medium",
                    })
                if semantic_rate < 0.45 and avg_distance > 0.20:
                    suggestions.append({
                        "type": "conversation_recall",
                        "target": "semantic_recall",
                        "finding": (
                            "Semantischer Recall greift selten oder zu unpraezise: "
                            f"semantic_rate {semantic_rate:.2f}, avg_top_distance {avg_distance:.2f}"
                        ),
                        "suggestion": (
                            "Embedding-/Ranking-Gewichte und Query-Normalisierung fuer "
                            "Konversations-Recall ueberarbeiten."
                        ),
                        "confidence": 0.68,
                        "severity": "medium",
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

    def get_llm_usage_summary(
        self,
        *,
        days: int = 7,
        session_id: Optional[str] = None,
        agent: Optional[str] = None,
        limit: int = 5,
    ) -> dict:
        """Aggregierte Token-/Kosten-Sicht fuer Status und Budgeting."""
        try:
            safe_days = max(1, min(90, int(days)))
            safe_limit = max(1, min(20, int(limit)))
            cutoff = (datetime.now() - timedelta(days=safe_days)).isoformat()
            if session_id and agent:
                totals_sql = """
                    SELECT COUNT(*) as total_requests,
                           SUM(CASE WHEN success = 1 THEN 1 ELSE 0 END) as successful_requests,
                           SUM(input_tokens) as input_tokens,
                           SUM(output_tokens) as output_tokens,
                           SUM(cached_tokens) as cached_tokens,
                           SUM(cost_usd) as total_cost_usd,
                           AVG(latency_ms) as avg_latency_ms
                    FROM llm_usage_analytics
                    WHERE timestamp >= ? AND session_id = ? AND agent = ?
                """
                by_agent_sql = """
                    SELECT agent,
                           COUNT(*) as total_requests,
                           SUM(cost_usd) as total_cost_usd,
                           SUM(input_tokens) as input_tokens,
                           SUM(output_tokens) as output_tokens
                    FROM llm_usage_analytics
                    WHERE timestamp >= ? AND session_id = ? AND agent = ?
                    GROUP BY agent
                    ORDER BY total_cost_usd DESC, total_requests DESC
                    LIMIT ?
                """
                by_model_sql = """
                    SELECT provider, model,
                           COUNT(*) as total_requests,
                           SUM(cost_usd) as total_cost_usd,
                           SUM(input_tokens) as input_tokens,
                           SUM(output_tokens) as output_tokens
                    FROM llm_usage_analytics
                    WHERE timestamp >= ? AND session_id = ? AND agent = ?
                    GROUP BY provider, model
                    ORDER BY total_cost_usd DESC, total_requests DESC
                    LIMIT ?
                """
                totals_params: List[Any] = [cutoff, session_id, agent]
                grouped_params: List[Any] = [cutoff, session_id, agent, safe_limit]
            elif session_id:
                totals_sql = """
                    SELECT COUNT(*) as total_requests,
                           SUM(CASE WHEN success = 1 THEN 1 ELSE 0 END) as successful_requests,
                           SUM(input_tokens) as input_tokens,
                           SUM(output_tokens) as output_tokens,
                           SUM(cached_tokens) as cached_tokens,
                           SUM(cost_usd) as total_cost_usd,
                           AVG(latency_ms) as avg_latency_ms
                    FROM llm_usage_analytics
                    WHERE timestamp >= ? AND session_id = ?
                """
                by_agent_sql = """
                    SELECT agent,
                           COUNT(*) as total_requests,
                           SUM(cost_usd) as total_cost_usd,
                           SUM(input_tokens) as input_tokens,
                           SUM(output_tokens) as output_tokens
                    FROM llm_usage_analytics
                    WHERE timestamp >= ? AND session_id = ?
                    GROUP BY agent
                    ORDER BY total_cost_usd DESC, total_requests DESC
                    LIMIT ?
                """
                by_model_sql = """
                    SELECT provider, model,
                           COUNT(*) as total_requests,
                           SUM(cost_usd) as total_cost_usd,
                           SUM(input_tokens) as input_tokens,
                           SUM(output_tokens) as output_tokens
                    FROM llm_usage_analytics
                    WHERE timestamp >= ? AND session_id = ?
                    GROUP BY provider, model
                    ORDER BY total_cost_usd DESC, total_requests DESC
                    LIMIT ?
                """
                totals_params: List[Any] = [cutoff, session_id]
                grouped_params: List[Any] = [cutoff, session_id, safe_limit]
            elif agent:
                totals_sql = """
                    SELECT COUNT(*) as total_requests,
                           SUM(CASE WHEN success = 1 THEN 1 ELSE 0 END) as successful_requests,
                           SUM(input_tokens) as input_tokens,
                           SUM(output_tokens) as output_tokens,
                           SUM(cached_tokens) as cached_tokens,
                           SUM(cost_usd) as total_cost_usd,
                           AVG(latency_ms) as avg_latency_ms
                    FROM llm_usage_analytics
                    WHERE timestamp >= ? AND agent = ?
                """
                by_agent_sql = """
                    SELECT agent,
                           COUNT(*) as total_requests,
                           SUM(cost_usd) as total_cost_usd,
                           SUM(input_tokens) as input_tokens,
                           SUM(output_tokens) as output_tokens
                    FROM llm_usage_analytics
                    WHERE timestamp >= ? AND agent = ?
                    GROUP BY agent
                    ORDER BY total_cost_usd DESC, total_requests DESC
                    LIMIT ?
                """
                by_model_sql = """
                    SELECT provider, model,
                           COUNT(*) as total_requests,
                           SUM(cost_usd) as total_cost_usd,
                           SUM(input_tokens) as input_tokens,
                           SUM(output_tokens) as output_tokens
                    FROM llm_usage_analytics
                    WHERE timestamp >= ? AND agent = ?
                    GROUP BY provider, model
                    ORDER BY total_cost_usd DESC, total_requests DESC
                    LIMIT ?
                """
                totals_params = [cutoff, agent]
                grouped_params = [cutoff, agent, safe_limit]
            else:
                totals_sql = """
                    SELECT COUNT(*) as total_requests,
                           SUM(CASE WHEN success = 1 THEN 1 ELSE 0 END) as successful_requests,
                           SUM(input_tokens) as input_tokens,
                           SUM(output_tokens) as output_tokens,
                           SUM(cached_tokens) as cached_tokens,
                           SUM(cost_usd) as total_cost_usd,
                           AVG(latency_ms) as avg_latency_ms
                    FROM llm_usage_analytics
                    WHERE timestamp >= ?
                """
                by_agent_sql = """
                    SELECT agent,
                           COUNT(*) as total_requests,
                           SUM(cost_usd) as total_cost_usd,
                           SUM(input_tokens) as input_tokens,
                           SUM(output_tokens) as output_tokens
                    FROM llm_usage_analytics
                    WHERE timestamp >= ?
                    GROUP BY agent
                    ORDER BY total_cost_usd DESC, total_requests DESC
                    LIMIT ?
                """
                by_model_sql = """
                    SELECT provider, model,
                           COUNT(*) as total_requests,
                           SUM(cost_usd) as total_cost_usd,
                           SUM(input_tokens) as input_tokens,
                           SUM(output_tokens) as output_tokens
                    FROM llm_usage_analytics
                    WHERE timestamp >= ?
                    GROUP BY provider, model
                    ORDER BY total_cost_usd DESC, total_requests DESC
                    LIMIT ?
                """
                totals_params = [cutoff]
                grouped_params = [cutoff, safe_limit]

            with sqlite3.connect(str(self.db_path)) as conn:
                totals = conn.execute(totals_sql, totals_params).fetchone()

                by_agent_rows = conn.execute(by_agent_sql, grouped_params).fetchall()

                by_model_rows = conn.execute(by_model_sql, grouped_params).fetchall()

            total_requests = int((totals[0] if totals else 0) or 0)
            successful_requests = int((totals[1] if totals else 0) or 0)
            failed_requests = max(total_requests - successful_requests, 0)

            return {
                "analysis_days": safe_days,
                "session_id": session_id or "",
                "agent_filter": agent or "",
                "total_requests": total_requests,
                "successful_requests": successful_requests,
                "failed_requests": failed_requests,
                "success_rate": round(successful_requests / total_requests, 3) if total_requests else 0.0,
                "input_tokens": int((totals[2] if totals else 0) or 0),
                "output_tokens": int((totals[3] if totals else 0) or 0),
                "cached_tokens": int((totals[4] if totals else 0) or 0),
                "total_cost_usd": round(float((totals[5] if totals else 0.0) or 0.0), 6),
                "avg_latency_ms": round(float((totals[6] if totals else 0.0) or 0.0), 1),
                "top_agents": [
                    {
                        "agent": row[0],
                        "total_requests": int(row[1] or 0),
                        "total_cost_usd": round(float(row[2] or 0.0), 6),
                        "input_tokens": int(row[3] or 0),
                        "output_tokens": int(row[4] or 0),
                    }
                    for row in by_agent_rows
                ],
                "top_models": [
                    {
                        "provider": row[0],
                        "model": row[1],
                        "total_requests": int(row[2] or 0),
                        "total_cost_usd": round(float(row[3] or 0.0), 6),
                        "input_tokens": int(row[4] or 0),
                        "output_tokens": int(row[5] or 0),
                    }
                    for row in by_model_rows
                ],
                "top_providers": [
                    {
                        "provider": provider,
                        "total_requests": sum(int(row["total_requests"] or 0) for row in provider_rows),
                        "total_cost_usd": round(sum(float(row["total_cost_usd"] or 0.0) for row in provider_rows), 6),
                        "input_tokens": sum(int(row["input_tokens"] or 0) for row in provider_rows),
                        "output_tokens": sum(int(row["output_tokens"] or 0) for row in provider_rows),
                    }
                    for provider, provider_rows in {
                        provider: [item for item in [
                            {
                                "provider": row[0],
                                "model": row[1],
                                "total_requests": int(row[2] or 0),
                                "total_cost_usd": round(float(row[3] or 0.0), 6),
                                "input_tokens": int(row[4] or 0),
                                "output_tokens": int(row[5] or 0),
                            }
                            for row in by_model_rows
                        ] if item["provider"] == provider]
                        for provider in {str(row[0] or "") for row in by_model_rows}
                    }.items()
                    if provider
                ],
            }
        except Exception as e:
            log.debug("get_llm_usage_summary: %s", e)
            return {
                "analysis_days": days,
                "session_id": session_id or "",
                "agent_filter": agent or "",
                "total_requests": 0,
                "successful_requests": 0,
                "failed_requests": 0,
                "success_rate": 0.0,
                "input_tokens": 0,
                "output_tokens": 0,
                "cached_tokens": 0,
                "total_cost_usd": 0.0,
                "avg_latency_ms": 0.0,
                "top_agents": [],
                "top_models": [],
                "top_providers": [],
            }

    def get_conversation_recall_stats(self, days: int = 7) -> dict:
        """Aggregierte Recall-Telemetrie fuer längere Gespräche."""
        try:
            safe_days = max(1, min(90, int(days)))
            cutoff = (datetime.now() - timedelta(days=safe_days)).isoformat()
            with sqlite3.connect(str(self.db_path)) as conn:
                totals = conn.execute(
                    """SELECT COUNT(*) as total_queries,
                              SUM(CASE WHEN source = 'semantic' THEN 1 ELSE 0 END) as semantic_hits,
                              SUM(CASE WHEN source = 'recent_assistant' THEN 1 ELSE 0 END) as recent_hits,
                              SUM(CASE WHEN source = 'summary' THEN 1 ELSE 0 END) as summary_hits,
                              SUM(CASE WHEN source = 'none' THEN 1 ELSE 0 END) as none_hits,
                              AVG(semantic_candidates) as avg_semantic_candidates,
                              AVG(recent_reply_candidates) as avg_recent_candidates,
                              AVG(top_distance) as avg_top_distance
                       FROM conversation_recall_analytics
                       WHERE timestamp >= ?""",
                    (cutoff,),
                ).fetchone()
                top_sources_rows = conn.execute(
                    """SELECT source, COUNT(*) as total
                       FROM conversation_recall_analytics
                       WHERE timestamp >= ?
                       GROUP BY source
                       ORDER BY total DESC""",
                    (cutoff,),
                ).fetchall()

            total = int((totals[0] if totals else 0) or 0)
            semantic_hits = int((totals[1] if totals else 0) or 0)
            recent_hits = int((totals[2] if totals else 0) or 0)
            summary_hits = int((totals[3] if totals else 0) or 0)
            none_hits = int((totals[4] if totals else 0) or 0)

            return {
                "analysis_days": safe_days,
                "total_queries": total,
                "semantic_hits": semantic_hits,
                "recent_hits": recent_hits,
                "summary_hits": summary_hits,
                "none_hits": none_hits,
                "semantic_rate": round(semantic_hits / total, 3) if total else 0.0,
                "recent_reply_rate": round(recent_hits / total, 3) if total else 0.0,
                "summary_fallback_rate": round(summary_hits / total, 3) if total else 0.0,
                "none_rate": round(none_hits / total, 3) if total else 0.0,
                "avg_semantic_candidates": round(float((totals[5] if totals else 0.0) or 0.0), 3),
                "avg_recent_reply_candidates": round(float((totals[6] if totals else 0.0) or 0.0), 3),
                "avg_top_distance": round(float((totals[7] if totals else 0.0) or 0.0), 3),
                "top_sources": [
                    {"source": str(row[0] or ""), "total": int(row[1] or 0)}
                    for row in top_sources_rows
                ],
            }
        except Exception as e:
            log.debug("get_conversation_recall_stats: %s", e)
            return {
                "analysis_days": days,
                "total_queries": 0,
                "semantic_hits": 0,
                "recent_hits": 0,
                "summary_hits": 0,
                "none_hits": 0,
                "semantic_rate": 0.0,
                "recent_reply_rate": 0.0,
                "summary_fallback_rate": 0.0,
                "none_rate": 0.0,
                "avg_semantic_candidates": 0.0,
                "avg_recent_reply_candidates": 0.0,
                "avg_top_distance": 0.0,
                "top_sources": [],
            }

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

    def mark_suggestion_applied(self, suggestion_id: str, applied: bool = True) -> None:
        """Markiert eine Suggestion als bearbeitet bzw. wieder offen."""
        safe_id = str(suggestion_id or "").strip()
        if not safe_id:
            return
        try:
            with sqlite3.connect(str(self.db_path)) as conn:
                conn.execute(
                    "UPDATE improvement_suggestions_m12 SET applied=? WHERE id=?",
                    (1 if applied else 0, safe_id),
                )
                conn.commit()
        except Exception as e:
            log.debug("mark_suggestion_applied: %s", e)

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
