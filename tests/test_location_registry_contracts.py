from __future__ import annotations

import deal

from utils.location_registry import (
    build_location_status_payload,
    normalize_location_controls,
    select_active_location_snapshot,
    sync_mode_allowed,
)


@deal.post(lambda r: isinstance(r["allowed_user_scopes"], list) and len(r["allowed_user_scopes"]) >= 1)
@deal.post(lambda r: isinstance(r["sharing_enabled"], bool))
def _contract_normalize_location_controls(payload: dict):
    return normalize_location_controls(payload)


@deal.post(lambda r: isinstance(r[1], list))
@deal.post(lambda r: isinstance(r[2], str))
def _contract_select_active_location_snapshot(registry: dict, controls: dict):
    return select_active_location_snapshot(registry, controls)


@deal.post(lambda r: isinstance(r["device_count"], int) and r["device_count"] >= 0)
def _contract_build_location_status_payload(registry: dict, controls: dict):
    return build_location_status_payload(registry, controls)


def test_contract_normalize_location_controls_defaults_scope() -> None:
    result = _contract_normalize_location_controls({})
    assert result["allowed_user_scopes"] == ["primary"]


def test_contract_sync_mode_allowed_foreground() -> None:
    assert sync_mode_allowed("foreground", {"background_sync_allowed": False}) is True
