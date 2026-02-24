"""
Parallel-Delegation-Tool — Fan-Out für parallele Agent-Ausführung.

Ermöglicht dem MetaAgent mehrere unabhängige Aufgaben gleichzeitig
an verschiedene Agenten zu delegieren (Wide-Research-Pattern).

Registriert sich automatisch über @tool Decorator in tool_registry_v2.
"""

import logging
from typing import List, Dict, Any

from tools.tool_registry_v2 import tool, ToolParameter as P, ToolCategory as C

log = logging.getLogger("ParallelDelegationTool")


@tool(
    name="delegate_multiple_agents",
    description=(
        "Führt mehrere UNABHÄNGIGE Aufgaben PARALLEL an verschiedene Agenten aus (Wide-Research-Pattern). "
        "Jeder Worker läuft isoliert mit eigenem Speicher. Ergebnisse werden gebündelt zurückgeliefert. "
        "NUR verwenden wenn Teilaufgaben wirklich voneinander unabhängig sind — "
        "bei abhängigen Schritten weiterhin delegate_to_agent sequenziell nutzen. "
        "Verfügbare Agenten: executor, research, reasoning, creative, developer, "
        "visual, meta, image, data, document, communication, system, shell."
    ),
    parameters=[
        P(
            "tasks",
            "array",
            (
                "JSON-Array von Tasks. Jeder Task: "
                "{\"task_id\": \"t1\", \"agent\": \"research\", \"task\": \"Beschreibung\", \"timeout\": 120}. "
                "task_id und timeout sind optional."
            ),
            required=True,
        ),
        P(
            "max_parallel",
            "integer",
            "Maximale Anzahl gleichzeitig laufender Agenten (Standard: 5, Max: 10)",
            required=False,
        ),
    ],
    capabilities=["orchestration"],
    category=C.SYSTEM,
    parallel_allowed=False,  # Dieses Tool selbst ist nicht parallel ausführbar
)
async def delegate_multiple_agents(
    tasks: List[Dict[str, Any]],
    max_parallel: int = 5,
) -> Dict[str, Any]:
    """
    Fan-Out: Startet alle Tasks parallel.
    Fan-In:  Bündelt Ergebnisse strukturiert.

    Gibt zurück:
        {
            "trace_id": "abc123",
            "total_tasks": 3,
            "success": 2, "partial": 0, "errors": 1,
            "results": [...],
            "summary": "2/3 erfolgreich | ..."
        }
    """
    from agent.agent_registry import agent_registry

    # Eingabe-Validierung
    if not tasks:
        return {
            "status": "error",
            "error": "tasks darf nicht leer sein",
        }

    # max_parallel auf sinnvollen Bereich begrenzen
    max_parallel = max(1, min(10, int(max_parallel)))

    log.info(
        f"[delegate_multiple_agents] {len(tasks)} Tasks | "
        f"max_parallel={max_parallel}"
    )

    result = await agent_registry.delegate_parallel(
        tasks=tasks,
        from_agent="meta",
        max_parallel=max_parallel,
    )

    log.info(
        f"[delegate_multiple_agents] Abgeschlossen: {result.get('summary', '')}"
    )

    return result
