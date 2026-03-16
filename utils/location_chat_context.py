from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


_LOCATION_CONTEXT_QUERY_PATTERNS = (
    r"\bwo bin ich\b",
    r"\bwo ist mein standort\b",
    r"\bstandort\b",
    r"\bin meiner nähe\b",
    r"\bin meiner naehe\b",
    r"\bin der nähe\b",
    r"\bin der naehe\b",
    r"\bnear me\b",
    r"\bnearby\b",
    r"\bclose by\b",
    r"\bum mich herum\b",
    r"\bwie komme ich\b",
    r"\broute\b",
    r"\brouting\b",
    r"\bnavigation\b",
    r"\bnavigier\b",
    r"\bführe mich\b",
    r"\bfuehre mich\b",
    r"\bweg zu\b",
    r"\bmaps\b",
)


def normalize_location_presence_status(value: str) -> str:
    normalized = str(value or "").strip().lower()
    if normalized in {"live", "recent", "stale", "unknown"}:
        return normalized
    return "unknown"


def is_location_context_query(query: str) -> bool:
    normalized = str(query or "").strip().lower()
    if not normalized:
        return False
    if len(normalized.split()) > 40:
        return False
    return any(re.search(pattern, normalized) for pattern in _LOCATION_CONTEXT_QUERY_PATTERNS)


@dataclass(frozen=True)
class LocationChatContextDecision:
    should_inject: bool
    reason: str
    presence_status: str
    usable_for_context: bool


def evaluate_location_chat_context(
    *,
    query: str,
    snapshot: dict[str, Any] | None,
    enabled: bool = True,
) -> LocationChatContextDecision:
    if not enabled:
        return LocationChatContextDecision(
            should_inject=False,
            reason="feature_disabled",
            presence_status="unknown",
            usable_for_context=False,
        )
    if not is_location_context_query(query):
        return LocationChatContextDecision(
            should_inject=False,
            reason="query_not_location_relevant",
            presence_status="unknown",
            usable_for_context=False,
        )
    if not isinstance(snapshot, dict) or not snapshot:
        return LocationChatContextDecision(
            should_inject=False,
            reason="missing_location_snapshot",
            presence_status="unknown",
            usable_for_context=False,
        )

    presence_status = normalize_location_presence_status(str(snapshot.get("presence_status") or "unknown"))
    usable_for_context = bool(snapshot.get("usable_for_context"))
    has_coordinates = bool(snapshot.get("has_coordinates", True))

    if presence_status not in {"live", "recent"}:
        return LocationChatContextDecision(
            should_inject=False,
            reason=f"presence_{presence_status}",
            presence_status=presence_status,
            usable_for_context=usable_for_context,
        )
    if not usable_for_context:
        return LocationChatContextDecision(
            should_inject=False,
            reason="location_not_usable_for_context",
            presence_status=presence_status,
            usable_for_context=False,
        )
    if not has_coordinates:
        return LocationChatContextDecision(
            should_inject=False,
            reason="missing_coordinates",
            presence_status=presence_status,
            usable_for_context=False,
        )
    return LocationChatContextDecision(
        should_inject=True,
        reason="fresh_location_context",
        presence_status=presence_status,
        usable_for_context=True,
    )


def build_location_chat_context_block(snapshot: dict[str, Any]) -> str:
    safe = dict(snapshot or {})
    parts = ["# LIVE LOCATION CONTEXT"]
    parts.append(f"presence_status: {normalize_location_presence_status(safe.get('presence_status') or 'unknown')}")
    if safe.get("display_name"):
        parts.append(f"display_name: {str(safe.get('display_name'))[:220]}")
    if safe.get("locality"):
        parts.append(f"locality: {str(safe.get('locality'))[:120]}")
    if safe.get("admin_area"):
        parts.append(f"admin_area: {str(safe.get('admin_area'))[:120]}")
    if safe.get("country_name"):
        parts.append(f"country_name: {str(safe.get('country_name'))[:120]}")
    if safe.get("accuracy_meters") not in (None, ""):
        parts.append(f"accuracy_meters: {safe.get('accuracy_meters')}")
    if safe.get("captured_at"):
        parts.append(f"captured_at: {str(safe.get('captured_at'))[:64]}")
    if safe.get("received_at"):
        parts.append(f"received_at: {str(safe.get('received_at'))[:64]}")
    if safe.get("maps_url"):
        parts.append(f"maps_url: {str(safe.get('maps_url'))[:260]}")
    parts.append("Use this location only for nearby, routing, navigation, or explicit place-context tasks.")
    return "\n".join(parts)
