from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any


_LIVE_MAX_AGE_SECONDS = "TIMUS_LOCATION_LIVE_MAX_AGE_SECONDS"
_RECENT_MAX_AGE_SECONDS = "TIMUS_LOCATION_RECENT_MAX_AGE_SECONDS"
_MAX_CONTEXT_ACCURACY_METERS = "TIMUS_LOCATION_MAX_CONTEXT_ACCURACY_METERS"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _isoformat_utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


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


def _safe_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except Exception:
        return None


def _safe_int(value: Any, default: int) -> int:
    if value in (None, ""):
        return default
    try:
        return max(0, int(float(value)))
    except Exception:
        return default


def _presence_config() -> dict[str, float | int]:
    live_max = _safe_int(os.getenv(_LIVE_MAX_AGE_SECONDS, "600"), 600)
    recent_max = max(live_max, _safe_int(os.getenv(_RECENT_MAX_AGE_SECONDS, "3600"), 3600))
    max_accuracy = _safe_float(os.getenv(_MAX_CONTEXT_ACCURACY_METERS, "250"))
    return {
        "live_max_age_seconds": live_max,
        "recent_max_age_seconds": recent_max,
        "max_context_accuracy_meters": max_accuracy if max_accuracy is not None else 250.0,
    }


def classify_location_freshness(
    *,
    effective_age_seconds: int | None,
    accuracy_meters: float | None,
    live_max_age_seconds: int | None = None,
    recent_max_age_seconds: int | None = None,
    max_context_accuracy_meters: float | None = None,
) -> dict[str, Any]:
    config = _presence_config()
    live_max = config["live_max_age_seconds"] if live_max_age_seconds is None else max(0, int(live_max_age_seconds))
    recent_max = config["recent_max_age_seconds"] if recent_max_age_seconds is None else max(live_max, int(recent_max_age_seconds))
    max_accuracy = config["max_context_accuracy_meters"] if max_context_accuracy_meters is None else max_context_accuracy_meters
    age = None if effective_age_seconds is None else max(0, int(effective_age_seconds))
    accuracy = None if accuracy_meters is None else float(accuracy_meters)

    if age is None:
        status = "unknown"
    elif age <= live_max:
        status = "live"
    elif age <= recent_max:
        status = "recent"
    else:
        status = "stale"

    accuracy_ok = accuracy is None or max_accuracy is None or max_accuracy <= 0 or accuracy <= float(max_accuracy)
    usable_for_context = status in {"live", "recent"} and accuracy_ok

    if status == "unknown":
        reason = "missing_age"
    elif status == "stale":
        reason = "stale_age"
    elif not accuracy_ok:
        reason = "poor_accuracy"
    else:
        reason = status

    return {
        "presence_status": status,
        "presence_reason": reason,
        "usable_for_context": usable_for_context,
        "accuracy_ok": accuracy_ok,
        "effective_age_seconds": age,
        "live_max_age_seconds": live_max,
        "recent_max_age_seconds": recent_max,
        "max_context_accuracy_meters": max_accuracy,
    }


def prepare_location_presence_snapshot(
    snapshot: dict[str, Any],
    *,
    received_at: str = "",
    default_device_id: str = "primary_mobile",
    default_user_scope: str = "primary",
) -> dict[str, Any]:
    normalized = dict(snapshot or {})
    received = _parse_timestamp(received_at or normalized.get("received_at")) or _utc_now()
    normalized["received_at"] = _isoformat_utc(received)
    normalized["device_id"] = str(normalized.get("device_id") or default_device_id).strip() or default_device_id
    normalized["user_scope"] = str(normalized.get("user_scope") or default_user_scope).strip() or default_user_scope
    return normalized


def enrich_location_presence_snapshot(snapshot: dict[str, Any] | None) -> dict[str, Any] | None:
    if not snapshot:
        return None

    enriched = dict(snapshot)
    enriched["device_id"] = str(enriched.get("device_id") or "primary_mobile").strip() or "primary_mobile"
    enriched["user_scope"] = str(enriched.get("user_scope") or "primary").strip() or "primary"
    enriched["received_at"] = str(enriched.get("received_at") or "").strip()
    latitude = _safe_float(enriched.get("latitude"))
    longitude = _safe_float(enriched.get("longitude"))
    accuracy = _safe_float(enriched.get("accuracy_meters"))
    captured_dt = _parse_timestamp(enriched.get("captured_at"))
    received_dt = _parse_timestamp(enriched.get("received_at"))
    now = _utc_now()

    captured_age = None if captured_dt is None else max(0, int((now - captured_dt).total_seconds()))
    received_age = None if received_dt is None else max(0, int((now - received_dt).total_seconds()))
    effective_age = captured_age if captured_age is not None else received_age
    effective_source = "captured_at" if captured_age is not None else ("received_at" if received_age is not None else "")

    freshness = classify_location_freshness(
        effective_age_seconds=effective_age,
        accuracy_meters=accuracy,
    )

    if latitude is None or longitude is None:
        freshness["presence_status"] = "unknown"
        freshness["presence_reason"] = "missing_coordinates"
        freshness["usable_for_context"] = False

    enriched.update(freshness)
    enriched["captured_age_seconds"] = captured_age
    enriched["received_age_seconds"] = received_age
    enriched["effective_timestamp_source"] = effective_source
    enriched["has_coordinates"] = latitude is not None and longitude is not None
    return enriched
