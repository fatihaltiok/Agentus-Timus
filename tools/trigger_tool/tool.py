"""
tools/trigger_tool/tool.py — M10: Proactive Triggers MCP-Tools

4 MCP-Tools für proaktive Trigger:
- add_proactive_trigger: Neuen Trigger anlegen
- list_proactive_triggers: Alle Trigger auflisten
- remove_proactive_trigger: Trigger entfernen
- enable_proactive_trigger: Trigger aktivieren/deaktivieren
"""

import logging

from tools.tool_registry_v2 import tool, ToolParameter as P, ToolCategory as C

log = logging.getLogger("trigger_tool")


@tool(
    name="add_proactive_trigger",
    description=(
        "Legt einen neuen zeitgesteuerten Trigger an. "
        "Der Trigger startet automatisch eine Aufgabe zur angegebenen Uhrzeit."
    ),
    parameters=[
        P("name",         "string",  "Anzeigename des Triggers (z.B. 'Morgen-Check')"),
        P("time_of_day",  "string",  "Uhrzeit im Format HH:MM (z.B. '08:00')"),
        P("action_query", "string",  "Was Timus tun soll wenn der Trigger feuert"),
        P("target_agent", "string",  "Ziel-Agent (z.B. 'meta', 'communication')", required=False, default="meta"),
        P("days_of_week", "string",  "Wochentage als JSON-Liste [0-6], [] = täglich (0=Mo)", required=False, default="[]"),
        P("enabled",      "boolean", "Ob der Trigger sofort aktiv sein soll", required=False, default=True),
    ],
    capabilities=["planning", "automation"],
    category=C.SYSTEM,
)
async def add_proactive_trigger(
    name: str,
    time_of_day: str,
    action_query: str,
    target_agent: str = "meta",
    days_of_week: str = "[]",
    enabled: bool = True,
) -> dict:
    """Legt einen neuen proaktiven Trigger an."""
    import json
    from orchestration.proactive_triggers import ProactiveTrigger, get_trigger_engine

    try:
        days = json.loads(days_of_week) if isinstance(days_of_week, str) else days_of_week
    except Exception:
        days = []

    trigger = ProactiveTrigger(
        name=name,
        time_of_day=time_of_day,
        action_query=action_query,
        target_agent=target_agent,
        days_of_week=days,
        enabled=enabled,
    )

    trigger_id = get_trigger_engine().add_trigger(trigger)
    return {
        "status": "ok",
        "trigger_id": trigger_id,
        "name": name,
        "time_of_day": time_of_day,
        "target_agent": target_agent,
    }


@tool(
    name="list_proactive_triggers",
    description="Listet alle proaktiven Trigger mit Status, Uhrzeit und letzter Ausführung auf.",
    parameters=[],
    capabilities=["planning", "automation"],
    category=C.SYSTEM,
)
async def list_proactive_triggers() -> dict:
    """Listet alle Trigger auf."""
    from orchestration.proactive_triggers import get_trigger_engine

    triggers = get_trigger_engine().list_triggers()
    return {
        "status": "ok",
        "count": len(triggers),
        "triggers": triggers,
    }


@tool(
    name="remove_proactive_trigger",
    description="Entfernt einen proaktiven Trigger anhand seiner ID.",
    parameters=[
        P("trigger_id", "string", "ID des zu entfernenden Triggers"),
    ],
    capabilities=["planning", "automation"],
    category=C.SYSTEM,
)
async def remove_proactive_trigger(trigger_id: str) -> dict:
    """Entfernt einen Trigger."""
    from orchestration.proactive_triggers import get_trigger_engine

    found = get_trigger_engine().remove_trigger(trigger_id)
    return {
        "status": "ok" if found else "not_found",
        "trigger_id": trigger_id,
        "removed": found,
    }


@tool(
    name="enable_proactive_trigger",
    description="Aktiviert oder deaktiviert einen proaktiven Trigger.",
    parameters=[
        P("trigger_id", "string",  "ID des Triggers"),
        P("enabled",    "boolean", "True = aktivieren, False = deaktivieren"),
    ],
    capabilities=["planning", "automation"],
    category=C.SYSTEM,
)
async def enable_proactive_trigger(trigger_id: str, enabled: bool) -> dict:
    """Aktiviert oder deaktiviert einen Trigger."""
    from orchestration.proactive_triggers import get_trigger_engine

    found = get_trigger_engine().enable_trigger(trigger_id, enabled)
    return {
        "status": "ok" if found else "not_found",
        "trigger_id": trigger_id,
        "enabled": enabled,
        "updated": found,
    }
