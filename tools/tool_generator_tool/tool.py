# tools/tool_generator_tool/tool.py
"""
M13: Tool-Generierung MCP-Tools.

Drei MCP-Tools:
  - generate_tool           — Generiert neues Tool + Telegram-Review-Request
  - get_pending_tool_reviews — Liste wartender Review-Anfragen
  - list_generated_tools    — Alle generierten Tools + Status

Feature-Flag: AUTONOMY_M13_ENABLED=false
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, List

from dotenv import load_dotenv
from tools.tool_registry_v2 import ToolCategory as C, ToolParameter as P, tool

load_dotenv(override=True)
log = logging.getLogger("tool_generator_tool")


def _m13_enabled() -> bool:
    return os.getenv("AUTONOMY_M13_ENABLED", "false").strip().lower() in {"1", "true", "yes"}


@tool(
    name="generate_tool",
    description=(
        "M13: Generiert ein neues MCP-Tool aus Name, Beschreibung und Parameter-Liste. "
        "Führt AST-Sicherheitsvalidierung durch und sendet Code-Preview via Telegram für Review."
    ),
    parameters=[
        P("tool_name", "str", "Name des neuen Tools (snake_case)", required=True),
        P("description", "str", "Was macht das Tool?", required=True),
        P("parameters", "str", "Kommagetrennte Parameter-Namen (z.B. 'url,timeout')", required=False, default=""),
    ],
    capabilities=["tool_generation", "autonomy"],
    category=C.PRODUCTIVITY,
)
async def generate_tool(
    tool_name: str,
    description: str,
    parameters: str = "",
) -> Dict[str, Any]:
    if not _m13_enabled():
        return {"error": "M13 ist deaktiviert (AUTONOMY_M13_ENABLED=false)"}

    param_list = [p.strip() for p in parameters.split(",") if p.strip()] if parameters else []

    from orchestration.tool_generator_engine import get_tool_generator_engine
    engine = get_tool_generator_engine()
    generated = engine.generate(tool_name, description, param_list)

    result = {
        "action_id": generated.action_id,
        "name": generated.name,
        "status": generated.status,
        "code_length": generated.code_length,
        "code_preview": generated.code[:400] + ("..." if len(generated.code) > 400 else ""),
    }

    if generated.status == "rejected":
        result["error"] = generated.error
        return result

    # Telegram-Review senden
    try:
        await engine.request_review(generated)
        result["telegram_sent"] = True
    except Exception as e:
        log.warning("M13: Telegram-Review fehlgeschlagen: %s", e)
        result["telegram_sent"] = False
        result["telegram_error"] = str(e)

    return result


@tool(
    name="get_pending_tool_reviews",
    description="M13: Gibt alle wartenden Tool-Review-Anfragen zurück (noch nicht genehmigt/abgelehnt).",
    parameters=[],
    capabilities=["tool_generation", "autonomy"],
    category=C.PRODUCTIVITY,
)
async def get_pending_tool_reviews() -> Dict[str, Any]:
    if not _m13_enabled():
        return {"error": "M13 ist deaktiviert (AUTONOMY_M13_ENABLED=false)"}

    from orchestration.tool_generator_engine import get_tool_generator_engine
    engine = get_tool_generator_engine()
    pending = engine.get_pending_reviews()
    return {
        "count": len(pending),
        "pending": pending,
    }


@tool(
    name="list_generated_tools",
    description="M13: Listet alle bisher generierten Tools mit Status (pending/approved/active/rejected).",
    parameters=[],
    capabilities=["tool_generation", "autonomy"],
    category=C.PRODUCTIVITY,
)
async def list_generated_tools() -> Dict[str, Any]:
    if not _m13_enabled():
        return {"error": "M13 ist deaktiviert (AUTONOMY_M13_ENABLED=false)"}

    from orchestration.tool_generator_engine import get_tool_generator_engine
    engine = get_tool_generator_engine()
    tools = engine.list_all_tools()
    return {
        "count": len(tools),
        "tools": tools,
    }
