"""SystemAgent — Log-Analyse, Prozesse, Systemressourcen, Service-Status."""

import asyncio
import logging

from agent.base_agent import BaseAgent
from agent.prompts import SYSTEM_PROMPT_TEMPLATE

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
                self._call_tool("get_service_status", {"service": "timus-mcp"}),
                self._call_tool("get_service_status", {"service": "timus-dispatcher"}),
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
        snapshot = await self._get_system_snapshot()
        if snapshot:
            log.info("SystemAgent | Snapshot injiziert")
            task = f"{snapshot}\n\n{task}"
        return await super().run(task)
