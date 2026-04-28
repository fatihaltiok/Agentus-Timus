"""Contracts fuer Behavior-Preference-Turns in Ausbaustufe 5."""

from __future__ import annotations

import deal
from hypothesis import given, settings
from hypothesis import strategies as st

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
def _contract_style_preference_route() -> dict[str, object]:
    return _route("speichere dir dass ich kurze antworten bevorzuge")


@deal.post(lambda r: r["dominant_turn_type"] == "behavior_instruction")
@deal.post(lambda r: r["response_mode"] == "acknowledge_and_store")
@deal.post(lambda r: r["route_bias"] == "meta_only")
@deal.post(lambda r: r["update_preferences"] is True)
def _contract_conditional_research_preference_route() -> dict[str, object]:
    return _route("wenn du recherchierst nenne mir immer die quellen direkt mit links")


@deal.post(lambda r: r["dominant_turn_type"] == "behavior_instruction")
@deal.post(lambda r: r["response_mode"] == "acknowledge_and_store")
@deal.post(lambda r: r["route_bias"] == "meta_only")
@deal.post(lambda r: r["update_preferences"] is False)
@deal.post(lambda r: r["remove_last_preference"] is True)
def _contract_preference_delete_route() -> dict[str, object]:
    return _route("vergiss die letzte praferenz die ich dir gegeben habe")


def test_contract_style_preference_route() -> None:
    assert _contract_style_preference_route()["update_preferences"] is True


def test_contract_conditional_research_preference_route() -> None:
    assert _contract_conditional_research_preference_route()["update_preferences"] is True


def test_contract_preference_delete_route() -> None:
    assert _contract_preference_delete_route()["remove_last_preference"] is True


@given(
    style=st.sampled_from(("kurze antworten", "kurz antworten", "weniger formal")),
    prefix=st.sampled_from(("speichere dir dass ich", "merk dir dass ich")),
)
@settings(max_examples=30)
def test_hypothesis_style_preferences_route_to_meta_store(style: str, prefix: str) -> None:
    result = _route(f"{prefix} {style} bevorzuge")

    assert result["dominant_turn_type"] == "behavior_instruction"
    assert result["response_mode"] == "acknowledge_and_store"
    assert result["update_preferences"] is True
    assert result["remove_last_preference"] is False


@given(
    topic=st.sampled_from(("coding fragen", "research aufgaben", "recherchen")),
    ordering=st.sampled_from(("zuerst", "immer")),
)
@settings(max_examples=20)
def test_hypothesis_conditional_work_preferences_route_to_meta_store(topic: str, ordering: str) -> None:
    result = _route(f"fuer {topic} gib mir {ordering} den kuerzesten brauchbaren weg")

    assert result["dominant_turn_type"] == "behavior_instruction"
    assert result["response_mode"] == "acknowledge_and_store"
    assert result["update_preferences"] is True
    assert result["remove_last_preference"] is False


@given(verb=st.sampled_from(("vergiss", "loesche", "lösche")))
@settings(max_examples=10)
def test_hypothesis_preference_delete_does_not_append_preference(verb: str) -> None:
    result = _route(f"{verb} die letzte praferenz die ich dir gegeben habe")

    assert result["dominant_turn_type"] == "behavior_instruction"
    assert result["response_mode"] == "acknowledge_and_store"
    assert result["update_preferences"] is False
    assert result["remove_last_preference"] is True
