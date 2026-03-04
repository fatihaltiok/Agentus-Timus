"""
tools/self_improvement_tool/tool.py — M12: Self-Improvement MCP-Tools

3 MCP-Tools für die Self-Improvement Engine:
- get_tool_analytics: Tool-Nutzungsstatistiken
- get_routing_stats: Routing-Entscheidungsstatistiken
- get_improvement_suggestions: Verbesserungsvorschläge
"""

import logging

from tools.tool_registry_v2 import tool, ToolParameter as P, ToolCategory as C

log = logging.getLogger("self_improvement_tool")


@tool(
    name="get_tool_analytics",
    description=(
        "Gibt Statistiken zur Tool-Nutzung zurück: Erfolgsraten, Laufzeiten "
        "und Häufigkeiten pro Tool und Agent. Hilft Bottlenecks zu identifizieren."
    ),
    parameters=[
        P("agent", "string",  "Agenten-Filter (leer = alle Agenten)", required=False, default=""),
        P("days",  "integer", "Analysezeitraum in Tagen (default: 7)", required=False, default=7),
    ],
    capabilities=["analysis", "system"],
    category=C.SYSTEM,
)
async def get_tool_analytics(agent: str = "", days: int = 7) -> dict:
    """Gibt Tool-Nutzungsstatistiken zurück."""
    from orchestration.self_improvement_engine import get_improvement_engine

    stats = get_improvement_engine().get_tool_stats(
        agent=agent if agent else None,
        days=max(1, min(90, days)),
    )
    return {
        "status": "ok",
        "agent_filter": agent or "all",
        "days": days,
        "count": len(stats),
        "stats": stats,
    }


@tool(
    name="get_routing_stats",
    description=(
        "Gibt Routing-Statistiken zurück: Welcher Agent wie oft gewählt wurde, "
        "durchschnittliche Konfidenz und Erfolgsrate."
    ),
    parameters=[
        P("days", "integer", "Analysezeitraum in Tagen (default: 7)", required=False, default=7),
    ],
    capabilities=["analysis", "system"],
    category=C.SYSTEM,
)
async def get_routing_stats(days: int = 7) -> dict:
    """Gibt Routing-Statistiken zurück."""
    from orchestration.self_improvement_engine import get_improvement_engine

    stats = get_improvement_engine().get_routing_stats(days=max(1, min(90, days)))
    return {"status": "ok", **stats}


@tool(
    name="get_improvement_suggestions",
    description=(
        "Gibt Verbesserungsvorschläge der Self-Improvement Engine zurück. "
        "Basiert auf Tool-Erfolgsraten, Routing-Konfidenz und Laufzeit-Analyse."
    ),
    parameters=[
        P("include_applied", "boolean", "Auch bereits angewendete Vorschläge anzeigen", required=False, default=False),
    ],
    capabilities=["analysis", "system"],
    category=C.SYSTEM,
)
async def get_improvement_suggestions(include_applied: bool = False) -> dict:
    """Gibt Verbesserungsvorschläge zurück."""
    from orchestration.self_improvement_engine import get_improvement_engine

    suggestions = get_improvement_engine().get_suggestions(applied=include_applied)
    return {
        "status": "ok",
        "count": len(suggestions),
        "suggestions": suggestions,
    }
