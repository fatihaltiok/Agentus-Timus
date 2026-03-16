from __future__ import annotations

import deal

from utils.location_reroute import (
    apply_live_reroute_metadata,
    assess_live_reroute,
    distance_meters,
)


@deal.post(lambda r: r is None or r >= 0)
def _contract_distance_meters(a_lat: float, a_lon: float, b_lat: float, b_lon: float):
    return distance_meters(a_lat, a_lon, b_lat, b_lon)


@deal.post(lambda r: isinstance(r["should_reroute"], bool))
@deal.post(lambda r: isinstance(r["reason"], str) and bool(r["reason"]))
def _contract_assess_live_reroute(route_snapshot: dict, location_snapshot: dict, min_distance_meters: int, min_interval_seconds: int):
    return assess_live_reroute(
        route_snapshot,
        location_snapshot,
        min_distance_meters=min_distance_meters,
        min_interval_seconds=min_interval_seconds,
    )


@deal.post(lambda r: r["reroute_count"] >= 1)
@deal.post(lambda r: r["route_status"] == "active")
def _contract_apply_live_reroute_metadata(new_snapshot: dict, previous_snapshot: dict, location_snapshot: dict, moved_distance_meters: int | None, reroute_reason: str, rerouted_at: str):
    return apply_live_reroute_metadata(
        new_snapshot,
        previous_snapshot,
        location_snapshot,
        moved_distance_meters=moved_distance_meters,
        reroute_reason=reroute_reason,
        rerouted_at=rerouted_at,
    )


def test_contract_assess_live_reroute_inactive_route() -> None:
    result = _contract_assess_live_reroute({}, {}, 150, 120)
    assert result["reason"] == "no_active_route"


def test_contract_apply_live_reroute_metadata_sets_active_status() -> None:
    result = _contract_apply_live_reroute_metadata(
        {"has_route": True},
        {"reroute_count": 0},
        {"captured_at": "2026-03-16T14:59:00Z"},
        250,
        "movement_threshold_exceeded",
        "2026-03-16T15:00:00Z",
    )
    assert result["route_status"] == "active"
