"""
DeepResearchAgent — Tiefenrecherche, Faktenprüfung, strukturierte Reports.

Erweiterungen gegenüber BaseAgent:
  - Kontext: Aktive Ziele (Recherche fokussieren), Blackboard (Duplikat vermeiden),
    letzte CuriosityEngine-Topics
  - max_iterations=8 bleibt (Research-Tools übernehmen die Schwerarbeit)
  - _call_tool-Override: session_id automatisch weiterreichen (unverändert)
  - Kompakter Kontext — Research produziert selbst viele Tokens
"""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime
from typing import Optional

import httpx

from agent.base_agent import BaseAgent
from agent.prompts import DEEP_RESEARCH_PROMPT_TEMPLATE

log = logging.getLogger("DeepResearchAgent")


class DeepResearchAgent(BaseAgent):
    """
    Tiefenrecherche-Agent von Timus (deepseek-reasoner).

    Führt strukturierte Recherchen mit start_deep_research,
    verify_fact und generate_research_report durch.
    Lädt vor jedem Task aktive Ziele und Blackboard-Wissen
    um Duplikate zu vermeiden und den Fokus zu schärfen.
    """

    def __init__(self, tools_description_string: str) -> None:
        super().__init__(
            DEEP_RESEARCH_PROMPT_TEMPLATE,
            tools_description_string,
            max_iterations=6,   # 3 Schritte nötig (start → report → final), 6 = sicherer Puffer
            agent_type="deep_research",
        )
        self.http_client = httpx.AsyncClient(timeout=600.0)
        self.current_session_id: Optional[str] = None

    # ------------------------------------------------------------------
    # _call_tool-Override: session_id automatisch weiterreichen
    # (Original-Logik unverändert)
    # ------------------------------------------------------------------

    @staticmethod
    def _effective_report_params(params: dict, current_session_id: Optional[str]) -> dict:
        effective = dict(params or {})
        if current_session_id:
            effective.setdefault("session_id", current_session_id)
        return effective

    async def _call_tool(self, method: str, params: dict) -> dict:
        if method == "generate_research_report" and self.current_session_id:
            params = self._effective_report_params(params, self.current_session_id)
        result = await super()._call_tool(method, params)
        if isinstance(result, dict) and "session_id" in result:
            self.current_session_id = result["session_id"]
        elif isinstance(result, dict):
            metadata = result.get("metadata")
            if isinstance(metadata, dict) and metadata.get("session_id"):
                self.current_session_id = metadata["session_id"]
        return result

    # ------------------------------------------------------------------
    # Erweiterter run()-Einstieg: Recherche-Kontext injizieren
    # ------------------------------------------------------------------

    async def run(self, task: str) -> str:
        """Reichert den Task mit Zielen und Blackboard-Vorwissen an."""
        context = await self._build_research_context(task)
        if context:
            enriched_task = task + "\n\n" + context
        else:
            enriched_task = task
        return await super().run(enriched_task)

    # ------------------------------------------------------------------
    # Recherche-Kontext aufbauen (kompakt — Research produziert viele Tokens)
    # ------------------------------------------------------------------

    async def _build_research_context(self, task: str) -> str:
        """
        Erstellt kompakten Kontext für den Research-Agent:
        - Aktive Ziele (Recherche auf relevante Themen fokussieren)
        - Blackboard-Einträge (bereits bekanntes Wissen, Duplikat-Schutz)
        - Letzte CuriosityEngine-Topics (Verbindung zu laufenden Interessen)
        - Aktuelle Zeit
        """
        lines: list[str] = ["# RECHERCHE-KONTEXT (automatisch geladen)"]
        has_content = False

        # 1. Aktive Ziele — Research soll ziel-relevant sein
        goals = await asyncio.to_thread(self._get_active_goals)
        if goals:
            lines.append(f"Aktive Timus-Ziele (Recherche darauf ausrichten): {goals}")
            has_content = True

        # 2. Blackboard — bereits bekannte Infos zum Thema
        bb = await asyncio.to_thread(self._get_blackboard_for_task, task)
        if bb:
            lines.append(f"Bereits bekannt (Blackboard, Duplikat vermeiden): {bb}")
            has_content = True

        # 3. Letzte Curiosity-Topics
        curiosity = await asyncio.to_thread(self._get_recent_curiosity_topics)
        if curiosity:
            lines.append(f"Aktuelle Interessensgebiete: {curiosity}")
            has_content = True

        lines.append(f"Aktuelle Zeit: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

        # Kontext nur zurückgeben wenn er echten Inhalt hat
        return "\n".join(lines) if has_content else ""

    def _get_active_goals(self) -> str:
        """Lädt aktive Ziele aus dem GoalQueueManager (M11)."""
        if not os.getenv("AUTONOMY_GOAL_QUEUE_ENABLED", "true").lower() == "true":
            return ""
        try:
            from orchestration.goal_queue_manager import GoalQueueManager

            tree = GoalQueueManager().get_goal_tree()
            active = [
                g["title"] for g in tree
                if g.get("status") in ("active", "in_progress", "pending")
            ][:3]
            return " | ".join(active) if active else ""
        except Exception as exc:
            log.debug("GoalQueueManager nicht abrufbar: %s", exc)
            return ""

    def _get_blackboard_for_task(self, task: str) -> str:
        """Sucht relevante Blackboard-Einträge zum aktuellen Task."""
        if not os.getenv("AUTONOMY_BLACKBOARD_ENABLED", "true").lower() == "true":
            return ""
        try:
            from memory.agent_blackboard import get_blackboard

            # Erste 60 Zeichen des Tasks als Suchquery
            query = task[:60].strip()
            entries = get_blackboard().search(query, limit=2)
            if not entries:
                return ""
            parts = []
            for e in entries:
                agent = e.get("agent", "?")
                key   = e.get("key", "")
                value = str(e.get("value", ""))[:80]
                parts.append(f"[{agent}:{key}] {value}")
            return " | ".join(parts)
        except Exception as exc:
            log.debug("Blackboard nicht abrufbar: %s", exc)
            return ""

    # ------------------------------------------------------------------
    # 3a: Source-Ranking + Duplikat-Filter (Phase 3)
    # ------------------------------------------------------------------

    MAX_RANKING_SCORE = 10  # Lean: research_ranking_score_bound

    _HIGH_AUTHORITY_DOMAINS = frozenset({
        "arxiv.org", "nature.com", "science.org", "github.com",
        "openai.com", "anthropic.com", "deepmind.com", "huggingface.co",
        "ieee.org", "acm.org", "springer.com", "semanticscholar.org",
    })

    @staticmethod
    def _normalize_url(url: str) -> str:
        """Entfernt Query-Parameter und Trailing Slashes für Duplikat-Vergleich."""
        url = (url or "").strip().lower()
        for prefix in ("https://", "http://", "www."):
            if url.startswith(prefix):
                url = url[len(prefix):]
        return url.split("?")[0].rstrip("/")

    @classmethod
    def _deduplicate_sources(cls, sources: list) -> list:
        """
        Entfernt Duplikate anhand normalisierter URL.
        unique_count ≤ total_count — Lean Th.45: research_dedup_bound

        Args:
            sources: Liste von Dicts mit mindestens {'url': str}
        Returns:
            Deduplizierte Liste (unique ≤ len(sources))
        """
        seen: set = set()
        unique: list = []
        for s in sources:
            key = cls._normalize_url(s.get("url", "") or s.get("link", ""))
            if key and key not in seen:
                seen.add(key)
                unique.append(s)
            elif not key:
                unique.append(s)  # Ohne URL immer behalten
        return unique

    @classmethod
    def _rank_sources(cls, sources: list) -> list:
        """
        Berechnet Ranking-Score ∈ [0, 10] für jede Quelle.
        Lean Th.46: research_ranking_score_bound: 0 ≤ max 0 (min 10 score) ≤ 10

        Score-Bestandteile:
          +2 High-Authority-Domain (arxiv, nature, github, …)
          +2 Verifiziert / relevance_score ≥ 0.8
          +1 Aktualität (published_year >= aktuelles Jahr - 1)
          Rest: Basis-Score aus relevance_score × 5
        """
        from datetime import datetime
        current_year = datetime.now().year

        result = []
        for s in sources:
            score = 0.0
            url = (s.get("url") or s.get("link") or "").lower()

            # Domain-Autorität
            for domain in cls._HIGH_AUTHORITY_DOMAINS:
                if domain in url:
                    score += 2
                    break

            # Relevanz-Score (0–1) → 0–5
            relevance = float(s.get("relevance_score") or s.get("score") or 0)
            score += relevance * 5

            # Verifizierung
            if s.get("verified") or relevance >= 0.8:
                score += 2

            # Aktualität
            year = s.get("published_year") or s.get("year")
            try:
                if year and int(year) >= current_year - 1:
                    score += 1
            except (ValueError, TypeError):
                pass

            # Clamp [0, MAX_RANKING_SCORE]
            s["ranking_score"] = max(0, min(cls.MAX_RANKING_SCORE, round(score, 2)))
            result.append(s)

        return sorted(result, key=lambda x: x["ranking_score"], reverse=True)

    def _get_recent_curiosity_topics(self) -> str:
        """Gibt die letzten Curiosity-Topics aus der DB zurück."""
        try:
            import sqlite3
            from pathlib import Path

            db_path = Path(__file__).resolve().parents[2] / "data" / "timus_memory.db"
            if not db_path.exists():
                return ""
            conn = sqlite3.connect(str(db_path))
            cur = conn.execute(
                "SELECT query FROM curiosity_sent ORDER BY sent_at DESC LIMIT 3"
            )
            topics = [row[0] for row in cur.fetchall() if row[0]]
            conn.close()
            return " | ".join(t[:40] for t in topics) if topics else ""
        except Exception as exc:
            log.debug("Curiosity-Topics nicht abrufbar: %s", exc)
            return ""
