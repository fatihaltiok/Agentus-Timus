from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from utils.coordinate_converter import (
    denormalize_point,
    extract_coordinate_pair,
    from_click_point,
    normalize_point,
    resolve_click_coordinates,
    to_click_point,
)


def test_normalize_and_denormalize_roundtrip():
    nx, ny = normalize_point(1280, 720, reference_width=2560, reference_height=1440)
    assert nx == 0.5
    assert ny == 0.5

    px, py = denormalize_point(nx, ny, reference_width=2560, reference_height=1440)
    assert px == 1280
    assert py == 720


def test_click_point_conversion_respects_dpi_and_monitor_offset():
    click_x, click_y = to_click_point(
        relative_pixel_x=400,
        relative_pixel_y=200,
        monitor_offset_x=100,
        monitor_offset_y=50,
        dpi_scale=2.0,
    )
    assert click_x == 250
    assert click_y == 125

    rel_x, rel_y = from_click_point(
        click_x=click_x,
        click_y=click_y,
        monitor_offset_x=100,
        monitor_offset_y=50,
        dpi_scale=2.0,
    )
    assert rel_x == 400
    assert rel_y == 200


def test_extract_and_resolve_coordinates_support_common_key_contracts():
    payload = {"x": 10, "y": 20}
    assert extract_coordinate_pair(payload) == (10.0, 20.0)
    assert resolve_click_coordinates(payload) == (10, 20)

    payload_click = {"click_x": 42, "click_y": 84}
    assert resolve_click_coordinates(payload_click) == (42, 84)

    payload_center = {"center_x": 7, "center_y": 9}
    assert resolve_click_coordinates(payload_center) == (7, 9)
