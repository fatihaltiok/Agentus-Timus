from __future__ import annotations

import deal

from utils.location_local_intent import (
    analyze_location_local_intent,
    analyze_location_route_intent,
    is_location_local_query,
    is_location_route_query,
)


@deal.post(lambda r: isinstance(r, bool))
def _contract_is_location_local_query(query: str) -> bool:
    return is_location_local_query(query)


@deal.post(lambda r: isinstance(r, bool))
def _contract_is_location_route_query(query: str) -> bool:
    return is_location_route_query(query)


@deal.post(lambda r: isinstance(r.is_location_relevant, bool))
@deal.post(lambda r: isinstance(r.is_location_only, bool))
@deal.post(lambda r: isinstance(r.maps_query, str))
@deal.post(lambda r: isinstance(r.wants_open_now, bool))
@deal.ensure(lambda query, result: (result.is_location_only is False) or (result.maps_query == ""))
def _contract_analyze_location_local_intent(query: str):
    return analyze_location_local_intent(query)


@deal.post(lambda r: isinstance(r.is_route_request, bool))
@deal.post(lambda r: isinstance(r.destination_query, str))
@deal.post(lambda r: r.travel_mode in {"driving", "walking", "bicycling", "transit"})
def _contract_analyze_location_route_intent(query: str):
    return analyze_location_route_intent(query)


def test_contract_location_only_queries_have_empty_maps_query() -> None:
    result = _contract_analyze_location_local_intent("Wo bin ich?")
    assert result.is_location_only is True
    assert result.maps_query == ""


def test_contract_non_local_query_is_not_location_relevant() -> None:
    result = _contract_analyze_location_local_intent("Erzaehl mir einen Witz")
    assert result.is_location_relevant is False


def test_contract_route_queries_are_separate_from_local_search() -> None:
    result = _contract_analyze_location_route_intent("Route zur Zeil in Frankfurt")
    assert result.is_route_request is True
    assert _contract_is_location_route_query("Route zur Zeil in Frankfurt") is True
