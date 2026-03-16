from __future__ import annotations

from hypothesis import given, strategies as st

from utils.location_registry import normalize_location_controls, sync_mode_allowed


@given(st.booleans(), st.booleans(), st.text(min_size=0, max_size=20))
def test_normalize_location_controls_produces_nonempty_scope(_sharing: bool, _context: bool, preferred_device_id: str) -> None:
    controls = normalize_location_controls(
        {
            "sharing_enabled": _sharing,
            "context_enabled": _context,
            "preferred_device_id": preferred_device_id,
        }
    )
    assert controls["allowed_user_scopes"]


@given(st.booleans())
def test_sync_mode_allowed_never_blocks_foreground(background_allowed: bool) -> None:
    assert sync_mode_allowed("foreground", {"background_sync_allowed": background_allowed}) is True
