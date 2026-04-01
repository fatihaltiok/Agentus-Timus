from __future__ import annotations

import deal
from hypothesis import given, settings
from hypothesis import strategies as st

from orchestration.meta_orchestration import (
    _apply_semantic_review_override,
    _derive_semantic_review_payload,
)


@deal.post(lambda r: isinstance(r, dict))
@deal.post(lambda r: isinstance(r.get("semantic_ambiguity_hints"), list))
@deal.post(lambda r: isinstance(r.get("semantic_review_recommended"), bool))
def _contract_semantic_review_payload(text: str, has_simple_live_lookup: bool, has_local_search: bool) -> dict:
    return _derive_semantic_review_payload(
        text,
        has_simple_live_lookup=has_simple_live_lookup,
        has_local_search=has_local_search,
    )


@given(st.text(max_size=120), st.booleans(), st.booleans())
@settings(max_examples=80)
def test_hypothesis_semantic_review_payload_shape(
    text: str,
    has_simple_live_lookup: bool,
    has_local_search: bool,
):
    result = _contract_semantic_review_payload(text, has_simple_live_lookup, has_local_search)
    assert all(isinstance(item, str) for item in result["semantic_ambiguity_hints"])
    if not result["semantic_ambiguity_hints"]:
        assert result["semantic_review_recommended"] is False


@deal.post(lambda r: isinstance(r, dict))
@deal.post(lambda r: isinstance(r.get("recommended_agent_chain"), list))
@deal.post(lambda r: isinstance(r.get("needs_structured_handoff"), bool))
def _contract_semantic_review_override(base_reason: str, semantic_hints: list[str]) -> dict:
    base = {
        "task_type": "simple_live_lookup",
        "site_kind": None,
        "required_capabilities": ["live_lookup"],
        "recommended_entry_agent": "meta",
        "recommended_agent_chain": ["meta", "executor"],
        "needs_structured_handoff": True,
        "reason": base_reason,
        "recommended_recipe_id": "simple_live_lookup",
        "recipe_stages": [{"stage_id": "live_lookup_scan"}],
        "recipe_recoveries": [],
        "alternative_recipes": [],
    }
    semantic_review = {
        "semantic_ambiguity_hints": semantic_hints,
        "semantic_review_recommended": bool(semantic_hints),
    }
    return _apply_semantic_review_override(base, semantic_review)


@given(st.text(max_size=80), st.lists(st.sampled_from([
    "mixed_personal_preference_and_wealth_strategy",
    "business_strategy_vs_local_lookup",
    "user_reported_location_state_update",
]), max_size=3, unique=True))
@settings(max_examples=40)
def test_hypothesis_semantic_review_override_shape(base_reason: str, semantic_hints: list[str]):
    result = _contract_semantic_review_override(base_reason, semantic_hints)
    if semantic_hints:
        assert result["recommended_agent_chain"] == ["meta"]
        assert result["recommended_recipe_id"] is None
