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
        for key in ("points", "encoded_polyline", "encodedPolyline", "polyline"):
            item = value.get(key)
            if isinstance(item, str) and item.strip():
                return item.strip()
    return ""


def _extract_place_info_coordinates(value: Any) -> dict[str, float]:
    if not isinstance(value, dict):
        return {}
    gps = value.get("gps_coordinates")
    if isinstance(gps, dict):
        coords = _extract_coordinates(gps)
        if coords:
            return coords
    return _extract_coordinates(value)


def _extract_google_latlng(value: Any) -> dict[str, float]:
    if not isinstance(value, dict):
        return {}
    latlng = value.get("latLng")
    if isinstance(latlng, dict):
        return _extract_coordinates(latlng)
    return _extract_coordinates(value)


def _append_path_coordinate(path_coordinates: list[dict[str, float]], value: Any) -> None:
    coords = _extract_coordinates(value)
    if not coords:
        return
    if path_coordinates:
        previous = path_coordinates[-1]
        if (
            abs(previous["latitude"] - coords["latitude"]) < 1e-7
            and abs(previous["longitude"] - coords["longitude"]) < 1e-7
        ):
            return
    path_coordinates.append(coords)


def _normalize_path_coordinates(value: Any) -> list[dict[str, float]]:
    normalized: list[dict[str, float]] = []
    if not isinstance(value, list):
        return normalized
    for item in value:
        _append_path_coordinate(normalized, item)
    return normalized


def route_step_segment_available(
    start_coordinates: dict[str, Any] | None,
    end_coordinates: dict[str, Any] | None,
) -> bool:
    return bool(
        _extract_coordinates(start_coordinates or {})
        and _extract_coordinates(end_coordinates or {})
    )


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
        or raw.get("title")
        or ""
    )
    distance_text = _text_value(raw.get("formatted_distance")) or _text_value(raw.get("distance"))
    duration_text = _text_value(raw.get("formatted_duration")) or _text_value(raw.get("duration"))
    maneuver = _text_value(raw.get("maneuver"))
    start_coordinates = (
        _extract_coordinates(raw.get("start_coordinates"))
        or _extract_coordinates(raw.get("start_location"))
        or _extract_google_latlng(raw.get("startLocation"))
    )
    end_coordinates = (
        _extract_coordinates(raw.get("end_coordinates"))
        or _extract_coordinates(raw.get("end_location"))
        or _extract_google_latlng(raw.get("endLocation"))
        or _extract_coordinates(raw.get("gps_coordinates"))
    )
    return {
        "position": max(1, int(position)),
        "instruction": instruction,
        "distance_text": distance_text,
        "duration_text": duration_text,
        "maneuver": maneuver,
        "start_coordinates": start_coordinates,
        "end_coordinates": end_coordinates,
        "highlight_available": route_step_segment_available(start_coordinates, end_coordinates),
    }


def _duration_seconds(value: Any) -> int:
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized.endswith("s"):
            try:
                return max(0, int(round(float(normalized[:-1]))))
            except Exception:
                return _as_int(value, 0)
    return _as_int(value, 0)


def _format_distance_text(value: Any) -> str:
    meters = _as_int(value, 0)
    if meters <= 0:
        return ""
    if meters < 1000:
        return f"{meters} m"
    kilometers = meters / 1000.0
    text = f"{kilometers:.1f}".replace(".", ",")
    return f"{text} km"


def _format_duration_text(value: Any) -> str:
    seconds = _duration_seconds(value)
    if seconds <= 0:
        return ""
    if seconds < 60:
        return f"{seconds} Sek."
    minutes = max(1, round(seconds / 60))
    if minutes < 60:
        return f"{minutes} min"
    hours = minutes // 60
    remainder_minutes = minutes % 60
    if remainder_minutes == 0:
        return f"{hours} h"
    return f"{hours} h {remainder_minutes} min"


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

    trips = route.get("trips") or []
    primary_trip = trips[0] if isinstance(trips, list) and trips else {}
    if not isinstance(primary_trip, dict):
        primary_trip = {}
    trip_details = primary_trip.get("details") or []
    if not isinstance(trip_details, list):
        trip_details = []

    places_info = safe_data.get("places_info") or []
    if not isinstance(places_info, list):
        places_info = []
    origin_place = places_info[0] if len(places_info) >= 1 and isinstance(places_info[0], dict) else {}
    destination_place = places_info[1] if len(places_info) >= 2 and isinstance(places_info[1], dict) else {}

    legs = route.get("legs") or []
    leg = legs[0] if isinstance(legs, list) and legs else {}
    if not isinstance(leg, dict):
        leg = {}

    all_trip_details: list[dict[str, Any]] = []
    for trip in trips:
        if not isinstance(trip, dict):
            continue
        details = trip.get("details") or []
        if not isinstance(details, list):
            continue
        all_trip_details.extend(item for item in details if isinstance(item, dict))

    steps_raw = leg.get("steps") or route.get("steps")
    if not isinstance(steps_raw, list):
        steps_raw = []
    use_trip_details = not steps_raw and bool(all_trip_details)
    if use_trip_details:
        steps_raw = all_trip_details

    normalized_mode = normalize_route_travel_mode(travel_mode)
    origin_latitude = _as_float(origin.get("latitude"))
    origin_longitude = _as_float(origin.get("longitude"))
    start_coordinates = (
        _extract_coordinates(leg.get("start_location"))
        or _extract_coordinates(route.get("start_location"))
        or _extract_place_info_coordinates(origin_place)
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
        or _extract_place_info_coordinates(destination_place)
    )
    path_coordinates: list[dict[str, float]] = []
    _append_path_coordinate(path_coordinates, start_coordinates)

    steps: list[dict[str, Any]] = []
    if use_trip_details:
        previous_coordinates = start_coordinates
        for idx, item in enumerate(steps_raw, start=1):
            if not isinstance(item, dict):
                continue
            detail_coordinates = _extract_coordinates(item.get("gps_coordinates"))
            step = _normalize_route_step(
                {
                    "title": item.get("title"),
                    "instruction": item.get("instruction"),
                    "maneuver": item.get("action"),
                    "distance": item.get("formatted_distance") or item.get("distance"),
                    "duration": item.get("formatted_duration") or item.get("duration"),
                    "start_coordinates": previous_coordinates,
                    "end_coordinates": detail_coordinates,
                },
                idx,
            )
            steps.append(step)
            if detail_coordinates:
                _append_path_coordinate(path_coordinates, detail_coordinates)
                previous_coordinates = detail_coordinates
    else:
        for idx, item in enumerate(steps_raw, start=1):
            if not isinstance(item, dict):
                continue
            step = _normalize_route_step(item, idx)
            steps.append(step)
            _append_path_coordinate(path_coordinates, step.get("start_coordinates"))
            _append_path_coordinate(path_coordinates, step.get("end_coordinates"))
    _append_path_coordinate(path_coordinates, end_coordinates)

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
        _text_value(leg.get("formatted_distance"))
        or _text_value(route.get("formatted_distance"))
        or _text_value(primary_trip.get("formatted_distance"))
        or
        _text_value(leg.get("distance"))
        or _text_value(route.get("distance"))
        or _text_value(primary_trip.get("distance"))
        or _text_value(safe_data.get("distance"))
    )
    duration_text = (
        _text_value(leg.get("formatted_duration"))
        or _text_value(route.get("formatted_duration"))
        or _text_value(primary_trip.get("formatted_duration"))
        or
        _text_value(leg.get("duration"))
        or _text_value(route.get("duration"))
        or _text_value(primary_trip.get("duration"))
        or _text_value(safe_data.get("duration"))
    )
    start_address = (
        _text_value(leg.get("start_address"))
        or _text_value(route.get("start_address"))
        or _text_value(origin_place.get("address"))
        or str(origin.get("display_name") or "").strip()
    )
    end_address = (
        _text_value(leg.get("end_address"))
        or _text_value(route.get("end_address"))
        or _text_value(destination_place.get("address"))
        or str(destination_query or "").strip()
    )
    summary = (
        _text_value(route.get("summary"))
        or _text_value(primary_trip.get("title"))
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
        "path_coordinates": path_coordinates,
        "overview_polyline": overview_polyline,
        "route_url": route_url,
        "maps_url": route_url,
        "source_provider": "serpapi",
        "engine": "google_maps_directions",
    }


def parse_google_routes_compute_route(
    data: dict[str, Any],
    *,
    origin: dict[str, Any],
    destination_query: str,
    travel_mode: str,
) -> dict[str, Any]:
    safe_data = data if isinstance(data, dict) else {}
    routes = safe_data.get("routes") or []
    route = routes[0] if isinstance(routes, list) and routes else {}
    if not isinstance(route, dict):
        route = {}

    legs = route.get("legs") or []
    leg = legs[0] if isinstance(legs, list) and legs else {}
    if not isinstance(leg, dict):
        leg = {}

    steps_raw = leg.get("steps") or []
    if not isinstance(steps_raw, list):
        steps_raw = []
    steps = []
    for idx, item in enumerate(steps_raw, start=1):
        if not isinstance(item, dict):
            continue
        steps.append(
            _normalize_route_step(
                {
                    "position": idx,
                    "instruction": strip_route_instruction_html(
                        _text_value((item.get("navigationInstruction") or {}).get("instructions"))
                        or _text_value(item.get("instruction"))
                    ),
                    "distance_text": _format_distance_text(item.get("distanceMeters")),
                    "duration_text": _format_duration_text(item.get("staticDuration") or item.get("duration")),
                    "maneuver": _text_value(item.get("maneuver") or item.get("travelMode")),
                    "startLocation": item.get("startLocation"),
                    "endLocation": item.get("endLocation"),
                },
                idx,
            )
        )

    origin_latitude = _as_float(origin.get("latitude"))
    origin_longitude = _as_float(origin.get("longitude"))
    start_coordinates = (
        _extract_google_latlng(leg.get("startLocation"))
        or _extract_google_latlng(route.get("startLocation"))
        or (
            {"latitude": origin_latitude, "longitude": origin_longitude}
            if origin_latitude or origin_longitude
            else {}
        )
    )
    end_coordinates = (
        _extract_google_latlng(leg.get("endLocation"))
        or _extract_google_latlng(route.get("endLocation"))
        or (_extract_google_latlng(steps_raw[-1].get("endLocation")) if steps_raw and isinstance(steps_raw[-1], dict) else {})
    )
    path_coordinates: list[dict[str, float]] = []
    _append_path_coordinate(path_coordinates, start_coordinates)
    for step in steps:
        _append_path_coordinate(path_coordinates, step.get("start_coordinates"))
        _append_path_coordinate(path_coordinates, step.get("end_coordinates"))
    _append_path_coordinate(path_coordinates, end_coordinates)
    overview_polyline = _extract_polyline(route.get("polyline"))
    route_url = build_google_maps_directions_url(
        origin_latitude=origin_latitude,
        origin_longitude=origin_longitude,
        destination_query=destination_query,
        travel_mode=travel_mode,
    )

    distance_text = (
        _format_distance_text(leg.get("distanceMeters"))
        or _format_distance_text(route.get("distanceMeters"))
    )
    duration_text = (
        _format_duration_text(leg.get("duration"))
        or _format_duration_text(route.get("duration"))
    )
    start_address = str(origin.get("display_name") or "").strip()
    end_address = str(destination_query or "").strip()
    summary = (
        _text_value(route.get("description"))
        or _text_value(route.get("routeLabels"))
        or destination_query
    )

    return {
        "origin": origin,
        "destination_query": str(destination_query or "").strip(),
        "destination_label": end_address,
        "travel_mode": normalize_route_travel_mode(travel_mode),
        "summary": summary,
        "distance_text": distance_text,
        "duration_text": duration_text,
        "start_address": start_address,
        "end_address": end_address,
        "steps": steps[:12],
        "step_count": len(steps),
        "start_coordinates": start_coordinates,
        "end_coordinates": end_coordinates,
        "path_coordinates": path_coordinates,
        "overview_polyline": overview_polyline,
        "route_url": route_url,
        "maps_url": route_url,
        "source_provider": "google_routes",
        "engine": "google_routes_computeRoutes",
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
        "path_coordinates": _normalize_path_coordinates(safe.get("path_coordinates")),
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
