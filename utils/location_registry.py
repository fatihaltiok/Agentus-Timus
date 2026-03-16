from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

from utils.location_presence import enrich_location_presence_snapshot


_ENV_SHARING_ENABLED = "TIMUS_LOCATION_SHARING_ENABLED"
_ENV_CONTEXT_ENABLED = "TIMUS_LOCATION_CONTEXT_ENABLED"
_ENV_BACKGROUND_SYNC_ALLOWED = "TIMUS_LOCATION_BACKGROUND_SYNC_ALLOWED"
_ENV_PREFERRED_DEVICE_ID = "TIMUS_LOCATION_PREFERRED_DEVICE_ID"
_ENV_ALLOWED_USER_SCOPES = "TIMUS_LOCATION_ALLOWED_USER_SCOPES"
_ENV_MAX_DEVICE_ENTRIES = "TIMUS_LOCATION_MAX_DEVICE_ENTRIES"


def _env_bool(name: str, default: bool) -> bool:
    raw = str(os.getenv(name, "1" if default else "0")).strip().lower()
    if raw in {"1", "true", "yes", "on"}:
        return True
    if raw in {"0", "false", "no", "off"}:
        return False
    return default


def _safe_int(value: Any, default: int) -> int:
    if value in (None, ""):
        return default
    try:
        return int(value)
    except Exception:
        return default


def _parse_timestamp(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except Exception:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _isoformat_utc(value: datetime | None = None) -> str:
    current = value.astimezone(timezone.utc) if value else datetime.now(timezone.utc)
    return current.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _normalize_scope_list(value: Any) -> list[str]:
    if isinstance(value, (list, tuple, set)):
        raw_items = [str(item or "").strip().lower() for item in value]
    else:
        raw_items = [part.strip().lower() for part in str(value or "").split(",")]
    normalized: list[str] = []
    for item in raw_items:
        if not item or item in normalized:
            continue
        normalized.append(item)
    return normalized or ["primary"]


def normalize_location_controls(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    raw = dict(payload or {})
    return {
        "sharing_enabled": bool(raw.get("sharing_enabled")) if "sharing_enabled" in raw else _env_bool(_ENV_SHARING_ENABLED, True),
        "context_enabled": bool(raw.get("context_enabled")) if "context_enabled" in raw else _env_bool(_ENV_CONTEXT_ENABLED, True),
        "background_sync_allowed": (
            bool(raw.get("background_sync_allowed"))
            if "background_sync_allowed" in raw
            else _env_bool(_ENV_BACKGROUND_SYNC_ALLOWED, True)
        ),
        "preferred_device_id": str(raw.get("preferred_device_id") or os.getenv(_ENV_PREFERRED_DEVICE_ID, "")).strip(),
        "allowed_user_scopes": _normalize_scope_list(
            raw.get("allowed_user_scopes", os.getenv(_ENV_ALLOWED_USER_SCOPES, "primary"))
        ),
        "max_device_entries": max(1, _safe_int(raw.get("max_device_entries", os.getenv(_ENV_MAX_DEVICE_ENTRIES, "8")), 8)),
        "updated_at": str(raw.get("updated_at") or _isoformat_utc()),
    }


def sync_mode_allowed(sync_mode: str, controls: dict[str, Any]) -> bool:
    normalized = str(sync_mode or "foreground").strip().lower()
    if normalized != "background":
        return True
    return bool((controls or {}).get("background_sync_allowed", True))


def apply_location_controls_to_snapshot(snapshot: dict[str, Any] | None, controls: dict[str, Any] | None) -> dict[str, Any] | None:
    enriched = enrich_location_presence_snapshot(snapshot or {})
    if not enriched:
        return None

    safe_controls = normalize_location_controls(controls)
    scope = str(enriched.get("user_scope") or "primary").strip().lower()
    allowed_scopes = list(safe_controls.get("allowed_user_scopes", ["primary"]))
    scope_allowed = scope in allowed_scopes
    control_blocked_reason = ""
    usable_for_context = bool(enriched.get("usable_for_context"))

    if not bool(safe_controls.get("sharing_enabled", True)):
        usable_for_context = False
        control_blocked_reason = "sharing_disabled"
    elif not bool(safe_controls.get("context_enabled", True)):
        usable_for_context = False
        control_blocked_reason = "context_disabled"
    elif not scope_allowed:
        usable_for_context = False
        control_blocked_reason = "user_scope_blocked"

    privacy_state = "enabled"
    if control_blocked_reason:
        privacy_state = "blocked"
    elif not bool(enriched.get("usable_for_context")):
        privacy_state = "limited"

    controlled = dict(enriched)
    controlled["usable_for_context"] = usable_for_context
    controlled["sharing_enabled"] = bool(safe_controls.get("sharing_enabled", True))
    controlled["context_enabled"] = bool(safe_controls.get("context_enabled", True))
    controlled["background_sync_allowed"] = bool(safe_controls.get("background_sync_allowed", True))
    controlled["scope_allowed"] = scope_allowed
    controlled["allowed_user_scopes"] = allowed_scopes
    controlled["control_blocked_reason"] = control_blocked_reason
    controlled["privacy_state"] = privacy_state
    return controlled


def normalize_location_registry(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    safe = dict(payload or {})
    devices = safe.get("devices")
    if not isinstance(devices, list):
        devices = []
    normalized_devices = [dict(item) for item in devices if isinstance(item, dict)]
    return {
        "devices": normalized_devices,
        "updated_at": str(safe.get("updated_at") or _isoformat_utc()),
    }


def update_location_registry(
    registry: dict[str, Any] | None,
    snapshot: dict[str, Any],
    *,
    max_entries: int,
) -> dict[str, Any]:
    normalized = normalize_location_registry(registry)
    key_device = str(snapshot.get("device_id") or "primary_mobile").strip() or "primary_mobile"
    key_scope = str(snapshot.get("user_scope") or "primary").strip() or "primary"
    devices = [
        item
        for item in normalized["devices"]
        if str(item.get("device_id") or "").strip() != key_device
        or str(item.get("user_scope") or "").strip() != key_scope
    ]
    devices.append(dict(snapshot))
    devices.sort(
        key=lambda item: (
            _parse_timestamp(item.get("received_at")) or datetime.min.replace(tzinfo=timezone.utc),
            _parse_timestamp(item.get("captured_at")) or datetime.min.replace(tzinfo=timezone.utc),
        ),
        reverse=True,
    )
    normalized["devices"] = devices[: max(1, int(max_entries))]
    normalized["updated_at"] = _isoformat_utc()
    return normalized


def _presence_rank(value: str) -> int:
    normalized = str(value or "unknown").strip().lower()
    return {"live": 3, "recent": 2, "stale": 1, "unknown": 0}.get(normalized, 0)


def _accuracy_rank(value: Any) -> float:
    try:
        parsed = float(value)
    except Exception:
        return -1_000_000.0
    if parsed <= 0:
        return -1_000_000.0
    return -parsed


def select_active_location_snapshot(
    registry: dict[str, Any] | None,
    controls: dict[str, Any] | None,
    *,
    fallback_snapshot: dict[str, Any] | None = None,
) -> tuple[dict[str, Any] | None, list[dict[str, Any]], str]:
    safe_controls = normalize_location_controls(controls)
    safe_registry = normalize_location_registry(registry)
    candidates = [dict(item) for item in safe_registry["devices"]]
    if not candidates and isinstance(fallback_snapshot, dict) and fallback_snapshot:
        candidates = [dict(fallback_snapshot)]

    controlled_devices: list[dict[str, Any]] = []
    preferred_device_id = str(safe_controls.get("preferred_device_id") or "").strip()
    for raw in candidates:
        controlled = apply_location_controls_to_snapshot(raw, safe_controls)
        if controlled:
            controlled["is_preferred_device"] = bool(preferred_device_id and controlled.get("device_id") == preferred_device_id)
            controlled_devices.append(controlled)

    if not controlled_devices:
        return None, [], "missing_location_snapshot"

    controlled_devices.sort(
        key=lambda item: (
            1 if item.get("is_preferred_device") and item.get("presence_status") in {"live", "recent"} else 0,
            1 if item.get("usable_for_context") else 0,
            _presence_rank(str(item.get("presence_status") or "unknown")),
            _parse_timestamp(item.get("received_at")) or datetime.min.replace(tzinfo=timezone.utc),
            _accuracy_rank(item.get("accuracy_meters")),
        ),
        reverse=True,
    )
    selected = dict(controlled_devices[0])
    selected["selected_device_count"] = len(controlled_devices)
    if selected.get("is_preferred_device") and selected.get("presence_status") in {"live", "recent"}:
        reason = "preferred_device"
    elif selected.get("usable_for_context"):
        reason = "freshest_usable_device"
    elif _presence_rank(str(selected.get("presence_status") or "unknown")) > 0:
        reason = "freshest_device_fallback"
    else:
        reason = "latest_device_fallback"
    selected["selection_reason"] = reason

    summarized_devices = []
    for item in controlled_devices:
        summary = dict(item)
        summary["selected"] = (
            summary.get("device_id") == selected.get("device_id")
            and summary.get("user_scope") == selected.get("user_scope")
        )
        summarized_devices.append(summary)
    return selected, summarized_devices, reason


def build_location_status_payload(
    registry: dict[str, Any] | None,
    controls: dict[str, Any] | None,
    *,
    fallback_snapshot: dict[str, Any] | None = None,
) -> dict[str, Any]:
    safe_controls = normalize_location_controls(controls)
    selected, devices, selection_reason = select_active_location_snapshot(
        registry,
        safe_controls,
        fallback_snapshot=fallback_snapshot,
    )
    return {
        "location": selected,
        "devices": devices,
        "controls": safe_controls,
        "device_count": len(devices),
        "selection_reason": selection_reason,
        "active_device_id": str((selected or {}).get("device_id") or "").strip(),
        "active_user_scope": str((selected or {}).get("user_scope") or "").strip(),
    }
