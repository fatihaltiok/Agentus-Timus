"""MetaAgent - Koordinator mit Skill-Orchestrierung."""

import logging
from typing import List
from pathlib import Path

from agent.base_agent import BaseAgent
from agent.prompts import META_SYSTEM_PROMPT

log = logging.getLogger("TimusAgent-v4.4")


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
