"""SystemAgent — Log-Analyse, Prozesse, Systemressourcen, Service-Status."""

from __future__ import annotations

import asyncio
import logging
from typing import Optional

from agent.base_agent import BaseAgent
from agent.prompts import SYSTEM_PROMPT_TEMPLATE
from agent.shared.delegation_handoff import DelegationHandoff, parse_delegation_handoff

log = logging.getLogger("TimusAgent-v4.4")

# Alert-Schwellwerte (%, read-only)
_ALERT: dict[str, float] = {
    "cpu_critical": 90.0, "cpu_warning": 70.0,
    "ram_critical": 90.0, "ram_warning": 80.0,
    "disk_critical": 90.0, "disk_warning": 80.0,
}


def _level(value: object, warn_key: str, crit_key: str) -> str:
    if not isinstance(value, (int, float)):
        return "?"
    if value >= _ALERT[crit_key]:
        return "KRITISCH"
    if value >= _ALERT[warn_key]:
        return "WARNUNG"
    return "OK"


class SystemAgent(BaseAgent):
    def __init__(self, tools_description_string: str):
        super().__init__(
            SYSTEM_PROMPT_TEMPLATE,
            tools_description_string,
            max_iterations=12,
            agent_type="system",
        )

    async def _get_system_snapshot(self) -> str:
        """Holt System-Snapshot parallel: Ressourcen + Service-Status."""
        try:
            stats_r, mcp_r, disp_r = await asyncio.gather(
                self._call_tool("get_system_stats", {}),
                self._call_tool("get_service_status", {"service_name": "timus-mcp"}),
                self._call_tool("get_service_status", {"service_name": "timus-dispatcher"}),
                return_exceptions=True,
            )
        except Exception as e:
            log.debug(f"System-Snapshot gather fehlgeschlagen: {e}")
            return ""

        lines = ["[SYSTEM-SNAPSHOT]"]

        if isinstance(stats_r, dict) and not stats_r.get("error"):
            cpu  = stats_r.get("cpu_percent", "?")
            ram  = stats_r.get("memory_percent", "?")
            disk = stats_r.get("disk_percent", "?")
            lines += [
                f"CPU:  {cpu}% [{_level(cpu,  'cpu_warning',  'cpu_critical')}]",
                f"RAM:  {ram}% [{_level(ram,  'ram_warning',  'ram_critical')}]",
                f"Disk: {disk}% [{_level(disk, 'disk_warning', 'disk_critical')}]",
            ]

        for label, result in (("timus-mcp", mcp_r), ("timus-dispatcher", disp_r)):
            if isinstance(result, dict) and not result.get("error"):
                status = result.get("status", result.get("active_state", "?"))
                lines.append(f"{label}: {status}")

        return "\n".join(lines)

    async def run(self, task: str) -> str:
        handoff = parse_delegation_handoff(task)
        effective_task = handoff.goal if handoff and handoff.goal else str(task or "").strip()
        snapshot = await self._get_system_snapshot()
        handoff_context = self._build_delegation_system_context(handoff)
        parts = [effective_task]
        if snapshot:
            log.info("SystemAgent | Snapshot injiziert")
            parts.append(snapshot)
        if handoff_context:
            parts.append(handoff_context)
        return await super().run("\n\n".join(part for part in parts if part))

    def _build_delegation_system_context(self, handoff: Optional[DelegationHandoff]) -> str:
        if not handoff:
            return ""

        lines: list[str] = ["# STRUKTURIERTER SYSTEM-HANDOFF"]
        if handoff.expected_output:
            lines.append(f"Erwarteter Output: {handoff.expected_output}")
        if handoff.success_signal:
            lines.append(f"Erfolgssignal: {handoff.success_signal}")
        if handoff.constraints:
            lines.append("Constraints: " + " | ".join(handoff.constraints))

        for key, label in (
            ("recipe_id", "Rezept"),
            ("stage_id", "Stage"),
            ("incident_key", "Incident-Key"),
            ("service_name", "Service"),
            ("expected_state", "Erwarteter Zustand"),
            ("previous_stage_result", "Vorheriges Stage-Ergebnis"),
            ("captured_context", "Bereits erfasster Kontext"),
            ("previous_blackboard_key", "Blackboard-Key"),
        ):
            value = handoff.handoff_data.get(key)
            if value:
                lines.append(f"{label}: {value}")
        return "\n".join(lines)
