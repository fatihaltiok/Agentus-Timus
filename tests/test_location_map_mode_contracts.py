from __future__ import annotations

import deal

from utils.location_map_mode import (
    normalize_route_map_mode,
    resolve_route_map_mode,
    route_map_interactive_available,
)


@deal.post(lambda r: r in {"static", "interactive"})
def _contract_normalize_route_map_mode(value: str) -> str:
    return normalize_route_map_mode(value)


@deal.post(lambda r: isinstance(r, bool))
@deal.ensure(lambda browser_api_key, enabled, result: (not result) or (enabled and bool(str(browser_api_key or "").strip())))
def _contract_route_map_interactive_available(browser_api_key: str, enabled: bool) -> bool:
    return route_map_interactive_available(browser_api_key, enabled=enabled)


@deal.post(lambda r: r in {"static", "interactive"})
@deal.ensure(lambda preferred_mode, interactive_available, result: (result != "interactive") or interactive_available)
def _contract_resolve_route_map_mode(preferred_mode: str, interactive_available: bool) -> str:
    return resolve_route_map_mode(preferred_mode, interactive_available=interactive_available)


def test_contract_resolve_route_map_mode_degrades_without_browser_key() -> None:
    assert _contract_resolve_route_map_mode("interactive", False) == "static"
