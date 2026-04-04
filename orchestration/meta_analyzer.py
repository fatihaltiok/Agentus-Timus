"""
orchestration/meta_analyzer.py

Schicht 3 — Zeitbasierte Meta-Analyse des Autonomie-Zustands.
Das konfigurierte Planning-/Meta-Modell analysiert 24h Scorecard-History +
letzte Incidents und speichert Erkenntnisse als canvas_store-Event.
"""

from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime
from typing import Any, Dict, List

import httpx

from orchestration.task_queue import TaskQueue, get_queue
from utils.dashscope_native import (
    build_dashscope_native_payload,
    dashscope_native_generation_url,
    extract_dashscope_native_reasoning,
    extract_dashscope_native_text,
)

log = logging.getLogger("MetaAnalyzer")


class MetaAnalyzer:
    """Erkennt Trends und strukturelle Schwächen im Autonomie-Zustand."""

    def __init__(self, queue: TaskQueue | None = None):
        self.queue = queue or get_queue()

    def run_analysis(self) -> Dict[str, Any]:
        """Haupteinstieg: Daten sammeln, LLM aufrufen, Ergebnis speichern."""
        try:
            history = self._get_scorecard_history(hours=24)
            incidents = self._get_recent_incidents(limit=15)
            # M12: Self-Improvement Befunde als zusätzlichen Input einbeziehen
            improvement_context = self._get_improvement_context()
            insights = self._call_llm(
                history=history,
                incidents=incidents,
                improvement_context=improvement_context,
            )
            if insights:
                self._store_insights(insights)
            return {"status": "ok", "insights": insights, "analyzed_at": datetime.now().isoformat()}
        except Exception as e:
            log.warning("Meta-Analyse fehlgeschlagen (nicht kritisch): %s", e)
            return {"status": "error", "error": str(e)}

    def _get_improvement_context(self) -> str:
        """M12: Lädt kritische Self-Improvement Befunde für Meta-Analyse."""
        try:
            import os
            if not os.getenv("AUTONOMY_SELF_IMPROVEMENT_ENABLED", "false").lower() in {"true", "1", "yes"}:
                return ""
            from orchestration.self_improvement_engine import get_improvement_engine
            suggestions = get_improvement_engine().get_suggestions(applied=False)
            critical = [s for s in suggestions if s.get("severity") == "high"][:5]
            if not critical:
                return ""
            lines = ["Kritische Self-Improvement Befunde:"]
            for s in critical:
                lines.append(f"- [{s['type']}:{s['target']}] {s['finding'][:120]}")
            return "\n".join(lines)
        except Exception:
            return ""

    # ------------------------------------------------------------------
    # Datensammlung
    # ------------------------------------------------------------------

    def _get_scorecard_history(self, hours: int = 24) -> List[Dict[str, Any]]:
        rows = self.queue.list_autonomy_scorecard_snapshots(window_hours=hours, limit=50)
        result = []
        for row in rows:
            pillars_raw = row.get("pillars")
            pillars = {}
            if isinstance(pillars_raw, str):
                try:
                    pillars = json.loads(pillars_raw)
                except Exception:
                    pass
            elif isinstance(pillars_raw, dict):
                pillars = pillars_raw
            result.append({
                "created_at": str(row.get("created_at", "")),
                "overall_score": float(row.get("overall_score") or 0.0),
                "autonomy_level": str(row.get("autonomy_level") or "low"),
                "pillars": {
                    k: round(float(v.get("score", 0) if isinstance(v, dict) else 0), 1)
                    for k, v in pillars.items()
                },
            })
        return result

    def _get_recent_incidents(self, limit: int = 15) -> List[Dict[str, Any]]:
        rows = self.queue.list_self_healing_incidents(limit=limit)
        result = []
        for row in rows:
            result.append({
                "incident_key": str(row.get("incident_key", "")),
                "component": str(row.get("component", "")),
                "signal": str(row.get("signal", "")),
                "severity": str(row.get("severity", "")),
                "status": str(row.get("status", "")),
                "title": str(row.get("title", "")),
                "first_seen_at": str(row.get("first_seen_at", "")),
            })
        return result

    # ------------------------------------------------------------------
    # LLM-Aufruf
    # ------------------------------------------------------------------

    def _call_llm(
        self,
        history: List[Dict[str, Any]],
        incidents: List[Dict[str, Any]],
        improvement_context: str = "",
    ) -> Dict[str, Any]:
        from agent.providers import (
            ModelProvider,
            get_provider_client,
            resolve_model_provider_env,
        )

        model, provider = resolve_model_provider_env(
            model_env="PLANNING_MODEL",
            provider_env="PLANNING_MODEL_PROVIDER",
            fallback_model="z-ai/glm-5",
            fallback_provider=ModelProvider.OPENROUTER,
        )
        if provider not in {
            ModelProvider.OPENAI,
            ModelProvider.ZAI,
            ModelProvider.DASHSCOPE,
            ModelProvider.DASHSCOPE_NATIVE,
            ModelProvider.DEEPSEEK,
            ModelProvider.INCEPTION,
            ModelProvider.NVIDIA,
            ModelProvider.OPENROUTER,
        }:
            log.debug(
                "Meta-Analyse uebersprungen: planning provider '%s' ist hier nicht openai-kompatibel",
                provider.value,
            )
            return {}
        history_summary = json.dumps(history[-10:], ensure_ascii=False)
        incidents_summary = json.dumps(incidents, ensure_ascii=False)

        improvement_section = ""
        if improvement_context:
            improvement_section = f"\n\n{improvement_context}"

        prompt = (
            "Du bist ein Autonomie-Analyst für das KI-System Timus.\n"
            "Analysiere die folgenden Daten und antworte NUR mit validem JSON.\n\n"
            f"Scorecard-Verlauf (letzte 10 Snapshots):\n{history_summary}\n\n"
            f"Letzte Incidents (bis 15):\n{incidents_summary}"
            f"{improvement_section}\n\n"
            "Antworte mit genau diesem JSON-Schema (keine weiteren Erklärungen):\n"
            '{"trend": "rising|stable|falling", '
            '"weakest_pillar": "planning|goals|self_healing|policy", '
            '"key_insight": "2-3 Sätze über aktuellen Zustand", '
            '"action_suggestion": "Konkrete Empfehlung für nächsten Zyklus", '
            '"risk_level": "low|medium|high"}'
        )

        if provider == ModelProvider.DASHSCOPE_NATIVE:
            provider_client = get_provider_client()
            api_key = provider_client.get_api_key(ModelProvider.DASHSCOPE_NATIVE)
            base_url = provider_client.get_base_url(ModelProvider.DASHSCOPE_NATIVE)
            payload = build_dashscope_native_payload(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.2,
                max_tokens=400,
            )
            with httpx.Client(timeout=float(os.getenv("DASHSCOPE_NATIVE_TIMEOUT", "60"))) as http:
                response = http.post(
                    dashscope_native_generation_url(base_url, model),
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                )
                response.raise_for_status()
                response_payload = response.json()
            raw = extract_dashscope_native_text(response_payload) or extract_dashscope_native_reasoning(response_payload)
        else:
            client = get_provider_client().get_client(provider)
            response = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.2,
                max_tokens=400,
            )
            raw = (response.choices[0].message.content or "").strip()
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if match:
            return json.loads(match.group(0))
        return {}

    # ------------------------------------------------------------------
    # Persistenz
    # ------------------------------------------------------------------

    def _store_insights(self, insights: Dict[str, Any]) -> None:
        try:
            from orchestration.canvas_store import canvas_store

            items = canvas_store.list_canvases(limit=1).get("items", [])
            if not items:
                return
            canvas_id = str(items[0].get("id", ""))
            if not canvas_id:
                return
            canvas_store.add_event(
                canvas_id=canvas_id,
                event_type="meta_analysis",
                status="info",
                message=(
                    f"meta-analysis trend={insights.get('trend','?')} "
                    f"risk={insights.get('risk_level','?')} "
                    f"weakest={insights.get('weakest_pillar','?')}"
                ),
                payload=insights,
            )
        except Exception as e:
            log.debug("Meta-Analyse canvas_store-Speicherung fehlgeschlagen: %s", e)
