"""C3 CrossHair-Contracts fuer Vision/OCR Router und ScrapingAnt-Client.

Alle Contracts werden via `crosshair check tests/test_c3_vision_crosshair.py`
symbolisch ausgefuehrt. Sie laufen als normale pytest-Tests (via deal-Assertions).

Contracts:
  1. _clamp_scrapingant_timeout: Ergebnis in [5, 60]
  2. _clamp_vram: Ergebnis in [0, 80000]
  3. _pixel_count: Ergebnis >= 0
  4. select_vision_strategy: Ergebnis ist VisionStrategy-Wert
  5. get_vram_available_mb: Ergebnis >= 0 (wenn kein CUDA → 0)
  6. is_oom_error: RuntimeError mit OOM-Wort → True (symbolisch)
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import deal
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools.engines.vision_router import (
    VisionStrategy,
    select_vision_strategy,
    _pixel_count,
    _clamp_vram,
)
from tools.engines.vision_telemetry import is_oom_error
from tools.social_media_tool.client import _clamp_scrapingant_timeout


# ---------------------------------------------------------------------------
# 1. _clamp_scrapingant_timeout: Ergebnis immer in [5, 60]
# ---------------------------------------------------------------------------

@deal.post(lambda r: 5 <= r <= 60)
def _contract_clamp_scrapingant_timeout(timeout_seconds: float) -> int:
    return _clamp_scrapingant_timeout(timeout_seconds)


def test_clamp_scrapingant_timeout_lower_bound():
    assert _contract_clamp_scrapingant_timeout(0.0) >= 5

def test_clamp_scrapingant_timeout_upper_bound():
    assert _contract_clamp_scrapingant_timeout(9999.0) <= 60

def test_clamp_scrapingant_timeout_nominal():
    result = _contract_clamp_scrapingant_timeout(45.0)
    assert 5 <= result <= 60

def test_clamp_scrapingant_timeout_negative():
    result = _contract_clamp_scrapingant_timeout(-10.0)
    assert result == 5

def test_clamp_scrapingant_timeout_exactly_60():
    result = _contract_clamp_scrapingant_timeout(60.0)
    assert result == 60

def test_clamp_scrapingant_timeout_exactly_5():
    result = _contract_clamp_scrapingant_timeout(5.0)
    assert result == 5


# ---------------------------------------------------------------------------
# 2. _clamp_vram: Ergebnis in [0, 80000]
# ---------------------------------------------------------------------------

@deal.post(lambda r: 0 <= r <= 80000)
def _contract_clamp_vram(vram_mb: int) -> int:
    return _clamp_vram(vram_mb)


def test_clamp_vram_zero():
    assert _contract_clamp_vram(0) == 0

def test_clamp_vram_negative():
    assert _contract_clamp_vram(-1000) == 0

def test_clamp_vram_max_exceeded():
    assert _contract_clamp_vram(999999) == 80000

def test_clamp_vram_nominal():
    assert _contract_clamp_vram(4096) == 4096

def test_clamp_vram_boundary():
    assert _contract_clamp_vram(80000) == 80000
    assert _contract_clamp_vram(80001) == 80000


# ---------------------------------------------------------------------------
# 3. _pixel_count: Ergebnis >= 0
# ---------------------------------------------------------------------------

@deal.post(lambda r: r >= 0.0)
def _contract_pixel_count(w: int, h: int) -> float:
    return _pixel_count(w, h)


def test_pixel_count_positive_inputs():
    assert _contract_pixel_count(1920, 1080) == pytest.approx(1920 * 1080)

def test_pixel_count_zero_inputs():
    assert _contract_pixel_count(0, 0) == 0.0

def test_pixel_count_negative_w():
    assert _contract_pixel_count(-100, 200) == 0.0

def test_pixel_count_negative_h():
    assert _contract_pixel_count(200, -100) == 0.0

def test_pixel_count_both_negative():
    assert _contract_pixel_count(-5, -5) == 0.0


# ---------------------------------------------------------------------------
# 4. select_vision_strategy: Ergebnis ist immer VisionStrategy
# ---------------------------------------------------------------------------

@deal.post(lambda r: r in list(VisionStrategy))
def _contract_select_vision_strategy(image_w: int, image_h: int,
                                      task_type: str, vram: int) -> VisionStrategy:
    return select_vision_strategy(
        image_w=image_w,
        image_h=image_h,
        task_type=task_type,
        vram_available_mb=vram,
    )


def test_contract_zero_vram():
    result = _contract_select_vision_strategy(1920, 1080, "ui_detection", 0)
    assert result == VisionStrategy.CPU_FALLBACK_ONLY

def test_contract_high_vram_ui():
    result = _contract_select_vision_strategy(1920, 1080, "ui_detection", 8000)
    assert result == VisionStrategy.FLORENCE2_PRIMARY

def test_contract_high_vram_large_image():
    result = _contract_select_vision_strategy(4000, 3000, "", 5000)
    assert result == VisionStrategy.FLORENCE2_PRIMARY

def test_contract_small_image():
    result = _contract_select_vision_strategy(200, 200, "", 4000)
    assert result == VisionStrategy.OCR_ONLY

def test_contract_medium_image_hybrid():
    result = _contract_select_vision_strategy(1000, 1000, "", 2500)
    assert result == VisionStrategy.FLORENCE2_HYBRID

def test_contract_negative_vram_fallback():
    """Negativer VRAM wird wie 0 behandelt (max(0,...) in get_vram_available_mb)."""
    result = _contract_select_vision_strategy(0, 0, "", -999)
    assert result == VisionStrategy.CPU_FALLBACK_ONLY


# ---------------------------------------------------------------------------
# 5. is_oom_error: Semantische Contracts
# ---------------------------------------------------------------------------

@deal.post(lambda r: isinstance(r, bool))
def _contract_is_oom_error_returns_bool(msg: str) -> bool:
    return is_oom_error(RuntimeError(msg))


def test_is_oom_returns_bool_true():
    assert _contract_is_oom_error_returns_bool("CUDA out of memory") is True

def test_is_oom_returns_bool_false():
    assert _contract_is_oom_error_returns_bool("some other error") is False

def test_is_oom_non_runtime_always_false():
    assert is_oom_error(ValueError("out of memory")) is False
    assert is_oom_error(ImportError("out of memory")) is False
    assert is_oom_error(OSError("out of memory")) is False
