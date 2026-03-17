from __future__ import annotations


VALID_ROUTE_MAP_MODES = {"static", "interactive"}


def normalize_route_map_mode(value: str | None) -> str:
    normalized = str(value or "").strip().lower()
    if normalized in VALID_ROUTE_MAP_MODES:
        return normalized
    return "static"


def route_map_interactive_available(browser_api_key: str | None, *, enabled: bool = True) -> bool:
    return bool(enabled and str(browser_api_key or "").strip())


def resolve_route_map_mode(preferred_mode: str | None, *, interactive_available: bool) -> str:
    normalized = normalize_route_map_mode(preferred_mode)
    if normalized == "interactive" and not interactive_available:
        return "static"
    return normalized
