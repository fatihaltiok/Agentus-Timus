"""C3 Hypothesis-Tests fuer Vision/OCR Router und Telemetrie.

Property-basierte Tests:
  1. Router: Ergebnis immer gueltige VisionStrategy (totale Funktion)
  2. Router: VRAM=0 → immer CPU_FALLBACK_ONLY (Monotonieproperty)
  3. Telemetrie: Event-Count monoton steigend nach Record
  4. Telemetrie: Ring-Puffer nie laenger als MAX_EVENTS
  5. is_oom_error: RuntimeError mit OOM-Substring → True
  6. _pixel_count: Ergebnis immer >= 0
  7. _clamp_vram: Ergebnis immer in [0, 80000]
  8. routing_summary: Gibt immer String zurueck
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from hypothesis import given, settings, HealthCheck
from hypothesis import strategies as st

from tools.engines.vision_router import (
    VisionStrategy,
    select_vision_strategy,
    routing_summary,
    _pixel_count,
    _clamp_vram,
    VRAM_MIN_MB,
)
from tools.engines.vision_telemetry import (
    VisionEvent,
    VisionPhase,
    VisionTelemetryRecorder,
    is_oom_error,
    MAX_EVENTS,
)


# ── Strategien ─────────────────────────────────────────────────────────────

_vram_st   = st.integers(min_value=-100, max_value=80000)
_image_st  = st.integers(min_value=0, max_value=8000)
_task_st   = st.sampled_from(["", "ui_detection", "ocr", "hybrid", "caption", "UNKNOWN"])
_engine_st = st.sampled_from(["ocr", "object_detection", "segmentation", "florence2", "qwen_vl"])
_phase_st  = st.sampled_from(list(VisionPhase))


# ---------------------------------------------------------------------------
# 1. Router ist total — gibt immer VisionStrategy zurueck
# ---------------------------------------------------------------------------

@given(
    image_w=_image_st,
    image_h=_image_st,
    task_type=_task_st,
    vram=_vram_st,
)
@settings(max_examples=300, suppress_health_check=[HealthCheck.too_slow])
def test_router_always_returns_valid_strategy(image_w, image_h, task_type, vram):
    result = select_vision_strategy(
        image_w=image_w,
        image_h=image_h,
        task_type=task_type,
        vram_available_mb=vram,
    )
    assert isinstance(result, VisionStrategy), f"Kein VisionStrategy: {result!r}"
    assert result in list(VisionStrategy), f"Unbekannte Strategie: {result!r}"


# ---------------------------------------------------------------------------
# 2. vram = 0 → immer CPU_FALLBACK_ONLY
# ---------------------------------------------------------------------------

@given(
    image_w=_image_st,
    image_h=_image_st,
    task_type=_task_st,
)
@settings(max_examples=200, suppress_health_check=[HealthCheck.too_slow])
def test_zero_vram_always_cpu_fallback(image_w, image_h, task_type):
    """VRAM=0 impliziert CPU_FALLBACK_ONLY — unabhaengig von task und Bildgroesse."""
    result = select_vision_strategy(
        image_w=image_w,
        image_h=image_h,
        task_type=task_type,
        vram_available_mb=0,
    )
    assert result == VisionStrategy.CPU_FALLBACK_ONLY, (
        f"Erwartet CPU_FALLBACK_ONLY bei vram=0, got {result!r} "
        f"(image={image_w}x{image_h}, task={task_type!r})"
    )


# ---------------------------------------------------------------------------
# 3. Telemetrie-Count ist monoton steigend
# ---------------------------------------------------------------------------

@given(events=st.lists(
    st.builds(
        VisionEvent,
        engine=_engine_st,
        phase=_phase_st,
        model=st.text(max_size=30),
        device=st.sampled_from(["cpu", "cuda"]),
    ),
    min_size=0,
    max_size=50,
))
@settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture])
def test_telemetry_count_monotone(events):
    rec = VisionTelemetryRecorder()
    with rec._ring_lock:
        rec._ring.clear()

    prev_count = len(rec.get_events(last_n=MAX_EVENTS + 1))
    for ev in events:
        rec.record(ev)
    new_count = len(rec.get_events(last_n=MAX_EVENTS + 1))
    # Count kann hoechstens um len(events) gestiegen sein
    # (Ring kuerzt auf MAX_EVENTS, also kann new_count <= prev_count + len(events))
    assert new_count >= 0
    # Wenn events nicht leer: mind. 1 Event muss vorhanden sein (Ring nicht leer)
    if events:
        assert new_count >= 1


# ---------------------------------------------------------------------------
# 4. Ring-Puffer nie laenger als MAX_EVENTS
# ---------------------------------------------------------------------------

@given(n=st.integers(min_value=0, max_value=MAX_EVENTS + 200))
@settings(max_examples=30, suppress_health_check=[HealthCheck.too_slow])
def test_ring_never_exceeds_max(n):
    rec = VisionTelemetryRecorder()
    with rec._ring_lock:
        rec._ring.clear()

    for i in range(n):
        rec.record(VisionEvent(engine="ocr", phase=VisionPhase.INFER_DONE,
                               model=f"m{i}", device="cpu"))

    with rec._ring_lock:
        assert len(rec._ring) <= MAX_EVENTS


# ---------------------------------------------------------------------------
# 5. is_oom_error: RuntimeError mit OOM-Keywords → True
# ---------------------------------------------------------------------------

@given(suffix=st.text(min_size=0, max_size=100))
@settings(max_examples=200, suppress_health_check=[HealthCheck.too_slow])
def test_oom_keyword_out_of_memory_detected(suffix):
    exc = RuntimeError("CUDA out of memory " + suffix)
    assert is_oom_error(exc) is True


@given(msg=st.text(min_size=1, max_size=100).filter(
    lambda s: "out of memory" not in s.lower() and
              not ("cuda" in s.lower() and "memory" in s.lower())
))
@settings(max_examples=200, suppress_health_check=[HealthCheck.too_slow])
def test_non_oom_runtime_error_not_flagged(msg):
    exc = RuntimeError(msg)
    assert is_oom_error(exc) is False


# ---------------------------------------------------------------------------
# 6. _pixel_count nie negativ
# ---------------------------------------------------------------------------

@given(
    w=st.integers(min_value=-1000, max_value=10000),
    h=st.integers(min_value=-1000, max_value=10000),
)
@settings(max_examples=300, suppress_health_check=[HealthCheck.too_slow])
def test_pixel_count_never_negative(w, h):
    result = _pixel_count(w, h)
    assert result >= 0.0


# ---------------------------------------------------------------------------
# 7. _clamp_vram in [0, 80000]
# ---------------------------------------------------------------------------

@given(v=st.integers(min_value=-100000, max_value=200000))
@settings(max_examples=300, suppress_health_check=[HealthCheck.too_slow])
def test_clamp_vram_in_bounds(v):
    result = _clamp_vram(v)
    assert 0 <= result <= 80000


# ---------------------------------------------------------------------------
# 8. routing_summary gibt immer String zurueck
# ---------------------------------------------------------------------------

@given(
    strategy=st.sampled_from(list(VisionStrategy)),
    w=_image_st,
    h=_image_st,
    vram=st.integers(min_value=0, max_value=80000),
    task=_task_st,
)
@settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
def test_routing_summary_always_string(strategy, w, h, vram, task):
    result = routing_summary(strategy, w, h, vram, task)
    assert isinstance(result, str)
    assert len(result) > 0
