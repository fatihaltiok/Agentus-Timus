"""
MetaAgent — Koordinator mit Skill-Orchestrierung + Autonomie-Kontext.

Erweiterungen gegenüber BaseAgent:
  - Kontext: Aktive Ziele, offene Tasks, Blackboard, letzte Reflexion, Trigger
  - max_iterations=30 für mehrstufige Koordinations-Workflows
  - Skill-Orchestrierung: wählt automatisch passende Skills aus skills/
  - create_visual_plan(): Nemotron-gestützte Browser-Planung
  - Partial-Result-Erkennung mit Koordinator-Hinweis
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from agent.base_agent import BaseAgent
from agent.prompts import META_SYSTEM_PROMPT

log = logging.getLogger("TimusAgent-v4.4")


from agent.shared.json_utils import extract_json_robust  # noqa: F401 - re-exported


class MetaAgent(BaseAgent):
    # Koordinator darf Spezialisten-Tools NIE direkt aufrufen — nur per Delegation.
    SYSTEM_ONLY_TOOLS = BaseAgent.SYSTEM_ONLY_TOOLS | {
        "run_command",
        "run_script",
        "add_cron",
    }

    def __init__(self, tools_description_string: str):
        super().__init__(META_SYSTEM_PROMPT, tools_description_string, 30, "meta")

        self.skill_registry = None
        self.active_skills: list = []
        self._init_skill_system()

    # ------------------------------------------------------------------
    # Skill-System
    # ------------------------------------------------------------------

    def _init_skill_system(self):
        try:
            from utils.skill_types import SkillRegistry

            self.skill_registry = SkillRegistry()

            skills_base = Path(__file__).parent.parent.parent / "skills"
            if skills_base.exists():
                self.skill_registry.load_all_from_directory(skills_base)
                log.info(f"MetaAgent: {len(self.skill_registry.skills)} Skills geladen")
            else:
                log.warning(f"MetaAgent: Skill-Verzeichnis nicht gefunden: {skills_base}")

        except Exception as e:
            log.error(f"MetaAgent: Fehler beim Initialisieren des Skill-Systems: {e}")
            self.skill_registry = None

    def _select_skills_for_task(self, task: str, top_k: int = 3) -> List:
        if not self.skill_registry:
            return []

        selected = self.skill_registry.select_for_task(task, top_k=top_k)

        if selected:
            log.info(f"MetaAgent: {len(selected)} Skill(s) fuer Task ausgewaehlt:")
            for skill in selected:
                log.info(f"   - {skill.name}")

        return selected

    def _build_skill_context(self, skills: List, include_references: bool = False) -> str:
        if not skills:
            return ""

        context_parts = ["\n# AVAILABLE SKILLS\n"]

        for skill in skills:
            if include_references:
                refs = list(skill.get_references().keys())
                skill_context = skill.get_full_context(include_references=refs)
            else:
                skill_context = skill.get_full_context()

            context_parts.append(skill_context)
            context_parts.append("\n---\n")

        context_parts.append("\n# INSTRUCTIONS\n")
        context_parts.append("Use the above skills when appropriate for this task.")
        context_parts.append("Follow the skill instructions and use provided scripts/references.")

        return "\n".join(context_parts)

    # ------------------------------------------------------------------
    # Erweiterter run()-Einstieg: Timus-Kontext + Skills injizieren
    # ------------------------------------------------------------------

    async def run(self, task: str) -> str:
        log.info(f"MetaAgent mit Kontext + Skill-Orchestrierung: {task[:50]}...")

        # 1. Timus Autonomie-Kontext laden
        meta_context = await self._build_meta_context()

        # 2. Skills auswählen
        self.active_skills = self._select_skills_for_task(task, top_k=3)
        skill_context = self._build_skill_context(self.active_skills, include_references=False)

        # 3. Task anreichern
        parts: list[str] = []
        if meta_context:
            parts.append(meta_context)
        if skill_context:
            parts.append(skill_context)
        parts.append(f"# AUFGABE\n{task}")
        if skill_context:
            parts.append("Prüfe ob verfügbare Skills zur Aufgabe passen und nutze sie entsprechend.")

        enhanced_task = "\n\n".join(parts)

        result = await super().run(enhanced_task)

        # Partial-Result-Erkennung
        _partial_markers = {"Limit erreicht.", "Max Iterationen."}
        if result in _partial_markers:
            log.warning(
                f"MetaAgent: Ergebnis ist partiell ('{result}') — "
                "Aufgabe moeglicherweise nicht vollstaendig abgeschlossen."
            )
            return result + "\n\n_(Koordinator-Hinweis: Ergebnis unvollstaendig)_"

        return result

    # ------------------------------------------------------------------
    # Timus Autonomie-Kontext aufbauen
    # ------------------------------------------------------------------

    async def _build_meta_context(self) -> str:
        """
        Erstellt Kontext für den Meta-Agent:
        - Aktive Langzeit-Ziele (M11 GoalQueueManager)
        - Offene Tasks in der Queue (TaskQueue)
        - Blackboard-Zusammenfassung (M9 AgentBlackboard)
        - Letzte Reflexion (M8 SessionReflectionLoop)
        - Aktive Proaktive Trigger (M10)
        - Verfügbare Agenten
        - Aktuelle Zeit
        """
        lines: list[str] = ["# TIMUS SYSTEM-KONTEXT (automatisch geladen)"]

        # 1. Aktive Ziele (M11)
        goals_ctx = await asyncio.to_thread(self._get_active_goals)
        if goals_ctx:
            lines.append(f"Aktive Langzeit-Ziele: {goals_ctx}")

        # 2. Offene Tasks in Queue
        tasks_ctx = await asyncio.to_thread(self._get_pending_tasks)
        if tasks_ctx:
            lines.append(f"Offene Tasks: {tasks_ctx}")

        # 3. Blackboard-Zusammenfassung (M9)
        bb_ctx = await asyncio.to_thread(self._get_blackboard_summary)
        if bb_ctx:
            lines.append(f"Agent-Blackboard: {bb_ctx}")

        # 4. Letzte Reflexion (M8)
        reflection_ctx = await self._get_last_reflection()
        if reflection_ctx:
            lines.append(f"Letzte Reflexion: {reflection_ctx}")

        # 5. Aktive Trigger (M10)
        trigger_ctx = await asyncio.to_thread(self._get_active_triggers)
        if trigger_ctx:
            lines.append(f"Aktive Routinen: {trigger_ctx}")

        # 6. Verfügbare Agenten
        lines.append(
            "Agenten: executor, research, reasoning, creative, developer, "
            "meta, visual, data, document, communication, system, shell, image"
        )

        lines.append(f"Aktuelle Zeit: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

        return "\n".join(lines)

    def _get_active_goals(self) -> str:
        """Lädt aktive Ziele aus dem GoalQueueManager (M11)."""
        if not os.getenv("AUTONOMY_GOAL_QUEUE_ENABLED", "true").lower() == "true":
            return ""
        try:
            from orchestration.goal_queue_manager import GoalQueueManager
            mgr = GoalQueueManager()
            tree = mgr.get_goal_tree()
            if not tree:
                return ""
            active = [
                g for g in tree
                if g.get("status") in ("active", "in_progress", "pending")
            ][:5]
            if not active:
                return ""
            parts = []
            for g in active:
                progress = int(g.get("progress", 0) * 100)
                parts.append(f"{g['title']} ({progress}%)")
            return " | ".join(parts)
        except Exception as exc:
            log.debug("GoalQueueManager nicht verfügbar: %s", exc)
            return ""

    def _get_pending_tasks(self) -> str:
        """Gibt offene Tasks aus der TaskQueue zurück."""
        try:
            from orchestration.task_queue import TaskQueue
            tq = TaskQueue()
            pending = tq.get_pending()[:5]
            if not pending:
                return "0 offen"
            parts = []
            for t in pending:
                desc = (t.get("description") or t.get("title") or "Task")[:40]
                agent = t.get("agent_type") or "?"
                parts.append(f"{desc} [{agent}]")
            return f"{len(pending)} offen: " + " | ".join(parts)
        except Exception as exc:
            log.debug("TaskQueue nicht verfügbar: %s", exc)
            return ""

    def _get_blackboard_summary(self) -> str:
        """Fasst den AgentBlackboard zusammen (M9)."""
        if not os.getenv("AUTONOMY_BLACKBOARD_ENABLED", "true").lower() == "true":
            return ""
        try:
            from memory.agent_blackboard import get_blackboard
            summary = get_blackboard().get_summary()
            total = summary.get("total_active", 0)
            if not total:
                return ""
            by_agent = summary.get("by_agent", {})
            agent_parts = [f"{a}:{c}" for a, c in list(by_agent.items())[:4]]
            return f"{total} Einträge ({', '.join(agent_parts)})"
        except Exception as exc:
            log.debug("AgentBlackboard nicht verfügbar: %s", exc)
            return ""

    async def _get_last_reflection(self) -> str:
        """Lädt die letzte Session-Reflexion (M8)."""
        if not os.getenv("AUTONOMY_REFLECTION_ENABLED", "false").lower() == "true":
            return ""
        try:
            from orchestration.session_reflection import SessionReflectionLoop
            loop = SessionReflectionLoop()
            reflections = await loop.get_recent_reflections(limit=1)
            if not reflections:
                return ""
            r = reflections[0]
            success = int(r.get("success_rate", 0) * 100)
            patterns = r.get("patterns_json", "[]")
            import json
            pat_list = json.loads(patterns) if isinstance(patterns, str) else patterns
            top_pattern = pat_list[0] if pat_list else ""
            result = f"Erfolgsrate {success}%"
            if top_pattern:
                result += f", Top-Muster: {str(top_pattern)[:60]}"
            return result
        except Exception as exc:
            log.debug("SessionReflectionLoop nicht verfügbar: %s", exc)
            return ""

    def _get_active_triggers(self) -> str:
        """Listet aktive Proaktive Trigger (M10)."""
        if not os.getenv("AUTONOMY_PROACTIVE_TRIGGERS_ENABLED", "false").lower() == "true":
            return ""
        try:
            from orchestration.proactive_triggers import ProactiveTriggerEngine
            engine = ProactiveTriggerEngine()
            triggers = [t for t in engine.list_triggers() if t.get("enabled")]
            if not triggers:
                return ""
            parts = [f"{t['name']} ({t['time_of_day']})" for t in triggers[:4]]
            return " | ".join(parts)
        except Exception as exc:
            log.debug("ProactiveTriggerEngine nicht verfügbar: %s", exc)
            return ""

    # ------------------------------------------------------------------
    # Visual-Plan-Erstellung (Nemotron-gestützt)
    # ------------------------------------------------------------------

    async def create_visual_plan(self, task: str) -> dict:
        """Erstellt einen strukturierten Plan für Visual/Browser-Tasks.

        Diese Methode analysiert den Task und erstellt eine Schritt-für-Schritt
        Roadmap mit konkreten Aktionen (URL öffnen, Elemente finden, etc.)

        Returns:
            Dict mit: goal, url, steps (Liste von Actions mit verification)
        """
        log.info(f"MetaAgent: Erstelle Visual-Plan für: {task[:60]}...")

        plan_prompt = f"""Erstelle einen DETAILLIERTEN Plan für diese Browser-Automatisierung:

AUFGABE: {task}

Analysiere:
1. Welche URL muss zuerst geöffnet werden?
2. Was sind die konkreten Schritte (in Reihenfolge)?
3. Welche Elemente müssen gefunden/klicked werden?
4. Was ist die erwartete Ergebnis-Überprüfung?

Gib den Plan in diesem JSON-Format zurück:
{{
  "goal": "Kurze Zusammenfassung des Ziels",
  "url": "https://... (Start-URL)",
  "steps": [
    {{
      "step_number": 1,
      "action": "navigate|click|type|scroll|wait|verify",
      "description": "Was genau soll passieren",
      "target": "Element-Name oder null",
      "value": "Eingabe-Wert oder null",
      "verification": "Wie prüfen wir Erfolg?",
      "fallback": "Was tun wenn es nicht klappt?"
    }}
  ],
  "success_criteria": ["Liste der Erfolgs-Bedingungen"],
  "estimated_steps": 5
}}

WICHTIG:
- Sei SPEZIFISCH (konkrete URLs, nicht "irgendeine Seite")
- Denke an COOKIE-BANNER (erster Schritt oft "akzeptieren")
- Berücksichtige LADEZEITEN (wait nach navigate)
- Jeder Step braucht eine verification

Antworte NUR mit dem JSON, keine Markdown, keine Erklärungen."""

        try:
            old_model = self.model
            old_provider = self.provider

            from agent.providers import ModelProvider
            self.model = os.getenv("REASONING_MODEL", "nvidia/nemotron-3-nano-30b-a3b")
            self.provider = ModelProvider.OPENROUTER

            response = await self._call_llm([
                {"role": "user", "content": plan_prompt}
            ])

            self.model = old_model
            self.provider = old_provider

            plan = extract_json_robust(response)
            if plan and plan.get('steps'):
                log.info(f"Visual-Plan erstellt: {plan.get('goal', 'N/A')} ({len(plan.get('steps', []))} Schritte)")
                return plan
            else:
                log.warning("Kein valides JSON im Meta-Agent Response gefunden")
                return self._create_fallback_plan(task)

        except Exception as e:
            log.error(f"Fehler bei Visual-Plan-Erstellung: {e}")
            return self._create_fallback_plan(task)

    def _extract_search_terms(self, task: str) -> str:
        """Extrahiert Suchbegriffe aus dem Task."""
        patterns = [
            r'(?:such|schau)\s+(?:nach|fuer|for)\s+(.+?)(?:\s+(?:auf|in|bei|von)|\.|$)',
            r'(?:search|find|look)\s+(?:for)?\s+(.+?)(?:\s+(?:on|in|at)|\.|$)',
        ]
        for p in patterns:
            m = re.search(p, task, re.IGNORECASE)
            if m:
                return m.group(1).strip()
        return ""

    def _create_fallback_plan(self, task: str) -> dict:
        """Fallback-Plan wenn die AI-Planung fehlschlaegt."""
        url_match = re.search(r'https?://[^\s]+', task)
        domain_match = re.search(r'([a-zA-Z0-9.-]+\.(de|com|org|net|io))', task)

        url = url_match.group(0) if url_match else (
            f"https://{domain_match.group(1)}" if domain_match else "https://www.google.com"
        )

        search_terms = self._extract_search_terms(task)

        steps = [
            {
                "step_number": 1,
                "action": "navigate",
                "description": f"Oeffne {url}",
                "target": None,
                "value": url,
                "verification": "URL geladen",
                "fallback": "Warte und versuche erneut"
            },
            {
                "step_number": 2,
                "action": "wait",
                "description": "Warte auf Seiten-Ladung",
                "target": None,
                "value": "3s",
                "verification": "Seite stabil",
                "fallback": "Weiter mit naechstem Schritt"
            },
        ]

        if search_terms:
            steps.append({
                "step_number": 3,
                "action": "type",
                "description": f"Suche nach: {search_terms}",
                "target": "Suchfeld",
                "value": search_terms,
                "verification": "Suchbegriff eingegeben",
                "fallback": "Suchfeld manuell finden"
            })
            steps.append({
                "step_number": 4,
                "action": "click",
                "description": "Suche absenden",
                "target": "Such-Button oder Enter",
                "value": None,
                "verification": "Suchergebnisse angezeigt",
                "fallback": "Enter druecken"
            })

        verify_step_number = len(steps) + 1
        steps.append({
            "step_number": verify_step_number,
            "action": "verify",
            "description": "Pruefe ob Aufgabe erfuellt",
            "target": None,
            "value": None,
            "verification": "Ziel erreicht",
            "fallback": "Manuelle Interaktion noetig"
        })

        return {
            "goal": task,
            "url": url,
            "steps": steps,
            "success_criteria": ["Seite erfolgreich geladen"],
            "estimated_steps": len(steps),
            "_fallback": True
        }
