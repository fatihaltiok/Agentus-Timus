# tools/maintenance_tool/tool.py

import logging

from orchestration.memory_curation import (
    get_memory_curation_status as _get_memory_curation_status,
    rollback_memory_curation as _rollback_memory_curation,
    run_memory_curation_mvp as _run_memory_curation_mvp,
)
from tools.tool_registry_v2 import tool, ToolParameter as P, ToolCategory as C


log = logging.getLogger(__name__)


@tool(
    name="run_memory_maintenance",
    description=(
        "Fuehrt den E5 Memory-Curation-MVP aus: klassifiziert Memory-Items, "
        "fasst sichere Gruppen zusammen, archiviert alte ephemere Items, "
        "wertet stale topic-bound Items konservativ ab und legt einen Rollback-Snapshot an."
    ),
    parameters=[
        P("days_old_threshold", "integer", "Stale-Schwelle in Tagen fuer Curation (default: 30)", required=False, default=30),
        P("access_count_threshold", "integer", "Legacy-Kompatibilitaetsparameter ohne Wirkung im E5-MVP", required=False, default=5),
        P("max_actions", "integer", "Maximale Anzahl Curation-Aktionen pro Lauf (default: 12)", required=False, default=12),
        P("dry_run", "boolean", "Nur Kandidaten und Metriken berechnen, ohne Mutation (default: false)", required=False, default=False),
    ],
    capabilities=["memory", "maintenance"],
    category=C.MEMORY,
)
async def run_memory_maintenance(
    days_old_threshold: int = 30,
    access_count_threshold: int = 5,
    max_actions: int = 12,
    dry_run: bool = False,
) -> dict:
    log.info(
        "Starte Memory-Curation-MVP (stale_days=%s, max_actions=%s, dry_run=%s, legacy_access_threshold=%s)",
        days_old_threshold,
        max_actions,
        dry_run,
        access_count_threshold,
    )
    result = _run_memory_curation_mvp(
        stale_days=max(1, int(days_old_threshold)),
        max_actions=max(1, int(max_actions)),
        dry_run=bool(dry_run),
    )
    result["legacy_access_count_threshold"] = int(access_count_threshold)
    return result


@tool(
    name="get_memory_curation_status",
    description=(
        "Gibt den aktuellen E5-Memory-Curation-Status zurueck: laufende Metriken, "
        "letzte Snapshots und aktuell erkennbare Curation-Kandidaten."
    ),
    parameters=[
        P("days_old_threshold", "integer", "Stale-Schwelle in Tagen fuer Metriken und Kandidaten (default: 30)", required=False, default=30),
        P("limit", "integer", "Maximale Anzahl Kandidaten/Snapshoteintraege (default: 5)", required=False, default=5),
    ],
    capabilities=["memory", "maintenance"],
    category=C.MEMORY,
)
async def get_memory_curation_status(days_old_threshold: int = 30, limit: int = 5) -> dict:
    from orchestration.phase_e_operator_snapshot import (
        build_phase_e_operator_surface,
        collect_phase_e_operator_snapshot,
    )

    status = _get_memory_curation_status(
        stale_days=max(1, int(days_old_threshold)),
        limit=max(1, int(limit)),
    )
    operator_snapshot = await collect_phase_e_operator_snapshot(limit=max(1, min(10, int(limit))))
    status["operator_surface"] = build_phase_e_operator_surface(operator_snapshot, focus_lane="memory_curation")
    return status


@tool(
    name="rollback_memory_curation",
    description="Rollback einer vorherigen Memory-Curation-Runde ueber Snapshot-ID.",
    parameters=[
        P("snapshot_id", "string", "Snapshot-ID einer frueheren Memory-Curation-Runde", required=True),
    ],
    capabilities=["memory", "maintenance"],
    category=C.MEMORY,
)
async def rollback_memory_curation(snapshot_id: str) -> dict:
    return _rollback_memory_curation(str(snapshot_id or "").strip())
