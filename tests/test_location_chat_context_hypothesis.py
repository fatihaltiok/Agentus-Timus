from __future__ import annotations

from hypothesis import given, strategies as st

from tests.test_location_chat_context_contracts import (
    _contract_build_location_chat_context_block,
    _contract_evaluate_location_chat_context,
    _contract_is_location_context_query,
)


@given(query=st.text(min_size=0, max_size=120))
def test_hypothesis_is_location_context_query_returns_bool(query: str) -> None:
    assert isinstance(_contract_is_location_context_query(query), bool)


@given(
    query=st.text(min_size=0, max_size=120),
    enabled=st.booleans(),
    presence_status=st.sampled_from(["live", "recent", "stale", "unknown", "weird"]),
    usable_for_context=st.booleans(),
    has_coordinates=st.booleans(),
)
def test_hypothesis_evaluate_location_chat_context_is_bounded(
    query: str,
    enabled: bool,
    presence_status: str,
    usable_for_context: bool,
    has_coordinates: bool,
) -> None:
    result = _contract_evaluate_location_chat_context(
        query,
        {
            "presence_status": presence_status,
            "usable_for_context": usable_for_context,
            "has_coordinates": has_coordinates,
        },
        enabled,
    )
    assert result.presence_status in {"live", "recent", "stale", "unknown"}


@given(
    presence_status=st.sampled_from(["live", "recent", "stale", "unknown"]),
)
def test_hypothesis_build_location_chat_context_block_has_required_markers(
    presence_status: str,
) -> None:
    block = _contract_build_location_chat_context_block({"presence_status": presence_status})
    assert "# LIVE LOCATION CONTEXT" in block
