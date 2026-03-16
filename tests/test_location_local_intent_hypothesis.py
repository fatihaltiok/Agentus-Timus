from __future__ import annotations

from hypothesis import given, strategies as st

from tests.test_location_local_intent_contracts import (
    _contract_analyze_location_local_intent,
    _contract_is_location_local_query,
)


@given(query=st.text(min_size=0, max_size=120))
def test_hypothesis_is_location_local_query_returns_bool(query: str) -> None:
    assert isinstance(_contract_is_location_local_query(query), bool)


@given(query=st.text(min_size=0, max_size=160))
def test_hypothesis_location_local_intent_returns_bounded_payload(query: str) -> None:
    result = _contract_analyze_location_local_intent(query)
    assert isinstance(result.maps_query, str)
    if result.is_location_only:
        assert result.maps_query == ""
