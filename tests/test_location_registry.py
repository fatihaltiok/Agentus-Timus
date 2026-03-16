from __future__ import annotations

from utils.location_registry import (
    apply_location_controls_to_snapshot,
    build_location_status_payload,
    normalize_location_controls,
    select_active_location_snapshot,
    sync_mode_allowed,
    update_location_registry,
)


def test_normalize_location_controls_defaults() -> None:
    controls = normalize_location_controls({})

    assert controls["sharing_enabled"] is True
    assert controls["context_enabled"] is True
    assert controls["background_sync_allowed"] is True
    assert controls["allowed_user_scopes"] == ["primary"]


def test_apply_location_controls_blocks_scope() -> None:
    snapshot = apply_location_controls_to_snapshot(
        {
            "latitude": 52.520008,
            "longitude": 13.404954,
            "captured_at": "2026-03-16T15:00:00Z",
            "user_scope": "guest",
        },
        {
            "sharing_enabled": True,
            "context_enabled": True,
            "background_sync_allowed": True,
            "preferred_device_id": "",
            "allowed_user_scopes": ["primary"],
            "max_device_entries": 8,
        },
    )

    assert snapshot is not None
    assert snapshot["usable_for_context"] is False
    assert snapshot["control_blocked_reason"] == "user_scope_blocked"


def test_update_location_registry_replaces_same_device() -> None:
    registry = update_location_registry(
        {"devices": [{"device_id": "phone_a", "user_scope": "primary", "received_at": "2026-03-16T14:00:00Z"}]},
        {"device_id": "phone_a", "user_scope": "primary", "received_at": "2026-03-16T15:00:00Z"},
        max_entries=8,
    )

    assert len(registry["devices"]) == 1
    assert registry["devices"][0]["received_at"] == "2026-03-16T15:00:00Z"


def test_select_active_location_snapshot_prefers_fresh_preferred_device() -> None:
    selected, devices, reason = select_active_location_snapshot(
        {
            "devices": [
                {
                    "device_id": "phone_a",
                    "user_scope": "primary",
                    "latitude": 52.520008,
                    "longitude": 13.404954,
                    "captured_at": "2026-03-16T15:00:00Z",
                    "received_at": "2026-03-16T15:00:00Z",
                    "presence_status": "live",
                    "usable_for_context": True,
                    "accuracy_meters": 12,
                },
                {
                    "device_id": "phone_b",
                    "user_scope": "primary",
                    "latitude": 48.137154,
                    "longitude": 11.576124,
                    "captured_at": "2026-03-16T15:00:00Z",
                    "received_at": "2026-03-16T15:00:00Z",
                    "presence_status": "live",
                    "usable_for_context": True,
                    "accuracy_meters": 8,
                },
            ]
        },
        {
            "sharing_enabled": True,
            "context_enabled": True,
            "background_sync_allowed": True,
            "preferred_device_id": "phone_a",
            "allowed_user_scopes": ["primary"],
            "max_device_entries": 8,
        },
    )

    assert selected is not None
    assert selected["device_id"] == "phone_a"
    assert reason == "preferred_device"
    assert len(devices) == 2


def test_build_location_status_payload_reports_active_device() -> None:
    payload = build_location_status_payload(
        {
            "devices": [
                {
                    "device_id": "phone_main",
                    "user_scope": "primary",
                    "latitude": 52.520008,
                    "longitude": 13.404954,
                    "captured_at": "2026-03-16T15:00:00Z",
                    "received_at": "2026-03-16T15:00:00Z",
                }
            ]
        },
        {
            "sharing_enabled": True,
            "context_enabled": True,
            "background_sync_allowed": True,
            "preferred_device_id": "",
            "allowed_user_scopes": ["primary"],
            "max_device_entries": 8,
        },
    )

    assert payload["active_device_id"] == "phone_main"
    assert payload["device_count"] == 1


def test_sync_mode_allowed_blocks_background_when_disabled() -> None:
    assert sync_mode_allowed("background", {"background_sync_allowed": False}) is False
    assert sync_mode_allowed("foreground", {"background_sync_allowed": False}) is True
