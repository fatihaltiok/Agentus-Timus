from __future__ import annotations

from utils.location_map_mode import (
    normalize_route_map_mode,
    resolve_route_map_mode,
    route_map_interactive_available,
)


def test_normalize_route_map_mode_defaults_unknown_to_static() -> None:
    assert normalize_route_map_mode("weird") == "static"
    assert normalize_route_map_mode("") == "static"


def test_normalize_route_map_mode_accepts_interactive() -> None:
    assert normalize_route_map_mode("interactive") == "interactive"


def test_route_map_interactive_available_requires_key_and_feature() -> None:
    assert route_map_interactive_available("browser-key", enabled=True) is True
    assert route_map_interactive_available("", enabled=True) is False
    assert route_map_interactive_available("browser-key", enabled=False) is False


def test_resolve_route_map_mode_falls_back_to_static_when_interactive_unavailable() -> None:
    assert resolve_route_map_mode("interactive", interactive_available=False) == "static"
    assert resolve_route_map_mode("interactive", interactive_available=True) == "interactive"
