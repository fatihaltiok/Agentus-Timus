"""SystemAgent — Log-Analyse, Prozesse, Systemressourcen, Service-Status."""

from __future__ import annotations

import asyncio
import logging
from typing import Optional

from agent.base_agent import BaseAgent
from agent.prompts import SYSTEM_PROMPT_TEMPLATE
from agent.shared.delegation_handoff import DelegationHandoff, parse_delegation_handoff
from orchestration.specialist_context import (
    assess_specialist_context_alignment,
    extract_specialist_context_from_handoff_data,
    format_specialist_signal_response,
    render_specialist_context_block,
)
from orchestration.autonomy_observation import record_autonomy_observation

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

    async def _get_system_snapshot(self, preferred_service: str = "", *, compact: bool = False) -> str:
        """Holt System-Snapshot parallel: Ressourcen + Service-Status."""
        preferred = str(preferred_service or "").strip()
        try:
            if compact and preferred:
                stats_r = None
                primary_r = await self._call_tool("get_service_status", {"service_name": preferred})
                secondary: list[tuple[str, object]] = []
            else:
                primary_services = [preferred] if preferred else []
                for candidate in ("timus-mcp", "timus-dispatcher"):
                    if candidate not in primary_services:
                        primary_services.append(candidate)
                gathered = await asyncio.gather(
                    self._call_tool("get_system_stats", {}),
                    *[
                        self._call_tool("get_service_status", {"service_name": name})
                        for name in primary_services[:2]
                    ],
                    return_exceptions=True,
                )
                stats_r = gathered[0]
                service_results = list(zip(primary_services[:2], gathered[1:]))
                primary_r = service_results[0][1] if service_results else None
                secondary = service_results[1:]
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

        primary_label = preferred or "timus-mcp"
        for label, result in [(primary_label, primary_r), *secondary]:
            if isinstance(result, dict) and not result.get("error"):
                status = result.get("status", result.get("active_state", "?"))
                lines.append(f"{label}: {status}")

        return "\n".join(lines)

    async def run(self, task: str) -> str:
        handoff = parse_delegation_handoff(task)
        specialist_context_payload = (
            extract_specialist_context_from_handoff_data(handoff.handoff_data) if handoff else {}
        )
        alignment = assess_specialist_context_alignment(
            current_task=(
                (handoff.handoff_data.get("original_user_task") or "") if handoff else ""
            )
            or ((handoff.handoff_data.get("service_name") or "") if handoff else "")
            or (handoff.goal if handoff and handoff.goal else task),
            payload=specialist_context_payload,
        )
        if handoff and alignment.get("alignment_state") == "needs_meta_reframe":
            return format_specialist_signal_response(
                "needs_meta_reframe",
                reason=str(alignment.get("reason") or ""),
                message=(
                    "Der aktuelle System-Handoff passt nicht sauber zum laufenden Themenanker. "
                    "Meta sollte erst die Diagnoseanfrage oder den Kontext neu rahmen."
                ),
            )
        response_mode = str(specialist_context_payload.get("response_mode") or "").strip().lower()
        snapshot_plan = self._derive_system_snapshot_plan(handoff, specialist_context_payload)
        effective_task = handoff.goal if handoff and handoff.goal else str(task or "").strip()
        if handoff:
            record_autonomy_observation(
                "specialist_strategy_selected",
                {
                    "agent": "system",
                    "strategy_mode": (
                        "compact_service_snapshot"
                        if snapshot_plan.get("compact")
                        else ("service_snapshot" if snapshot_plan.get("preferred_service") else "full_snapshot")
                    ),
                    "response_mode": response_mode,
                    "session_id": str(handoff.handoff_data.get("session_id") or ""),
                },
            )
        snapshot = await self._get_system_snapshot(
            snapshot_plan.get("preferred_service", ""),
            compact=bool(snapshot_plan.get("compact")),
        )
        if handoff and response_mode == "summarize_state" and self._is_status_summary_handoff(handoff, effective_task):
            return self._build_direct_status_summary(handoff, effective_task, snapshot)
        handoff_context = self._build_delegation_system_context(handoff)
        parts = [effective_task]
        if snapshot:
            log.info("SystemAgent | Snapshot injiziert")
            parts.append(snapshot)
        if handoff_context:
            parts.append(handoff_context)
        return await super().run("\n\n".join(part for part in parts if part))

    def _derive_system_snapshot_plan(
        self,
        handoff: Optional[DelegationHandoff],
        specialist_context_payload: dict,
    ) -> dict:
        preferred_service = str((handoff.handoff_data or {}).get("service_name") or "").strip() if handoff else ""
        response_mode = str(specialist_context_payload.get("response_mode") or "").strip().lower()
        preferences = " | ".join(str(item or "").strip().lower() for item in specialist_context_payload.get("user_preferences") or [])
        compact = bool(
            preferred_service
            and (
                response_mode == "summarize_state"
                or "kurz" in preferences
                or "knapp" in preferences
            )
        )
        return {
            "preferred_service": preferred_service,
            "compact": compact,
        }

    def _is_status_summary_handoff(self, handoff: DelegationHandoff, effective_task: str) -> bool:
        service_name = str(handoff.handoff_data.get("service_name") or "").strip()
        if service_name:
            return True
        task_lower = str(effective_task or "").strip().lower()
        return any(
            token in task_lower
            for token in ("zustand", "status", "health", "gesund", "diagnose", "mcp", "dispatcher", "service")
        )

    def _build_direct_status_summary(
        self,
        handoff: DelegationHandoff,
        effective_task: str,
        snapshot: str,
    ) -> str:
        lines = ["Systemstatus-Zusammenfassung", effective_task]
        service_name = str(handoff.handoff_data.get("service_name") or "").strip()
        expected_state = str(handoff.handoff_data.get("expected_state") or "").strip()
        if service_name:
            lines.append(f"Service: {service_name}")
        if expected_state:
            lines.append(f"Erwarteter Zustand: {expected_state}")
        if snapshot:
            lines.append(snapshot)
        return "\n".join(line for line in lines if line)

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

        specialist_context_payload = extract_specialist_context_from_handoff_data(handoff.handoff_data)
        specialist_context = render_specialist_context_block(
            specialist_context_payload,
            alignment=assess_specialist_context_alignment(
                current_task=handoff.handoff_data.get("original_user_task")
                or handoff.handoff_data.get("service_name")
                or handoff.goal,
                payload=specialist_context_payload,
            ),
        )
        if specialist_context:
            lines.append(specialist_context)

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
