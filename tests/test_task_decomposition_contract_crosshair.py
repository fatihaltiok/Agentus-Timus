from __future__ import annotations

import json

import deal

from orchestration.task_decomposition_contract import (
    build_task_decomposition,
    parse_task_decomposition,
)


@deal.post(lambda r: r == 1)
def _contract_build_setup_requests_are_plannable() -> int:
    decomposition = build_task_decomposition(
        source_query="Recherchiere eine Integration und richte sie dann bei mir ein.",
        orchestration_policy={
            "task_type": "integration_setup",
            "response_mode": "execute",
            "action_count": 2,
            "capability_count": 3,
        },
    )
    return 1 if decomposition["intent_family"] == "build_setup" and decomposition["planning_needed"] else 0


@deal.post(lambda r: r == 1)
def _contract_task_decomposition_parse_keeps_schema() -> int:
    decomposition = build_task_decomposition(
        source_query="Hole aus einem YouTube-Video maximal viel Inhalt raus und schreibe einen Bericht dazu.",
        orchestration_policy={
            "task_type": "youtube_content_extraction",
            "response_mode": "report",
            "action_count": 2,
            "capability_count": 4,
            "route_to_meta": True,
        },
    )
    parsed = parse_task_decomposition(json.dumps(decomposition, ensure_ascii=False))
    return 1 if parsed["schema_version"] == 1 and len(parsed["subtasks"]) >= 1 else 0
