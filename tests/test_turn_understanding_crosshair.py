"""CrossHair-safe contracts for turn-understanding preference routes.

This module intentionally avoids importing Hypothesis. CrossHair's audit wall
can reject Hypothesis plugin imports before it reaches the pure contract code.
"""

from __future__ import annotations

import deal

from orchestration.turn_understanding import build_turn_understanding_input, interpret_turn


def _route(query: str) -> dict[str, object]:
    interpretation = interpret_turn(
        build_turn_understanding_input(
            raw_query=query,
            effective_query=query,
            dialog_state={},
            semantic_review_hints=[],
        )
    )
    effects = interpretation.state_effects.to_dict()
    return {
        "dominant_turn_type": interpretation.dominant_turn_type,
        "response_mode": interpretation.response_mode,
        "route_bias": interpretation.route_bias,
        "update_preferences": bool(effects.get("update_preferences")),
        "remove_last_preference": bool(effects.get("remove_last_preference")),
    }


@deal.post(lambda r: r["dominant_turn_type"] == "behavior_instruction")
@deal.post(lambda r: r["response_mode"] == "acknowledge_and_store")
@deal.post(lambda r: r["route_bias"] == "meta_only")
@deal.post(lambda r: r["update_preferences"] is True)
def _contract_conditional_research_preference_route() -> dict[str, object]:
    return _route("wenn du recherchierst nenne mir immer die quellen direkt mit links")


@deal.post(lambda r: r["dominant_turn_type"] == "behavior_instruction")
@deal.post(lambda r: r["response_mode"] == "acknowledge_and_store")
@deal.post(lambda r: r["route_bias"] == "meta_only")
@deal.post(lambda r: r["update_preferences"] is True)
def _contract_coding_preference_route() -> dict[str, object]:
    return _route("fuer coding fragen gib mir zuerst den kuerzesten funktionierenden fix")


def test_contract_conditional_research_preference_route() -> None:
    assert _contract_conditional_research_preference_route()["update_preferences"] is True


def test_contract_coding_preference_route() -> None:
    assert _contract_coding_preference_route()["update_preferences"] is True
