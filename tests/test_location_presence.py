from __future__ import annotations

from utils.location_presence import (
    classify_location_freshness,
    enrich_location_presence_snapshot,
    prepare_location_presence_snapshot,
)


def test_classify_location_freshness_live_recent_and_stale() -> None:
    assert classify_location_freshness(effective_age_seconds=30, accuracy_meters=12.0)["presence_status"] == "live"
    assert classify_location_freshness(effective_age_seconds=1200, accuracy_meters=12.0)["presence_status"] == "recent"
    assert classify_location_freshness(effective_age_seconds=7200, accuracy_meters=12.0)["presence_status"] == "stale"


def test_classify_location_freshness_marks_poor_accuracy_unusable() -> None:
    result = classify_location_freshness(
        effective_age_seconds=120,
        accuracy_meters=400.0,
        max_context_accuracy_meters=250.0,
    )

    assert result["presence_status"] == "live"
    assert result["presence_reason"] == "poor_accuracy"
    assert result["usable_for_context"] is False


def test_prepare_location_presence_snapshot_adds_presence_metadata() -> None:
    prepared = prepare_location_presence_snapshot(
        {
            "latitude": 52.52,
            "longitude": 13.40,
        },
        received_at="2026-03-16T08:00:00Z",
    )

    assert prepared["received_at"] == "2026-03-16T08:00:00Z"
    assert prepared["device_id"] == "primary_mobile"
    assert prepared["user_scope"] == "primary"


def test_enrich_location_presence_snapshot_detects_missing_coordinates() -> None:
    enriched = enrich_location_presence_snapshot(
        {
            "display_name": "Unknown",
            "captured_at": "2026-03-16T08:00:00Z",
            "received_at": "2026-03-16T08:00:05Z",
        }
    )

    assert enriched is not None
    assert enriched["presence_status"] == "unknown"
    assert enriched["presence_reason"] == "missing_coordinates"
    assert enriched["usable_for_context"] is False
