from __future__ import annotations

import html
import re
from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote_plus


_ROUTE_MODE_ALIASES = {
    "drive": "driving",
    "driving": "driving",
    "car": "driving",
    "auto": "driving",
    "walk": "walking",
    "walking": "walking",
    "foot": "walking",
    "fuss": "walking",
    "zu fuss": "walking",
    "bike": "bicycling",
    "bicycle": "bicycling",
    "bicycling": "bicycling",
    "fahrrad": "bicycling",
    "cycling": "bicycling",
    "transit": "transit",
    "pt": "transit",
    "oepnv": "transit",
    "öpnv": "transit",
    "public_transport": "transit",
}


def normalize_route_travel_mode(value: str) -> str:
    normalized = str(value or "").strip().lower()
    if not normalized:
        return "driving"
    return _ROUTE_MODE_ALIASES.get(normalized, "driving")


def _text_value(value: Any) -> str:
    if isinstance(value, dict):
        for key in ("text", "value", "label", "name"):
            item = value.get(key)
            if isinstance(item, str) and item.strip():
                return item.strip()
        return ""
    if isinstance(value, str):
        return value.strip()
    if value in (None, ""):
        return ""
    return str(value).strip()


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        if value in (None, ""):
            return default
        return float(value)
    except Exception:
        return default


def _as_int(value: Any, default: int = 0) -> int:
    try:
        if value in (None, ""):
            return default
        return int(value)
    except Exception:
        return default


def _extract_coordinates(value: Any) -> dict[str, float]:
    if not isinstance(value, dict):
        return {}
    latitude = _as_float(
        value.get("latitude", value.get("lat", value.get("y"))),
        default=0.0,
    )
    longitude = _as_float(
        value.get("longitude", value.get("lng", value.get("lon", value.get("x")))),
        default=0.0,
    )
    if latitude == 0.0 and longitude == 0.0:
        return {}
    return {"latitude": latitude, "longitude": longitude}


def _extract_polyline(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, dict):
        for key in ("points", "encoded_polyline", "polyline"):
            item = value.get(key)
            if isinstance(item, str) and item.strip():
                return item.strip()
    return ""


def strip_route_instruction_html(value: str) -> str:
    text = html.unescape(str(value or ""))
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def build_google_maps_directions_url(
    *,
    origin_latitude: float,
    origin_longitude: float,
    destination_query: str,
    travel_mode: str = "driving",
) -> str:
    safe_destination = quote_plus(str(destination_query or "").strip())
    safe_mode = normalize_route_travel_mode(travel_mode)
    return (
        "https://www.google.com/maps/dir/?api=1"
        f"&origin={origin_latitude},{origin_longitude}"
        f"&destination={safe_destination}"
        f"&travelmode={safe_mode}"
    )


def _normalize_route_step(raw: dict[str, Any], position: int) -> dict[str, Any]:
    instruction = strip_route_instruction_html(
        raw.get("instructions")
        or raw.get("html_instructions")
        or raw.get("instruction")
        or raw.get("narrative")
        or ""
    )
    distance_text = _text_value(raw.get("distance"))
    duration_text = _text_value(raw.get("duration"))
    maneuver = _text_value(raw.get("maneuver"))
    return {
        "position": max(1, int(position)),
        "instruction": instruction,
        "distance_text": distance_text,
        "duration_text": duration_text,
        "maneuver": maneuver,
    }


def parse_serpapi_google_maps_directions(
    data: dict[str, Any],
    *,
    origin: dict[str, Any],
    destination_query: str,
    travel_mode: str,
) -> dict[str, Any]:
    safe_data = data if isinstance(data, dict) else {}
    routes = safe_data.get("directions") or safe_data.get("routes") or []
    route = routes[0] if isinstance(routes, list) and routes else {}
    if not isinstance(route, dict):
        route = {}

    legs = route.get("legs") or []
    leg = legs[0] if isinstance(legs, list) and legs else {}
    if not isinstance(leg, dict):
        leg = {}

    steps_raw = leg.get("steps") or route.get("steps") or []
    if not isinstance(steps_raw, list):
        steps_raw = []
    steps = [
        _normalize_route_step(item, idx)
        for idx, item in enumerate(steps_raw, start=1)
        if isinstance(item, dict)
    ]

    normalized_mode = normalize_route_travel_mode(travel_mode)
    origin_latitude = _as_float(origin.get("latitude"))
    origin_longitude = _as_float(origin.get("longitude"))
    start_coordinates = (
        _extract_coordinates(leg.get("start_location"))
        or _extract_coordinates(route.get("start_location"))
        or (
            {"latitude": origin_latitude, "longitude": origin_longitude}
            if origin_latitude or origin_longitude
            else {}
        )
    )
    end_coordinates = (
        _extract_coordinates(leg.get("end_location"))
        or _extract_coordinates(route.get("end_location"))
        or _extract_coordinates(route.get("destination"))
    )
    overview_polyline = (
        _extract_polyline(route.get("overview_polyline"))
        or _extract_polyline(route.get("polyline"))
        or _extract_polyline(route.get("route_overview_polyline"))
        or _extract_polyline(safe_data.get("overview_polyline"))
    )
    route_url = build_google_maps_directions_url(
        origin_latitude=origin_latitude,
        origin_longitude=origin_longitude,
        destination_query=destination_query,
        travel_mode=normalized_mode,
    )

    distance_text = (
        _text_value(leg.get("distance"))
        or _text_value(route.get("distance"))
        or _text_value(safe_data.get("distance"))
    )
    duration_text = (
        _text_value(leg.get("duration"))
        or _text_value(route.get("duration"))
        or _text_value(safe_data.get("duration"))
    )
    start_address = (
        _text_value(leg.get("start_address"))
        or _text_value(route.get("start_address"))
        or str(origin.get("display_name") or "").strip()
    )
    end_address = (
        _text_value(leg.get("end_address"))
        or _text_value(route.get("end_address"))
        or str(destination_query or "").strip()
    )
    summary = (
        _text_value(route.get("summary"))
        or _text_value(route.get("title"))
        or _text_value(route.get("route_summary"))
        or destination_query
    )

    return {
        "origin": origin,
        "destination_query": str(destination_query or "").strip(),
        "destination_label": end_address,
        "travel_mode": normalized_mode,
        "summary": summary,
        "distance_text": distance_text,
        "duration_text": duration_text,
        "start_address": start_address,
        "end_address": end_address,
        "steps": steps[:12],
        "step_count": len(steps),
        "start_coordinates": start_coordinates,
        "end_coordinates": end_coordinates,
        "overview_polyline": overview_polyline,
        "route_url": route_url,
        "maps_url": route_url,
        "source_provider": "serpapi",
        "engine": "google_maps_directions",
    }


def prepare_route_snapshot(payload: dict[str, Any], *, saved_at: str | None = None) -> dict[str, Any]:
    safe = dict(payload or {})
    route_url = str(safe.get("route_url") or safe.get("maps_url") or "").strip()
    destination_query = str(safe.get("destination_query") or "").strip()
    normalized_mode = normalize_route_travel_mode(str(safe.get("travel_mode") or "driving"))
    effective_saved_at = str(
        saved_at or datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    )
    normalized_steps = []
    raw_steps = safe.get("steps") or []
    if isinstance(raw_steps, list):
        for idx, item in enumerate(raw_steps, start=1):
            if isinstance(item, dict):
                normalized_steps.append(_normalize_route_step(item, idx))

    return {
        "has_route": bool(route_url and destination_query),
        "destination_query": destination_query,
        "destination_label": str(safe.get("destination_label") or destination_query).strip(),
        "travel_mode": normalized_mode,
        "language_code": str(safe.get("language_code") or "de").strip() or "de",
        "summary": str(safe.get("summary") or destination_query).strip(),
        "distance_text": str(safe.get("distance_text") or "").strip(),
        "duration_text": str(safe.get("duration_text") or "").strip(),
        "start_address": str(safe.get("start_address") or "").strip(),
        "end_address": str(safe.get("end_address") or "").strip(),
        "steps": normalized_steps[:12],
        "step_count": len(normalized_steps),
        "origin": safe.get("origin") if isinstance(safe.get("origin"), dict) else {},
        "start_coordinates": safe.get("start_coordinates") if isinstance(safe.get("start_coordinates"), dict) else {},
        "end_coordinates": safe.get("end_coordinates") if isinstance(safe.get("end_coordinates"), dict) else {},
        "overview_polyline": str(safe.get("overview_polyline") or "").strip(),
        "route_url": route_url,
        "maps_url": route_url,
        "saved_at": effective_saved_at,
        "route_started_at": str(safe.get("route_started_at") or effective_saved_at),
        "last_reroute_at": str(safe.get("last_reroute_at") or "").strip(),
        "reroute_count": max(0, _as_int(safe.get("reroute_count"), 0)),
        "reroute_reason": str(safe.get("reroute_reason") or "").strip(),
        "reroute_trigger_distance_meters": (
            None
            if safe.get("reroute_trigger_distance_meters") in (None, "")
            else max(0, _as_int(safe.get("reroute_trigger_distance_meters"), 0))
        ),
        "reroute_trigger_captured_at": str(safe.get("reroute_trigger_captured_at") or "").strip(),
        "route_status": str(safe.get("route_status") or "active").strip() or "active",
        "last_reroute_error": str(safe.get("last_reroute_error") or "").strip(),
        "source_provider": str(safe.get("source_provider") or "serpapi").strip(),
        "engine": str(safe.get("engine") or "google_maps_directions").strip(),
    }
