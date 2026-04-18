from __future__ import annotations

import deal

from orchestration.conversation_state import normalize_conversation_state


@deal.post(lambda r: r == 1)
def _contract_active_plan_seeds_next_step() -> int:
    state = normalize_conversation_state(
        {
            "active_plan": {
                "plan_id": "z3_contract_plan",
                "plan_mode": "multi_step_execution",
                "goal": "YouTube-Inhalt sammeln",
                "next_step_id": "visual_access",
                "next_step_title": "YouTube-Seite oeffnen",
                "next_step_agent": "visual",
                "step_count": 3,
            }
        },
        session_id="z3_contract",
        last_updated="2026-04-18T12:10:00Z",
    )
    return 1 if state.active_plan and state.next_expected_step and state.open_loop else 0
