from __future__ import annotations

from hypothesis import given, strategies as st

from utils.location_map_mode import (
    normalize_route_map_mode,
    resolve_route_map_mode,
    route_map_interactive_available,
)


@given(st.text())
def test_hypothesis_normalize_route_map_mode_stays_in_allowed_set(value: str) -> None:
    assert normalize_route_map_mode(value) in {"static", "interactive"}


@given(st.text(), st.booleans())
def test_hypothesis_resolve_route_map_mode_never_returns_interactive_without_availability(
    preferred_mode: str,
    interactive_available: bool,
) -> None:
    result = resolve_route_map_mode(preferred_mode, interactive_available=interactive_available)
    assert result in {"static", "interactive"}
    if result == "interactive":
        assert interactive_available is True


@given(st.text(), st.booleans())
def test_hypothesis_route_map_interactive_available_requires_nonempty_key(browser_api_key: str, enabled: bool) -> None:
    result = route_map_interactive_available(browser_api_key, enabled=enabled)
    if result:
        assert enabled is True
        assert browser_api_key.strip() != ""
