from pathlib import Path
import sys

import cv2
import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools.opencv_template_matcher_tool import tool as matcher_tool


def _create_pattern(size: int) -> np.ndarray:
    img = np.full((size, size, 3), 255, dtype=np.uint8)
    cv2.rectangle(img, (2, 2), (size - 3, size - 3), (0, 0, 0), 2)
    cv2.line(img, (0, 0), (size - 1, size - 1), (0, 0, 255), 2)
    cv2.line(img, (0, size - 1), (size - 1, 0), (0, 255, 0), 2)
    return img


def test_opencv_template_match_finds_exact_template(tmp_path):
    screenshot = np.full((240, 320, 3), 245, dtype=np.uint8)
    pattern = _create_pattern(28)

    top, left = 90, 140
    screenshot[top : top + 28, left : left + 28] = pattern

    screenshot_path = tmp_path / "screen.png"
    template_path = tmp_path / "pattern.png"
    cv2.imwrite(str(screenshot_path), screenshot)
    cv2.imwrite(str(template_path), pattern)

    result = matcher_tool.match_templates(
        image_path=str(screenshot_path),
        template_path=str(template_path),
        threshold=0.9,
        multi_scale=False,
        max_results=3,
    )

    assert result["found"] is True
    assert result["template_name"] == "pattern"
    assert abs(result["x"] - (left + 14)) <= 2
    assert abs(result["y"] - (top + 14)) <= 2
    assert result["confidence"] >= 0.9


def test_opencv_template_match_supports_multi_scale(tmp_path):
    screenshot = np.full((260, 360, 3), 250, dtype=np.uint8)
    pattern = _create_pattern(20)
    scaled_pattern = cv2.resize(pattern, (32, 32), interpolation=cv2.INTER_CUBIC)

    top, left = 120, 190
    screenshot[top : top + 32, left : left + 32] = scaled_pattern

    screenshot_path = tmp_path / "screen_scaled.png"
    template_path = tmp_path / "pattern_base.png"
    cv2.imwrite(str(screenshot_path), screenshot)
    cv2.imwrite(str(template_path), pattern)

    no_scale = matcher_tool.match_templates(
        image_path=str(screenshot_path),
        template_path=str(template_path),
        threshold=0.85,
        multi_scale=False,
        max_results=1,
    )
    assert no_scale["found"] is False

    with_scale = matcher_tool.match_templates(
        image_path=str(screenshot_path),
        template_path=str(template_path),
        threshold=0.85,
        multi_scale=True,
        max_results=2,
    )
    assert with_scale["found"] is True
    assert abs(with_scale["x"] - (left + 16)) <= 3
    assert abs(with_scale["y"] - (top + 16)) <= 3

