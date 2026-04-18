from __future__ import annotations

import json

import deal

from orchestration.specialist_step_package import (
    build_specialist_step_package_payload,
    parse_specialist_step_package_payload,
)


@deal.post(lambda r: r == 1)
def _contract_specialist_step_package_keeps_step_identity() -> int:
    payload = build_specialist_step_package_payload(
        plan_summary={"plan_id": "plan_z4", "goal": "Setup abschliessen"},
        plan_step={"id": "step_1", "title": "Konfiguration anwenden"},
        previous_stage_result="Vorbedingungen erfuellt",
    )
    parsed = parse_specialist_step_package_payload(json.dumps(payload, ensure_ascii=False))
    return 1 if parsed["step_id"] == "step_1" and parsed["focus_context"]["previous_stage_result"] else 0
