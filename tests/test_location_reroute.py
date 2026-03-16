from __future__ import annotations

from datetime import datetime, timedelta, timezone

from utils.location_reroute import (
    apply_live_reroute_metadata,
    assess_live_reroute,
    distance_meters,
)


def test_distance_meters_returns_positive_distance() -> None:
    result = distance_meters(52.520008, 13.404954, 52.507507, 13.390373)

    assert result is not None
    assert result > 0


def test_assess_live_reroute_recommends_after_movement_threshold() -> None:
    now = datetime(2026, 3, 16, 15, 0, tzinfo=timezone.utc)
    decision = assess_live_reroute(
        {
            "has_route": True,
            "destination_query": "Checkpoint Charlie Berlin",
            "saved_at": "2026-03-16T14:45:00Z",
            "start_coordinates": {"latitude": 52.520008, "longitude": 13.404954},
        },
        {
            "latitude": 52.507507,
            "longitude": 13.390373,
            "presence_status": "live",
            "usable_for_context": True,
        },
        min_distance_meters=150,
        min_interval_seconds=120,
        now=now,
    )

    assert decision["should_reroute"] is True
    assert decision["reason"] == "movement_threshold_exceeded"
    assert decision["moved_distance_meters"] >= 150


def test_assess_live_reroute_blocks_small_movement() -> None:
    now = datetime(2026, 3, 16, 15, 0, tzinfo=timezone.utc)
    decision = assess_live_reroute(
        {
            "has_route": True,
            "destination_query": "Checkpoint Charlie Berlin",
            "saved_at": "2026-03-16T14:45:00Z",
            "start_coordinates": {"latitude": 52.520008, "longitude": 13.404954},
        },
        {
            "latitude": 52.520308,
            "longitude": 13.405154,
            "presence_status": "live",
            "usable_for_context": True,
        },
        min_distance_meters=150,
        min_interval_seconds=120,
        now=now,
    )

    assert decision["should_reroute"] is False
    assert decision["reason"] == "movement_below_threshold"


def test_assess_live_reroute_honors_cooldown() -> None:
    now = datetime(2026, 3, 16, 15, 0, tzinfo=timezone.utc)
    decision = assess_live_reroute(
        {
            "has_route": True,
            "destination_query": "Checkpoint Charlie Berlin",
            "last_reroute_at": "2026-03-16T14:58:45Z",
            "start_coordinates": {"latitude": 52.520008, "longitude": 13.404954},
        },
        {
            "latitude": 52.507507,
            "longitude": 13.390373,
            "presence_status": "live",
            "usable_for_context": True,
        },
        min_distance_meters=150,
        min_interval_seconds=120,
        now=now,
    )

    assert decision["should_reroute"] is False
    assert decision["reason"] == "cooldown_active"


def test_apply_live_reroute_metadata_increments_counter() -> None:
    rerouted_at = (datetime.now(timezone.utc) + timedelta(minutes=5)).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    result = apply_live_reroute_metadata(
        {
            "has_route": True,
            "destination_query": "Checkpoint Charlie Berlin",
            "saved_at": rerouted_at,
        },
        {
            "saved_at": "2026-03-16T14:30:00Z",
            "route_started_at": "2026-03-16T14:30:00Z",
            "reroute_count": 1,
        },
        {"captured_at": "2026-03-16T14:59:00Z"},
        moved_distance_meters=340,
        reroute_reason="movement_threshold_exceeded",
        rerouted_at=rerouted_at,
    )

    assert result["reroute_count"] == 2
    assert result["route_started_at"] == "2026-03-16T14:30:00Z"
    assert result["last_reroute_at"] == rerouted_at
    assert result["reroute_trigger_distance_meters"] == 340
