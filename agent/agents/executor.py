"""ExecutorAgent - Schnelle einfache Tasks."""

from agent.base_agent import BaseAgent
from agent.prompts import EXECUTOR_PROMPT_TEMPLATE
from agent.shared.delegation_handoff import DelegationHandoff, parse_delegation_handoff


class ExecutorAgent(BaseAgent):
    def __init__(self, tools_description_string: str):
        super().__init__(EXECUTOR_PROMPT_TEMPLATE, tools_description_string, 30, "executor")

    def _build_executor_handoff_context(self, handoff: DelegationHandoff | None) -> str:
        if not handoff:
            return ""

        lines: list[str] = ["# STRUKTURIERTER EXECUTOR-HANDOFF"]
        if handoff.expected_output:
            lines.append(f"Erwarteter Output: {handoff.expected_output}")
        if handoff.success_signal:
            lines.append(f"Erfolgssignal: {handoff.success_signal}")
        if handoff.constraints:
            lines.append("Constraints: " + " | ".join(handoff.constraints))

        for key, label in (
            ("task_type", "Task-Typ"),
            ("recipe_id", "Rezept"),
            ("stage_id", "Stage"),
            ("site_kind", "Seitenklasse"),
            ("strategy_id", "Strategie"),
            ("strategy_mode", "Strategiemodus"),
            ("error_strategy", "Fehlerstrategie"),
            ("preferred_search_tool", "Bevorzugtes Suchtool"),
            ("preferred_tools", "Bevorzugte Tools"),
            ("fallback_tools", "Fallback-Tools"),
            ("avoid_tools", "Zu vermeidende Tools"),
            ("search_mode", "Suchmodus"),
            ("max_results", "Max Ergebnisse"),
            ("avoid_deep_research", "Deep-Research vermeiden"),
            ("previous_stage_result", "Vorheriges Stage-Ergebnis"),
            ("previous_blackboard_key", "Blackboard-Key"),
        ):
            value = handoff.handoff_data.get(key)
            if value:
                lines.append(f"{label}: {value}")
        return "\n".join(lines)

    async def run(self, task: str) -> str:
        handoff = parse_delegation_handoff(task)
        effective_task = handoff.goal if handoff and handoff.goal else task
        handoff_context = self._build_executor_handoff_context(handoff)
        enriched_task = "\n\n".join(part for part in (effective_task, handoff_context) if part)
        return await super().run(enriched_task)
