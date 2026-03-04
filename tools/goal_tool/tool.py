"""
tools/goal_tool/tool.py — M11: Goal Queue Manager MCP-Tools

4 MCP-Tools für das hierarchische Ziel-Management:
- set_long_term_goal: Haupt-Ziel setzen
- add_subgoal: Teilziel zu bestehendem Ziel
- complete_milestone: Meilenstein abhaken
- get_goal_progress: Fortschritt + Tree abfragen
"""

import logging

from tools.tool_registry_v2 import tool, ToolParameter as P, ToolCategory as C

log = logging.getLogger("goal_tool")


@tool(
    name="set_long_term_goal",
    description=(
        "Legt ein neues langfristiges Ziel an. "
        "Optionale Meilensteine ermöglichen Fortschritts-Tracking. "
        "Rückgabe: goal_id für weitere Operationen."
    ),
    parameters=[
        P("title",       "string", "Kurzer Titel des Ziels"),
        P("description", "string", "Detaillierte Beschreibung des Ziels", required=False, default=""),
        P("milestones",  "string", "Meilensteine als JSON-Liste (z.B. '[\"Phase 1\", \"Phase 2\"]')", required=False, default="[]"),
    ],
    capabilities=["planning", "tasks", "memory"],
    category=C.SYSTEM,
)
async def set_long_term_goal(
    title: str,
    description: str = "",
    milestones: str = "[]",
) -> dict:
    """Legt ein neues langfristiges Ziel an."""
    import json
    from orchestration.goal_queue_manager import get_goal_manager

    try:
        ms_list = json.loads(milestones) if isinstance(milestones, str) else milestones
    except Exception:
        ms_list = []

    goal_id = get_goal_manager().add_goal(
        title=title,
        description=description,
        milestones=ms_list if ms_list else None,
    )

    return {
        "status": "ok",
        "goal_id": goal_id,
        "title": title,
        "milestones_count": len(ms_list),
    }


@tool(
    name="add_subgoal",
    description=(
        "Fügt ein Teilziel zu einem bestehenden Ziel hinzu. "
        "Nutze get_goal_progress um die goal_id eines Ziels zu ermitteln."
    ),
    parameters=[
        P("parent_goal_id", "string", "ID des übergeordneten Ziels"),
        P("title",          "string", "Kurzer Titel des Teilziels"),
        P("description",    "string", "Detailbeschreibung", required=False, default=""),
    ],
    capabilities=["planning", "tasks"],
    category=C.SYSTEM,
)
async def add_subgoal(
    parent_goal_id: str,
    title: str,
    description: str = "",
) -> dict:
    """Fügt ein Teilziel hinzu."""
    from orchestration.goal_queue_manager import get_goal_manager

    goal_id = get_goal_manager().add_subgoal(
        parent_id=parent_goal_id,
        title=title,
        description=description,
    )

    return {
        "status": "ok",
        "goal_id": goal_id,
        "parent_goal_id": parent_goal_id,
        "title": title,
    }


@tool(
    name="complete_milestone",
    description=(
        "Markiert einen Meilenstein eines Ziels als abgeschlossen. "
        "Der Fortschritt wird automatisch berechnet und zum Parent-Ziel hochgerechnet."
    ),
    parameters=[
        P("goal_id",       "string",  "ID des Ziels"),
        P("milestone_idx", "integer", "0-basierter Index des Meilensteins"),
    ],
    capabilities=["planning", "tasks"],
    category=C.SYSTEM,
)
async def complete_milestone(goal_id: str, milestone_idx: int) -> dict:
    """Markiert einen Meilenstein als erledigt."""
    from orchestration.goal_queue_manager import get_goal_manager

    progress = get_goal_manager().complete_milestone(
        goal_id=goal_id,
        milestone_idx=milestone_idx,
    )

    return {
        "status": "ok",
        "goal_id": goal_id,
        "milestone_idx": milestone_idx,
        "progress": progress,
        "completed": progress >= 1.0,
    }


@tool(
    name="get_goal_progress",
    description=(
        "Gibt Fortschritt, Meilensteine und Tree-Struktur eines Ziels zurück. "
        "Ohne goal_id wird der vollständige Ziel-Baum zurückgegeben."
    ),
    parameters=[
        P("goal_id", "string", "ID des Ziels (leer = alle Ziele als Tree)", required=False, default=""),
    ],
    capabilities=["planning", "tasks", "analysis"],
    category=C.SYSTEM,
)
async def get_goal_progress(goal_id: str = "") -> dict:
    """Gibt Fortschritt oder den gesamten Ziel-Baum zurück."""
    from orchestration.goal_queue_manager import get_goal_manager

    manager = get_goal_manager()

    if goal_id:
        return manager.get_goal_progress(goal_id)
    else:
        tree = manager.get_goal_tree()
        return {
            "status": "ok",
            "tree": tree,
            "nodes": len([e for e in tree if "source" not in e.get("data", {})]),
            "edges": len([e for e in tree if "source" in e.get("data", {})]),
        }
