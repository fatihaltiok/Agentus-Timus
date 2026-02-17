"""MetaAgent - Koordinator mit Skill-Orchestrierung."""
import os
import re
import json
import logging
from typing import List, Optional
from pathlib import Path

from agent.base_agent import BaseAgent
from agent.prompts import META_SYSTEM_PROMPT

log = logging.getLogger("TimusAgent-v4.4")


from agent.shared.json_utils import extract_json_robust  # noqa: F401 - re-exported


class MetaAgent(BaseAgent):
    def __init__(self, tools_description_string: str):
        super().__init__(META_SYSTEM_PROMPT, tools_description_string, 30, "meta")

        self.skill_registry = None
        self.active_skills: list = []
        self._init_skill_system()

    def _init_skill_system(self):
        try:
            from utils.skill_types import SkillRegistry
            from utils.skill_parser import find_all_skills

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

    async def run(self, task: str) -> str:
        log.info(f"MetaAgent mit Skill-Orchestrierung: {task[:50]}...")

        self.active_skills = self._select_skills_for_task(task, top_k=3)

        skill_context = self._build_skill_context(
            self.active_skills,
            include_references=False,
        )

        if skill_context:
            enhanced_task = f"""{skill_context}

# TASK
{task}

When executing this task, check if any of the available skills apply.
If a skill matches, use its instructions and resources."""
        else:
            enhanced_task = task

        result = await super().run(enhanced_task)

        return result

    async def create_visual_plan(self, task: str) -> dict:
        """Erstellt einen strukturierten Plan für Visual/Browser-Tasks.

        Diese Methode analysiert den Task und erstellt eine Schritt-für-Schritt
        Roadmap mit konkreten Aktionen (URL öffnen, Elemente finden, etc.)

        Returns:
            Dict mit: goal, url, steps (Liste von Actions mit verification)
        """
        log.info(f"MetaAgent: Erstelle Visual-Plan für: {task[:60]}...")

        # Prompt für strukturierte Planung
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
            # Nutze Reasoning-Modell (Nemotron) für bessere Planung
            old_model = self.model
            old_provider = self.provider

            # Temporär auf Nemotron umschalten für Planung
            from agent.providers import ModelProvider
            self.model = os.getenv("REASONING_MODEL", "nvidia/nemotron-3-nano-30b-a3b")
            self.provider = ModelProvider.OPENROUTER

            response = await self._call_llm([
                {"role": "user", "content": plan_prompt}
            ])

            # Restore original settings
            self.model = old_model
            self.provider = old_provider

            # Parse JSON aus Response via robustes Brace-Counting
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
        # Extrahiere URL aus Task
        url_match = re.search(r'https?://[^\s]+', task)
        domain_match = re.search(r'([a-zA-Z0-9.-]+\.(de|com|org|net|io))', task)

        url = url_match.group(0) if url_match else (
            f"https://{domain_match.group(1)}" if domain_match else "https://www.google.com"
        )

        # Suchbegriffe aus Task extrahieren
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

        # Wenn Suchbegriffe vorhanden, Suche als Steps einfuegen
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

        # Verify-Step am Ende
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
