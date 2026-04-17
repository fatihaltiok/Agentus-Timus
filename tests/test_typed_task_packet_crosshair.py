from __future__ import annotations

import deal

from orchestration.typed_task_packet import build_request_preflight, build_typed_task_packet


@deal.post(lambda r: r == 1)
def _contract_packet_schema_and_type() -> int:
    packet = build_typed_task_packet(
        packet_type="meta_orchestration",
        objective="Bitte plane den Ablauf.",
    )
    return 1 if packet["schema_version"] == 1 and packet["packet_type"] == "meta_orchestration" else 0


@deal.post(lambda r: r == 1)
def _contract_preflight_flags_oversized_request() -> int:
    packet = build_typed_task_packet(
        packet_type="meta_orchestration",
        objective="Recherchiere aktuelle Fakten.",
        allowed_tools=["start_deep_research"],
    )
    report = build_request_preflight(
        packet=packet,
        original_request="q" * 5000,
        rendered_handoff="# META ORCHESTRATION HANDOFF",
        task_type="knowledge_research",
        recipe_id="knowledge_research",
    )
    return 1 if report["state"] in {"warn", "blocked"} and len(report["issues"]) >= 1 else 0
