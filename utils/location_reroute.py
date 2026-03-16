from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any


def _as_float(value: Any) -> float | None:
    try:
        if value in (None, ""):
            return None
        return float(value)
    except Exception:
        return None


def _as_int(value: Any, default: int = 0) -> int:
    try:
        if value in (None, ""):
            return default
        return int(value)
    except Exception:
        return default


def _parse_timestamp(value: Any) -> datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    normalized = raw.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _route_origin_coordinates(route_snapshot: dict[str, Any]) -> tuple[float, float] | None:
    for key in ("start_coordinates", "origin"):
        raw = route_snapshot.get(key)
        if not isinstance(raw, dict):
            continue
        latitude = _as_float(raw.get("latitude", raw.get("lat")))
        longitude = _as_float(raw.get("longitude", raw.get("lng", raw.get("lon"))))
        if latitude is None or longitude is None:
            continue
        return latitude, longitude
    return None


def distance_meters(
    origin_latitude: float | None,
    origin_longitude: float | None,
    target_latitude: float | None,
    target_longitude: float | None,
) -> int | None:
    if None in {origin_latitude, origin_longitude, target_latitude, target_longitude}:
        return None
    try:
        origin_lat = float(origin_latitude)
        origin_lon = float(origin_longitude)
        target_lat = float(target_latitude)
        target_lon = float(target_longitude)
    except Exception:
        return None
    if not all(math.isfinite(value) for value in (origin_lat, origin_lon, target_lat, target_lon)):
        return None
    radius_m = 6_371_000
    lat1 = math.radians(origin_lat)
    lon1 = math.radians(origin_lon)
    lat2 = math.radians(target_lat)
    lon2 = math.radians(target_lon)
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return int(radius_m * c)


def assess_live_reroute(
    route_snapshot: dict[str, Any] | None,
    location_snapshot: dict[str, Any] | None,
    *,
    min_distance_meters: int,
    min_interval_seconds: int,
    now: datetime | None = None,
) -> dict[str, Any]:
    current_time = now.astimezone(timezone.utc) if now else datetime.now(timezone.utc)
    if not isinstance(route_snapshot, dict) or not bool(route_snapshot.get("has_route")):
        return {"should_reroute": False, "reason": "no_active_route", "moved_distance_meters": None, "seconds_since_last_update": None}
    if not isinstance(location_snapshot, dict):
        return {"should_reroute": False, "reason": "missing_location", "moved_distance_meters": None, "seconds_since_last_update": None}
    if not str(route_snapshot.get("destination_query") or "").strip():
        return {"should_reroute": False, "reason": "missing_destination", "moved_distance_meters": None, "seconds_since_last_update": None}
    if not bool(location_snapshot.get("usable_for_context")):
        return {"should_reroute": False, "reason": "location_not_usable", "moved_distance_meters": None, "seconds_since_last_update": None}
    presence_status = str(location_snapshot.get("presence_status") or "unknown").strip().lower()
    if presence_status not in {"live", "recent"}:
        return {"should_reroute": False, "reason": f"presence_{presence_status}", "moved_distance_meters": None, "seconds_since_last_update": None}

    origin = _route_origin_coordinates(route_snapshot)
    if not origin:
        return {"should_reroute": False, "reason": "route_origin_missing", "moved_distance_meters": None, "seconds_since_last_update": None}

    moved_distance = distance_meters(
        origin[0],
        origin[1],
        _as_float(location_snapshot.get("latitude")),
        _as_float(location_snapshot.get("longitude")),
    )
    if moved_distance is None:
        return {"should_reroute": False, "reason": "location_coordinates_missing", "moved_distance_meters": None, "seconds_since_last_update": None}

    reference_time = (
        _parse_timestamp(route_snapshot.get("last_reroute_at"))
        or _parse_timestamp(route_snapshot.get("saved_at"))
        or _parse_timestamp(route_snapshot.get("route_started_at"))
    )
    seconds_since_last_update = (
        max(0, int((current_time - reference_time).total_seconds()))
        if reference_time
        else None
    )
    if seconds_since_last_update is not None and seconds_since_last_update < max(0, int(min_interval_seconds)):
        return {
            "should_reroute": False,
            "reason": "cooldown_active",
            "moved_distance_meters": moved_distance,
            "seconds_since_last_update": seconds_since_last_update,
        }
    if moved_distance < max(1, int(min_distance_meters)):
        return {
            "should_reroute": False,
            "reason": "movement_below_threshold",
            "moved_distance_meters": moved_distance,
            "seconds_since_last_update": seconds_since_last_update,
        }
    return {
        "should_reroute": True,
        "reason": "movement_threshold_exceeded",
        "moved_distance_meters": moved_distance,
        "seconds_since_last_update": seconds_since_last_update,
    }


def apply_live_reroute_metadata(
    new_snapshot: dict[str, Any],
    previous_snapshot: dict[str, Any] | None,
    location_snapshot: dict[str, Any] | None,
    *,
    moved_distance_meters: int | None,
    reroute_reason: str,
    rerouted_at: str,
) -> dict[str, Any]:
    safe_new = dict(new_snapshot or {})
    safe_previous = previous_snapshot if isinstance(previous_snapshot, dict) else {}
    safe_location = location_snapshot if isinstance(location_snapshot, dict) else {}
    route_started_at = str(
        safe_previous.get("route_started_at")
        or safe_previous.get("saved_at")
        or rerouted_at
    ).strip()
    safe_new["route_started_at"] = route_started_at
    safe_new["last_reroute_at"] = str(rerouted_at or "").strip()
    safe_new["reroute_count"] = max(1, _as_int(safe_previous.get("reroute_count"), 0) + 1)
    safe_new["reroute_reason"] = str(reroute_reason or "movement_threshold_exceeded").strip()
    safe_new["reroute_trigger_distance_meters"] = (
        None if moved_distance_meters is None else max(0, int(moved_distance_meters))
    )
    safe_new["reroute_trigger_captured_at"] = str(safe_location.get("captured_at") or "").strip()
    safe_new["route_status"] = "active"
    safe_new["last_reroute_error"] = ""
    return safe_new
