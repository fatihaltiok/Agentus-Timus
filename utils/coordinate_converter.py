"""Shared coordinate conversion helpers for vision/browser pipelines."""

from __future__ import annotations

from typing import Any, Mapping, Optional, Sequence, Tuple


_COORDINATE_KEY_PAIRS: Sequence[Tuple[str, str]] = (
    ("click_x", "click_y"),
    ("x", "y"),
    ("center_x", "center_y"),
)


def sanitize_scale(value: Any, default: float = 1.0) -> float:
    """Returns a positive scale factor, falls back to default otherwise."""
    try:
        scale = float(value)
    except (TypeError, ValueError):
        return float(default)
    if scale <= 0:
        return float(default)
    return scale


def clamp(value: float, minimum: float, maximum: float) -> float:
    """Clamps a numeric value to [minimum, maximum]."""
    return max(minimum, min(value, maximum))


def normalize_point(
    pixel_x: float,
    pixel_y: float,
    reference_width: int,
    reference_height: int,
) -> Tuple[float, float]:
    """Converts pixel coordinates to normalized [0, 1] coordinates."""
    if reference_width <= 0 or reference_height <= 0:
        raise ValueError("reference_width and reference_height must be > 0")

    x = clamp(float(pixel_x) / float(reference_width), 0.0, 1.0)
    y = clamp(float(pixel_y) / float(reference_height), 0.0, 1.0)
    return x, y


def denormalize_point(
    normalized_x: float,
    normalized_y: float,
    reference_width: int,
    reference_height: int,
) -> Tuple[int, int]:
    """Converts normalized [0, 1] coordinates to pixel coordinates."""
    if reference_width <= 0 or reference_height <= 0:
        raise ValueError("reference_width and reference_height must be > 0")

    x = int(round(clamp(float(normalized_x), 0.0, 1.0) * reference_width))
    y = int(round(clamp(float(normalized_y), 0.0, 1.0) * reference_height))
    return min(x, reference_width - 1), min(y, reference_height - 1)


def to_click_point(
    relative_pixel_x: float,
    relative_pixel_y: float,
    monitor_offset_x: int = 0,
    monitor_offset_y: int = 0,
    dpi_scale: float = 1.0,
) -> Tuple[int, int]:
    """Maps screenshot pixels to global logical click coordinates."""
    scale = sanitize_scale(dpi_scale, default=1.0)
    absolute_x = (float(relative_pixel_x) + float(monitor_offset_x)) / scale
    absolute_y = (float(relative_pixel_y) + float(monitor_offset_y)) / scale
    return int(round(absolute_x)), int(round(absolute_y))


def from_click_point(
    click_x: float,
    click_y: float,
    monitor_offset_x: int = 0,
    monitor_offset_y: int = 0,
    dpi_scale: float = 1.0,
) -> Tuple[int, int]:
    """Maps global logical click coordinates back to screenshot pixels."""
    scale = sanitize_scale(dpi_scale, default=1.0)
    relative_x = (float(click_x) * scale) - float(monitor_offset_x)
    relative_y = (float(click_y) * scale) - float(monitor_offset_y)
    return int(round(relative_x)), int(round(relative_y))


def _to_number(value: Any) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def extract_coordinate_pair(
    payload: Optional[Mapping[str, Any]],
    key_pairs: Sequence[Tuple[str, str]] = _COORDINATE_KEY_PAIRS,
) -> Optional[Tuple[float, float]]:
    """Extracts coordinates from common key pairs."""
    if payload is None:
        return None
    for x_key, y_key in key_pairs:
        x_value = _to_number(payload.get(x_key))
        y_value = _to_number(payload.get(y_key))
        if x_value is not None and y_value is not None:
            return x_value, y_value
    return None


def resolve_click_coordinates(
    payload: Optional[Mapping[str, Any]],
    monitor_offset_x: int = 0,
    monitor_offset_y: int = 0,
    dpi_scale: float = 1.0,
    already_absolute: bool = True,
) -> Optional[Tuple[int, int]]:
    """
    Resolves click coordinates from a tool payload.

    If already_absolute=True, the extracted coordinates are interpreted as global
    click coordinates. Otherwise they are treated as screenshot-relative pixels.
    """
    point = extract_coordinate_pair(payload)
    if point is None:
        return None

    x, y = point
    if already_absolute:
        return int(round(x)), int(round(y))
    return to_click_point(
        relative_pixel_x=x,
        relative_pixel_y=y,
        monitor_offset_x=monitor_offset_x,
        monitor_offset_y=monitor_offset_y,
        dpi_scale=dpi_scale,
    )
