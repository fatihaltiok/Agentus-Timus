"""
tools/blackboard_tool/tool.py — M9: Agent Blackboard MCP-Tools

3 MCP-Tools für den Agent-Blackboard:
- write_to_blackboard: Eintrag publizieren
- read_from_blackboard: Einträge lesen
- search_blackboard: Volltext-Suche
"""

import logging

from tools.tool_registry_v2 import tool, ToolParameter as P, ToolCategory as C

log = logging.getLogger("blackboard_tool")


@tool(
    name="write_to_blackboard",
    description=(
        "Publiziert eine Information im Agent-Blackboard (geteiltes Kurzzeit-Gedächtnis). "
        "Andere Agenten können diese Information lesen. Sinnvoll für Research-Ergebnisse, "
        "Zwischenstände und gemeinsame Kontext-Informationen."
    ),
    parameters=[
        P("agent",       "string",  "Name des schreibenden Agenten (z.B. 'research', 'meta')"),
        P("topic",       "string",  "Themen-Kategorie (z.B. 'research_results', 'user_prefs')"),
        P("key",         "string",  "Eindeutiger Schlüssel innerhalb des Topics"),
        P("value",       "string",  "Zu speichernder Wert (Text oder JSON-String)"),
        P("ttl_minutes", "integer", "Gültigkeitsdauer in Minuten (default: 60)", required=False, default=60),
    ],
    capabilities=["memory", "analysis"],
    category=C.MEMORY,
)
async def write_to_blackboard(
    agent: str,
    topic: str,
    key: str,
    value: str,
    ttl_minutes: int = 60,
) -> dict:
    """Publiziert einen Eintrag im Agent-Blackboard."""
    from memory.agent_blackboard import get_blackboard

    get_blackboard().write(
        agent=agent,
        topic=topic,
        key=key,
        value=value,
        ttl_minutes=ttl_minutes,
    )
    return {
        "status": "ok",
        "agent": agent,
        "topic": topic,
        "key": key,
        "ttl_minutes": ttl_minutes,
    }


@tool(
    name="read_from_blackboard",
    description=(
        "Liest Einträge aus dem Agent-Blackboard für ein bestimmtes Topic. "
        "Optionaler Key-Filter liefert nur den gewünschten Eintrag zurück."
    ),
    parameters=[
        P("topic", "string", "Das zu lesende Topic"),
        P("key",   "string", "Optionaler Schlüssel-Filter (leer = alle Keys)", required=False, default=""),
    ],
    capabilities=["memory", "analysis"],
    category=C.MEMORY,
)
async def read_from_blackboard(topic: str, key: str = "") -> dict:
    """Liest Einträge aus dem Blackboard."""
    from memory.agent_blackboard import get_blackboard

    blackboard = get_blackboard()
    entries = blackboard.read(topic=topic, key=key)
    lookup_mode = "topic"

    # Delegations-Ergebnisse werden unter topic="delegation_results" und key=<blackboard_key>
    # persistiert. Meta-Agenten lesen im Lauf aber oft direkt mit dem blackboard_key als topic.
    if not entries and not key and str(topic or "").startswith("delegation:"):
        entries = blackboard.read(topic="delegation_results", key=topic)
        lookup_mode = "delegation_key"

    return {
        "status": "ok",
        "topic": topic,
        "lookup_mode": lookup_mode,
        "count": len(entries),
        "entries": entries,
    }


@tool(
    name="search_blackboard",
    description=(
        "Sucht im Agent-Blackboard nach einem Begriff (Topic, Key oder Value). "
        "Gibt die relevantesten aktiven Einträge zurück."
    ),
    parameters=[
        P("query", "string",  "Suchbegriff"),
        P("limit", "integer", "Maximale Ergebnisanzahl (1-20)", required=False, default=5),
    ],
    capabilities=["memory", "analysis", "search"],
    category=C.MEMORY,
)
async def search_blackboard(query: str, limit: int = 5) -> dict:
    """Volltext-Suche im Agent-Blackboard."""
    from memory.agent_blackboard import get_blackboard

    entries = get_blackboard().search(query=query, limit=min(20, max(1, limit)))
    return {
        "status": "ok",
        "query": query,
        "count": len(entries),
        "entries": entries,
    }
