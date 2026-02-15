"""
Delegation Tool - Ermoeglicht Agent-zu-Agent Delegation ueber MCP.

Tools:
- delegate_to_agent: Delegiert eine Aufgabe an einen spezialisierten Agenten
- find_agent_by_capability: Findet passende Agenten fuer eine Faehigkeit
"""

import logging
from tools.tool_registry_v2 import tool, P, C

log = logging.getLogger("DelegationTool")


@tool(
    name="delegate_to_agent",
    description=(
        "Delegiert eine Aufgabe an einen spezialisierten Agenten. "
        "Nutze dies wenn deine eigenen Faehigkeiten nicht ausreichen. "
        "Verfuegbare Agenten: executor, research, reasoning, creative, developer, visual, meta."
    ),
    parameters=[
        P("agent_type", "string",
          "Ziel-Agent: executor, research, reasoning, creative, developer, visual, meta"),
        P("task", "string", "Die zu delegierende Aufgabe"),
    ],
    capabilities=["orchestration"],
    category=C.SYSTEM,
)
async def delegate_to_agent(agent_type: str, task: str) -> dict:
    from agent.agent_registry import agent_registry

    log.info(f"Delegation angefragt: -> {agent_type} | Task: {task[:100]}")

    result = await agent_registry.delegate(
        from_agent="unknown",
        to_agent=agent_type,
        task=task,
    )

    return {"status": "success", "agent": agent_type, "result": result}


@tool(
    name="find_agent_by_capability",
    description=(
        "Findet den passenden Agenten fuer eine bestimmte Faehigkeit. "
        "Moegliche Faehigkeiten: execution, research, search, deep_analysis, "
        "reasoning, analysis, debugging, creative, images, content_generation, "
        "code, development, files, refactoring, vision, ui, browser, "
        "orchestration, planning, coordination."
    ),
    parameters=[
        P("capability", "string",
          "Gesuchte Faehigkeit, z.B.: research, vision, code, creative, reasoning, search"),
    ],
    capabilities=["orchestration"],
    category=C.SYSTEM,
)
async def find_agent_by_capability(capability: str) -> dict:
    from agent.agent_registry import agent_registry

    agents = agent_registry.find_by_capability(capability)

    return {
        "status": "success",
        "capability": capability,
        "agents": [
            {"name": a.name, "type": a.agent_type, "capabilities": a.capabilities}
            for a in agents
        ],
    }
