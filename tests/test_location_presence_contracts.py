from __future__ import annotations

import deal

from utils.location_presence import classify_location_freshness, prepare_location_presence_snapshot


@deal.post(lambda r: r["presence_status"] in {"live", "recent", "stale", "unknown"})
@deal.post(lambda r: isinstance(r["usable_for_context"], bool))
@deal.ensure(lambda effective_age_seconds, accuracy_meters, result: (effective_age_seconds is None) or (int(effective_age_seconds) <= result["recent_max_age_seconds"]) or (result["usable_for_context"] is False))
def _contract_classify_location_freshness(
    effective_age_seconds: int | None,
    accuracy_meters: float | None,
):
    return classify_location_freshness(
        effective_age_seconds=effective_age_seconds,
        accuracy_meters=accuracy_meters,
    )


@deal.post(lambda r: "received_at" in r and bool(r["received_at"]))
@deal.post(lambda r: bool(r["device_id"]))
@deal.post(lambda r: bool(r["user_scope"]))
def _contract_prepare_location_presence_snapshot(snapshot: dict):
    return prepare_location_presence_snapshot(snapshot)


def test_contract_classify_location_freshness_unknown_without_age() -> None:
    result = _contract_classify_location_freshness(None, 5.0)
    assert result["presence_status"] == "unknown"


def test_contract_prepare_location_presence_snapshot_defaults() -> None:
    prepared = _contract_prepare_location_presence_snapshot({"latitude": 52.52, "longitude": 13.4})
    assert prepared["device_id"] == "primary_mobile"
    assert prepared["user_scope"] == "primary"
