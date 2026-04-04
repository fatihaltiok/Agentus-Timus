"""
DeepResearchAgent — Tiefenrecherche, Faktenprüfung, strukturierte Reports.

Erweiterungen gegenüber BaseAgent:
  - Kontext: Aktive Ziele (Recherche fokussieren), Blackboard (Duplikat vermeiden),
    letzte CuriosityEngine-Topics
  - DeepResearch-Loop ist env-konfigurierbar, Default 24 Iterationen
  - Bounded multi-pass workflow statt starrem 3-Schritt-Schema
  - _call_tool-Override: session_id automatisch weiterreichen (unverändert)
  - Kompakter Kontext — Research produziert selbst viele Tokens
"""

from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

import httpx

from agent.base_agent import BaseAgent
from agent.prompts import DEEP_RESEARCH_PROMPT_TEMPLATE
from agent.shared.delegation_handoff import DelegationHandoff, parse_delegation_handoff
from tools.deep_research.research_contracts import is_german_state_affiliated_url

log = logging.getLogger("DeepResearchAgent")


DEFAULT_DEEP_RESEARCH_MAX_ITERATIONS = 24
MIN_DEEP_RESEARCH_MAX_ITERATIONS = 6
MAX_DEEP_RESEARCH_MAX_ITERATIONS = 48


@dataclass(frozen=True)
class DeepResearchLoopLimits:
    max_iterations: int
    max_research_passes: int
    max_report_attempts: int


def normalize_deep_research_max_iterations(
    raw_value: str | None,
    *,
    default: int = DEFAULT_DEEP_RESEARCH_MAX_ITERATIONS,
    minimum: int = MIN_DEEP_RESEARCH_MAX_ITERATIONS,
    maximum: int = MAX_DEEP_RESEARCH_MAX_ITERATIONS,
) -> int:
    """Normalisiert das Iterationsbudget auf sichere, begrenzte Integer-Werte."""
    text = str(raw_value or "").strip()
    if not text:
        return default
    try:
        parsed = int(text)
    except (TypeError, ValueError):
        return default
    return max(minimum, min(maximum, parsed))


def resolve_deep_research_loop_limits(raw_value: str | None) -> DeepResearchLoopLimits:
    """
    Leitet aus dem Iterationsbudget sichere Workflow-Grenzen ab.

    24 Iterationen erlauben mehrere gezielte Recherche-Paesse, halten aber
    genug Reserve fuer Parse-Reparaturen, Report-Retries und Finalisierung.
    """
    max_iterations = normalize_deep_research_max_iterations(raw_value)
    max_research_passes = max(1, min(3, max_iterations // 8))
    max_report_attempts = 2 if max_iterations >= 12 else 1
    return DeepResearchLoopLimits(
        max_iterations=max_iterations,
        max_research_passes=max_research_passes,
        max_report_attempts=max_report_attempts,
    )


def build_deep_research_system_prompt(loop_limits: DeepResearchLoopLimits) -> str:
    return (
        DEEP_RESEARCH_PROMPT_TEMPLATE
        .replace("{deep_research_max_iterations}", str(loop_limits.max_iterations))
        .replace(
            "{deep_research_max_research_passes}",
            str(loop_limits.max_research_passes),
        )
        .replace(
            "{deep_research_max_report_attempts}",
            str(loop_limits.max_report_attempts),
        )
    )


class DeepResearchAgent(BaseAgent):
    """
    Tiefenrecherche-Agent von Timus (deepseek-reasoner).

    Führt strukturierte Recherchen mit start_deep_research,
    verify_fact und generate_research_report durch.
    Lädt vor jedem Task aktive Ziele und Blackboard-Wissen
    um Duplikate zu vermeiden und den Fokus zu schärfen.
    """

    def __init__(self, tools_description_string: str) -> None:
        loop_limits = self._runtime_loop_limits()
        super().__init__(
            build_deep_research_system_prompt(loop_limits),
            tools_description_string,
            max_iterations=loop_limits.max_iterations,
            agent_type="deep_research",
        )
        self.http_client = httpx.AsyncClient(timeout=600.0)
        self.current_session_id: Optional[str] = None
        self.loop_limits = loop_limits

    @classmethod
    def _runtime_loop_limits(cls) -> DeepResearchLoopLimits:
        return resolve_deep_research_loop_limits(
            os.getenv("DEEP_RESEARCH_MAX_ITERATIONS")
        )

    @staticmethod
    def _max_retry_attempts() -> int:
        raw = str(os.getenv("RESEARCH_RUN_MAX_RETRIES", "2")).strip()
        try:
            return max(1, int(raw))
        except ValueError:
            return 2

    @staticmethod
    def _retry_backoff_seconds(attempt: int, base_seconds: float | None = None) -> float:
        base = base_seconds
        if base is None:
            raw = str(os.getenv("RESEARCH_RETRY_BACKOFF_BASE_SECONDS", "1.0")).strip()
            try:
                base = float(raw)
            except ValueError:
                base = 1.0
        safe_base = max(0.1, float(base))
        safe_attempt = max(1, int(attempt))
        return round(safe_base * (2 ** (safe_attempt - 1)), 2)

    @classmethod
    def _is_retryable_result_text(cls, result: str) -> bool:
        text = str(result or "").strip()
        if not text:
            return True
        lowered = text.lower()
        if lowered.startswith("error:"):
            if cls._is_retryable_provider_error_text(lowered):
                return True
            return "empty result" in lowered or "leeres ergebnis" in lowered
        return "empty result" in lowered or "leeres ergebnis" in lowered

    @classmethod
    def _is_retryable_run_exception(cls, error: Exception) -> bool:
        return cls._is_retryable_provider_error(error) or isinstance(error, asyncio.TimeoutError)

    @staticmethod
    def _retry_hint(reason: str, attempt: int, max_attempts: int) -> str:
        return (
            "# RETRY-HINWEIS\n"
            f"Vorheriger Versuch endete mit einem temporaeren Fehler ({reason}). "
            f"Retry {attempt}/{max_attempts}. "
            "Nutze die Research-Tools direkt, vermeide leere Antworten und liefere im Zweifel "
            "ein ehrliches Partial statt leerem Output."
        )

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
        handoff = parse_delegation_handoff(task)
        # original_user_task ist das eigentliche Recherche-Thema (z.B. "KI Industrie Roboter").
        # handoff.goal ist das generische Delegationsziel ("Recherchiere externe Fakten...").
        # Das LLM bekommt original_user_task als primären Task damit es weiß WAS zu recherchieren ist.
        original = (handoff.handoff_data.get("original_user_task") or "") if handoff else ""
        effective_task = original.strip() or (handoff.goal if handoff and handoff.goal else task)
        context = await self._build_research_context(effective_task)
        handoff_context = self._build_delegation_research_context(handoff)

        parts = [effective_task]
        if context:
            parts.append(context)
        if handoff_context:
            parts.append(handoff_context)
        enriched_task = "\n\n".join(part for part in parts if part)

        max_attempts = self._max_retry_attempts()
        for attempt in range(1, max_attempts + 1):
            attempt_task = enriched_task
            if attempt > 1:
                attempt_task = (
                    f"{enriched_task}\n\n"
                    f"{self._retry_hint('transient_failure', attempt, max_attempts)}"
                )
            try:
                result = await super().run(attempt_task)
            except Exception as exc:
                if attempt < max_attempts and self._is_retryable_run_exception(exc):
                    delay = self._retry_backoff_seconds(attempt)
                    log.warning(
                        "Research-Retry %s/%s nach Exception: %s | backoff=%ss",
                        attempt,
                        max_attempts,
                        exc,
                        delay,
                    )
                    await asyncio.sleep(delay)
                    continue
                raise

            if attempt < max_attempts and self._is_retryable_result_text(result):
                delay = self._retry_backoff_seconds(attempt)
                log.warning(
                    "Research-Retry %s/%s nach retryablem Ergebnis: %s | backoff=%ss",
                    attempt,
                    max_attempts,
                    str(result or "")[:160],
                    delay,
                )
                await asyncio.sleep(delay)
                continue
            return result

        return ""

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

        # 2. Blackboard — bereits bekannte Infos zum Thema (mit echtem Thema suchen, nicht Handoff-Boilerplate)
        bb = await asyncio.to_thread(self._get_blackboard_for_task, task)
        if bb:
            lines.append(f"Bereits bekannt zu ANDEREM Thema (NUR nutzen wenn thematisch passend, sonst ignorieren): {bb}")
            has_content = True

        # 3. Letzte Curiosity-Topics
        curiosity = await asyncio.to_thread(self._get_recent_curiosity_topics)
        if curiosity:
            lines.append(f"Aktuelle Interessensgebiete: {curiosity}")
            has_content = True

        lines.append(f"Aktuelle Zeit: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

        # Kontext nur zurückgeben wenn er echten Inhalt hat
        return "\n".join(lines) if has_content else ""

    def _build_delegation_research_context(self, handoff: Optional[DelegationHandoff]) -> str:
        if not handoff:
            return ""

        lines: list[str] = ["# STRUKTURIERTER RESEARCH-HANDOFF"]
        # original_user_task als ERSTES ausgeben — das ist das eigentliche Recherche-Thema
        original_user_task = handoff.handoff_data.get("original_user_task", "")
        if original_user_task:
            lines.append(f"RECHERCHE-THEMA (original_user_task): {original_user_task}")
        if handoff.expected_output:
            lines.append(f"Erwarteter Output: {handoff.expected_output}")
        if handoff.success_signal:
            lines.append(f"Erfolgssignal: {handoff.success_signal}")
        if handoff.constraints:
            lines.append("Constraints: " + " | ".join(handoff.constraints))

        for key, label in (
            ("recipe_id", "Rezept"),
            ("stage_id", "Stage"),
            ("source_urls", "Quell-URLs"),
            ("captured_context", "Bereits erfasster Kontext"),
            ("previous_stage_result", "Vorheriges Stage-Ergebnis"),
            ("previous_blackboard_key", "Blackboard-Key"),
        ):
            value = handoff.handoff_data.get(key)
            if value:
                lines.append(f"{label}: {value}")
        return "\n".join(lines)

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

            # Echtes Thema als Suchquery (task ist hier bereits effective_task = original_user_task)
            query = task[:80].strip()
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

            if is_german_state_affiliated_url(url):
                score -= 1.5
                s["source_policy_flag"] = "german_state_affiliated"

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
                "SELECT topic FROM curiosity_sent ORDER BY sent_at DESC LIMIT 3"
            )
            topics = [row[0] for row in cur.fetchall() if row[0]]
            conn.close()
            return " | ".join(t[:40] for t in topics) if topics else ""
        except Exception as exc:
            log.debug("Curiosity-Topics nicht abrufbar: %s", exc)
            return ""
