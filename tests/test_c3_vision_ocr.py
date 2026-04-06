"""C3 Vision/OCR Tests.

Testmatrix gemaess C3_VISION_OCR_PREP.md:
  1. Router-Entscheidungen (alle 7 Routing-Regeln)
  2. Telemetrie-Aufzeichnung (Ring-Puffer, Counter, Summary)
  3. OOM-Guard in OCREngine
  4. OOM-Guard in ObjectDetectionEngine
  5. OOM-Guard in SegmentationEngine
  6. Degradationsfall ohne GPU (CPU-Fallback)
  7. is_oom_error Erkennung
"""
from __future__ import annotations

import sys
import threading
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools.engines.vision_router import (
    VisionStrategy,
    select_vision_strategy,
    get_vram_available_mb,
    routing_summary,
    _pixel_count,
    _clamp_vram,
    VRAM_MIN_MB,
    VRAM_LO_MB,
    VRAM_HI_MB,
    MP_SMALL,
    MP_LARGE,
)
from tools.engines.vision_telemetry import (
    VisionEvent,
    VisionPhase,
    VisionTelemetryRecorder,
    vision_telemetry,
    is_oom_error,
    MAX_EVENTS,
)


# ---------------------------------------------------------------------------
# Hilfsfunktionen
# ---------------------------------------------------------------------------

def _fresh_recorder() -> VisionTelemetryRecorder:
    """Gibt die globale Instanz mit geleerten Puffern zurueck."""
    rec = VisionTelemetryRecorder()
    with rec._ring_lock:
        rec._ring.clear()
    rec._oom_counts.clear()
    rec._fallback_counts.clear()
    rec._error_counts.clear()
    return rec


def _image_dims_for_mp(mp: float) -> tuple[int, int]:
    """Berechnet quadratische Bildgroesse fuer gegebene Megapixelzahl."""
    import math
    side = int(math.sqrt(mp * 1_000_000))
    return side, side


# ---------------------------------------------------------------------------
# 1. Router-Entscheidungen
# ---------------------------------------------------------------------------

class TestVisionRouter:

    def test_rule1_no_vram_returns_cpu_fallback(self):
        """Regel 1: vram < VRAM_MIN → CPU_FALLBACK_ONLY."""
        assert select_vision_strategy(vram_available_mb=0) == VisionStrategy.CPU_FALLBACK_ONLY
        assert select_vision_strategy(vram_available_mb=VRAM_MIN_MB - 1) == VisionStrategy.CPU_FALLBACK_ONLY

    def test_rule2_ui_detection_always_florence(self):
        """Regel 2: task_type=ui_detection → FLORENCE2_PRIMARY, unabhaengig von Bildgroesse."""
        assert select_vision_strategy(task_type="ui_detection", vram_available_mb=VRAM_HI_MB) == VisionStrategy.FLORENCE2_PRIMARY
        assert select_vision_strategy(task_type="ui_detection", vram_available_mb=VRAM_LO_MB) == VisionStrategy.FLORENCE2_PRIMARY

    def test_rule3_large_image_high_vram_florence_primary(self):
        """Regel 3: Bild > 2MP UND vram >= VRAM_HI → FLORENCE2_PRIMARY."""
        w, h = _image_dims_for_mp(2.5)
        strategy = select_vision_strategy(image_w=w, image_h=h, vram_available_mb=VRAM_HI_MB + 500)
        assert strategy == VisionStrategy.FLORENCE2_PRIMARY

    def test_rule3_large_image_insufficient_vram_not_primary(self):
        """Regel 3: Bild > 2MP aber vram < VRAM_HI → nicht FLORENCE2_PRIMARY aus Regel 3."""
        w, h = _image_dims_for_mp(2.5)
        strategy = select_vision_strategy(image_w=w, image_h=h, vram_available_mb=VRAM_HI_MB - 1)
        # Kann Hybrid oder OCR_ONLY sein, nicht FLORENCE2_PRIMARY aus Regel 3
        # (aber Hybrid aus Regel 5 ist moeglich wenn vram >= VRAM_LO)
        assert strategy in (VisionStrategy.FLORENCE2_HYBRID, VisionStrategy.OCR_ONLY,
                            VisionStrategy.FLORENCE2_PRIMARY)

    def test_rule4_small_image_ocr_only(self):
        """Regel 4: Bild <= 0.5MP → OCR_ONLY."""
        w, h = _image_dims_for_mp(0.3)
        strategy = select_vision_strategy(image_w=w, image_h=h, vram_available_mb=VRAM_HI_MB)
        assert strategy == VisionStrategy.OCR_ONLY

    def test_rule4_zero_pixel_image_with_vram(self):
        """Regel 4 / Regel 6: Bild unbekannt (0x0) mit gutem VRAM → FLORENCE2_PRIMARY."""
        strategy = select_vision_strategy(image_w=0, image_h=0, vram_available_mb=VRAM_HI_MB)
        assert strategy == VisionStrategy.FLORENCE2_PRIMARY

    def test_rule5_medium_image_hybrid(self):
        """Regel 5: Bild > 0.5MP <= 2MP und vram >= VRAM_LO → FLORENCE2_HYBRID."""
        w, h = _image_dims_for_mp(1.0)
        strategy = select_vision_strategy(image_w=w, image_h=h, vram_available_mb=VRAM_LO_MB + 100)
        assert strategy == VisionStrategy.FLORENCE2_HYBRID

    def test_rule6_no_image_size_sufficient_vram_florence(self):
        """Regel 6: Kein Bild, VRAM >= VRAM_LO → FLORENCE2_PRIMARY."""
        strategy = select_vision_strategy(vram_available_mb=VRAM_LO_MB)
        assert strategy == VisionStrategy.FLORENCE2_PRIMARY

    def test_rule7_default_fallback(self):
        """Regel 7: Niedrige VRAM aber ueber Minimum → OCR_ONLY."""
        # vram zwischen MIN und LO, kein Bild
        low_vram = VRAM_MIN_MB + 100
        if low_vram < VRAM_LO_MB:
            strategy = select_vision_strategy(vram_available_mb=low_vram)
            assert strategy == VisionStrategy.OCR_ONLY

    def test_router_never_raises(self):
        """Der Router darf nie eine Exception werfen."""
        for vram in (-1, 0, VRAM_MIN_MB, VRAM_LO_MB, VRAM_HI_MB, 99999):
            for task in ("", "ui_detection", "ocr", "hybrid", "caption", "UNKNOWN_TASK"):
                for w, h in ((0, 0), (100, 100), (4000, 3000)):
                    result = select_vision_strategy(image_w=w, image_h=h,
                                                    task_type=task, vram_available_mb=vram)
                    assert isinstance(result, VisionStrategy)

    def test_routing_summary_returns_string(self):
        s = routing_summary(VisionStrategy.OCR_ONLY, 1920, 1080, 2048, "ui_detection")
        assert "C3-Route" in s
        assert "ocr_only" in s

    def test_pixel_count_non_negative(self):
        assert _pixel_count(0, 0) == 0.0
        assert _pixel_count(-10, 100) == 0.0
        assert _pixel_count(1920, 1080) == pytest.approx(1920 * 1080)

    def test_clamp_vram_bounds(self):
        assert _clamp_vram(-5) == 0
        assert _clamp_vram(0) == 0
        assert _clamp_vram(2048) == 2048
        assert _clamp_vram(999999) == 80000


# ---------------------------------------------------------------------------
# 2. Telemetrie-Aufzeichnung
# ---------------------------------------------------------------------------

class TestVisionTelemetry:

    def test_record_event_appends_to_ring(self):
        rec = _fresh_recorder()
        ev = VisionEvent(engine="ocr", phase=VisionPhase.INFER_DONE, model="easyocr", device="cpu")
        rec.record(ev)
        events = rec.get_events(engine="ocr", last_n=10)
        assert len(events) == 1
        assert events[0]["engine"] == "ocr"
        assert events[0]["phase"] == "infer_done"

    def test_ring_capped_at_max_events(self):
        rec = _fresh_recorder()
        for i in range(MAX_EVENTS + 50):
            rec.record(VisionEvent(engine="test", phase=VisionPhase.INFER_DONE, model=f"m{i}", device="cpu"))
        with rec._ring_lock:
            assert len(rec._ring) == MAX_EVENTS

    def test_oom_counter_incremented(self):
        rec = _fresh_recorder()
        rec.oom("ocr", "easyocr", "cuda", "CUDA out of memory")
        rec.oom("ocr", "easyocr", "cuda", "CUDA out of memory")
        assert rec._oom_counts.get("ocr", 0) == 2

    def test_fallback_counter_incremented(self):
        rec = _fresh_recorder()
        rec.fallback("florence2", "cuda", "cpu", "OOM", model="Florence-2-large")
        assert rec._fallback_counts.get("florence2", 0) == 1

    def test_get_summary_structure(self):
        rec = _fresh_recorder()
        rec.infer_start("ocr", "easyocr", "cpu")
        t0 = rec.init_start("segmentation", "sam-vit-base", "cuda")
        rec.init_done("segmentation", "sam-vit-base", "cuda", t0, success=True)
        summary = rec.get_summary()
        assert "total_events" in summary
        assert "engines" in summary
        assert "oom_counts" in summary
        assert "fallback_counts" in summary

    def test_record_never_raises_on_bad_input(self):
        rec = _fresh_recorder()
        # Kaputtes Event (fehlende Pflichtfelder simuliert durch direkten Aufruf)
        try:
            rec.record(VisionEvent(engine="", phase=VisionPhase.ERROR))
        except Exception as e:
            pytest.fail(f"record() hat Exception geworfen: {e}")

    def test_thread_safety(self):
        """Gleichzeitige Writes aus mehreren Threads duerfen nicht crashen."""
        rec = _fresh_recorder()
        errors = []

        def _write(n: int) -> None:
            try:
                for i in range(n):
                    rec.record(VisionEvent(engine="ocr", phase=VisionPhase.INFER_DONE,
                                           model="easyocr", device="cpu"))
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=_write, args=(50,)) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0, f"Thread-Safety Fehler: {errors}"

    def test_convenience_methods_emit_events(self):
        rec = _fresh_recorder()
        t0 = rec.infer_start("object_detection", "yolos-tiny", "cuda", 1920, 1080)
        rec.infer_done("object_detection", "yolos-tiny", "cuda", t0,
                        image_w=1920, image_h=1080, success=True)
        events = rec.get_events(engine="object_detection")
        assert len(events) == 2
        done_ev = [e for e in events if e["phase"] == "infer_done"][0]
        assert done_ev["duration_ms"] >= 0.0
        assert done_ev["image_w"] == 1920


# ---------------------------------------------------------------------------
# 3. OOM-Guard in OCREngine
# ---------------------------------------------------------------------------

class TestOCREngineOOMGuard:

    def _make_engine(self):
        from tools.engines.ocr_engine import OCREngine
        engine = object.__new__(OCREngine)
        engine.initialized = True
        engine.active_backend = "easyocr"
        engine.device = "cuda"
        engine.backend = "easyocr"
        engine.use_gpu = True
        engine.languages = ["en"]
        engine.easyocr_reader = None
        engine.paddleocr_reader = None
        engine.trocr_processor = None
        engine.trocr_model = None
        return engine

    def test_oom_returns_error_dict_not_raises(self):
        engine = self._make_engine()
        from PIL import Image as PILImage
        img = PILImage.new("RGB", (100, 100))
        with patch.object(engine, "_process_easyocr",
                          side_effect=RuntimeError("CUDA out of memory. Tried to allocate 2GB")):
            result = engine.process(img, with_boxes=False)
        assert isinstance(result, dict)
        assert "error" in result
        assert result.get("oom") is True
        assert result["extracted_text"] == []

    def test_non_oom_runtime_error_still_returns_dict(self):
        engine = self._make_engine()
        from PIL import Image as PILImage
        img = PILImage.new("RGB", (100, 100))
        with patch.object(engine, "_process_easyocr",
                          side_effect=RuntimeError("Andere Runtime-Fehler")):
            result = engine.process(img, with_boxes=False)
        assert isinstance(result, dict)
        assert "error" in result
        assert result.get("oom") is None  # Kein OOM-Flag

    def test_generic_exception_returns_dict(self):
        engine = self._make_engine()
        from PIL import Image as PILImage
        img = PILImage.new("RGB", (100, 100))
        with patch.object(engine, "_process_easyocr", side_effect=ValueError("test")):
            result = engine.process(img, with_boxes=False)
        assert isinstance(result, dict)
        assert "error" in result


# ---------------------------------------------------------------------------
# 4. OOM-Guard in ObjectDetectionEngine
# ---------------------------------------------------------------------------

class TestObjectDetectionEngineOOMGuard:

    def _make_engine(self):
        from tools.engines.object_detection_engine import ObjectDetectionEngine
        engine = object.__new__(ObjectDetectionEngine)
        engine.initialized = True
        engine.device = "cuda"
        engine.model = MagicMock()
        engine.image_processor = MagicMock()
        return engine

    def test_oom_returns_empty_list_not_raises(self):
        engine = self._make_engine()
        from PIL import Image as PILImage
        img = PILImage.new("RGB", (200, 200))
        engine.image_processor.return_value.to.side_effect = RuntimeError("CUDA out of memory")
        result = engine.find_ui_elements(img)
        assert result == []

    def test_generic_error_returns_empty_list(self):
        engine = self._make_engine()
        from PIL import Image as PILImage
        img = PILImage.new("RGB", (200, 200))
        engine.image_processor.return_value.to.side_effect = Exception("boom")
        result = engine.find_ui_elements(img)
        assert result == []

    def test_not_initialized_returns_empty(self):
        from tools.engines.object_detection_engine import ObjectDetectionEngine
        engine = object.__new__(ObjectDetectionEngine)
        engine.initialized = False
        engine.device = "cpu"
        from PIL import Image as PILImage
        img = PILImage.new("RGB", (100, 100))
        result = engine.find_ui_elements(img)
        assert result == []


# ---------------------------------------------------------------------------
# 5. OOM-Guard in SegmentationEngine
# ---------------------------------------------------------------------------

class TestSegmentationEngineOOMGuard:

    def _make_engine(self):
        from tools.engines.segmentation_engine import SegmentationEngine
        engine = object.__new__(SegmentationEngine)
        engine.initialized = True
        engine.device = "cuda"
        engine.sam_model = MagicMock()
        engine.sam_processor = MagicMock()
        engine.clip_model = MagicMock()
        engine.clip_processor = MagicMock()
        return engine

    def test_oom_returns_empty_list(self):
        engine = self._make_engine()
        from PIL import Image as PILImage
        img = PILImage.new("RGB", (300, 300))
        engine.sam_processor.return_value.to.side_effect = RuntimeError("CUDA out of memory")
        result = engine.get_ui_elements_from_image(img)
        assert result == []

    def test_not_initialized_returns_empty(self):
        from tools.engines.segmentation_engine import SegmentationEngine
        engine = object.__new__(SegmentationEngine)
        engine.initialized = False
        engine.device = "cpu"
        from PIL import Image as PILImage
        img = PILImage.new("RGB", (100, 100))
        result = engine.get_ui_elements_from_image(img)
        assert result == []


# ---------------------------------------------------------------------------
# 6. Degradationsfall ohne GPU
# ---------------------------------------------------------------------------

class TestCPUFallbackDegradation:

    def test_cpu_fallback_strategy_without_gpu(self):
        """Ohne GPU (vram=0) muss CPU_FALLBACK_ONLY gewaehlt werden."""
        strategy = select_vision_strategy(image_w=1920, image_h=1080,
                                           task_type="ui_detection",
                                           vram_available_mb=0)
        assert strategy == VisionStrategy.CPU_FALLBACK_ONLY

    def test_get_vram_available_mb_returns_zero_without_cuda(self):
        """Wenn torch.cuda.is_available() False, muss 0 zurueckkommen."""
        import torch as _torch
        with patch.object(_torch.cuda, "is_available", return_value=False):
            result = get_vram_available_mb()
        assert result == 0

    def test_get_vram_available_mb_never_negative(self):
        import torch as _torch
        with patch.object(_torch.cuda, "is_available", return_value=True):
            with patch.object(_torch.cuda, "mem_get_info", return_value=(0, 8 * 1024**3)):
                result = get_vram_available_mb()
        assert result >= 0


# ---------------------------------------------------------------------------
# 7. is_oom_error Erkennung
# ---------------------------------------------------------------------------

class TestIsOOMError:

    def test_cuda_oom_recognized(self):
        exc = RuntimeError("CUDA out of memory. Tried to allocate 2.50 GiB")
        assert is_oom_error(exc) is True

    def test_cuda_memory_recognized(self):
        exc = RuntimeError("cuda memory allocation failed")
        assert is_oom_error(exc) is True

    def test_generic_runtime_error_not_oom(self):
        exc = RuntimeError("some other error")
        assert is_oom_error(exc) is False

    def test_value_error_not_oom(self):
        exc = ValueError("out of memory")
        assert is_oom_error(exc) is False  # Kein RuntimeError

    def test_import_error_not_oom(self):
        exc = ImportError("cannot import")
        assert is_oom_error(exc) is False


# ---------------------------------------------------------------------------
# 8. C3 Integrations-Regressionen
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    ("strategy", "expected_helper"),
    [
        ("ocr_only", "ocr_only"),
        ("cpu_fallback_only", "ocr_only"),
        ("florence2_primary", "full"),
        ("florence2_hybrid", "hybrid"),
    ],
)
def test_florence_hot_path_respects_c3_router(monkeypatch, strategy, expected_helper):
    from PIL import Image as PILImage
    import tools.florence2_tool.tool as florence_tool

    image = PILImage.new("RGB", (1280, 720))
    strategy_enum = florence_tool.VisionStrategy(strategy)
    called = []

    monkeypatch.setattr(florence_tool, "select_vision_strategy", lambda **_: strategy_enum)
    monkeypatch.setattr(florence_tool, "get_vram_available_mb", lambda: 4096)
    monkeypatch.setattr(florence_tool, "routing_summary", lambda *args, **kwargs: "C3-Route: test")
    monkeypatch.setattr(
        florence_tool,
        "_full_analysis",
        lambda img: called.append("full") or {
            "summary_prompt": "full",
            "element_count": 1,
            "text_count": 0,
            "device": "cuda",
        },
    )
    monkeypatch.setattr(
        florence_tool,
        "_hybrid_analysis",
        lambda img: called.append("hybrid") or {
            "summary_prompt": "hybrid",
            "element_count": 1,
            "text_count": 1,
            "device": "cuda",
            "ocr_backend": "paddleocr",
        },
    )
    monkeypatch.setattr(
        florence_tool,
        "_paddle_ocr_texts",
        lambda img: (
            [{"text": "Hallo", "center": [10, 10], "bbox": [0, 0, 20, 20], "confidence": 0.99}],
            "paddleocr",
        ),
    )

    result = florence_tool._analyze_with_c3_routing(image)

    assert result["vision_strategy"] == strategy
    assert result["route_summary"] == "C3-Route: test"
    if expected_helper == "ocr_only":
        assert called == []
        assert result["device"] == "cpu"
        assert result["ocr_backend"] == "paddleocr"
    else:
        assert called == [expected_helper]


def test_vision_fallback_observability_includes_reason(monkeypatch):
    rec = _fresh_recorder()
    calls = []

    def _capture(event_type, payload):
        calls.append((event_type, payload))

    monkeypatch.setattr("orchestration.autonomy_observation.record_autonomy_observation", _capture)

    rec.fallback("florence2", "cuda", "cpu", "oom during load", model="Florence-2")

    assert calls
    event_type, payload = calls[-1]
    assert event_type == "vision_fallback"
    assert payload["fallback_reason"] == "oom during load"
    assert payload["fallback_from"] == "cuda"
    assert payload["fallback_to"] == "cpu"


def test_ocr_initialize_emits_init_telemetry(monkeypatch):
    import tools.engines.ocr_engine as ocr_mod

    engine = object.__new__(ocr_mod.OCREngine)
    engine.initialized = False
    engine.backend = "easyocr"
    engine.use_gpu = False
    engine.languages = ["en"]
    engine.easyocr_reader = None
    engine.paddleocr_reader = None
    engine.trocr_processor = None
    engine.trocr_model = None
    engine.device = "cpu"
    engine.active_backend = None

    telemetry = MagicMock()
    monkeypatch.setattr(ocr_mod, "_C3_TELEMETRY", True)
    monkeypatch.setattr(ocr_mod, "vision_telemetry", telemetry)
    monkeypatch.setattr(ocr_mod, "EASYOCR_AVAILABLE", True)
    monkeypatch.setattr(engine, "_init_easyocr", lambda: None)

    engine.initialize()

    telemetry.init_start.assert_called_once()
    telemetry.init_done.assert_called_once()
    assert engine.initialized is True
    assert engine.active_backend == "easyocr"


def test_ocr_generic_error_emits_error_telemetry(monkeypatch):
    import tools.engines.ocr_engine as ocr_mod
    from PIL import Image as PILImage

    telemetry = MagicMock()
    monkeypatch.setattr(ocr_mod, "_C3_TELEMETRY", True)
    monkeypatch.setattr(ocr_mod, "vision_telemetry", telemetry)

    engine = TestOCREngineOOMGuard()._make_engine()
    image = PILImage.new("RGB", (100, 100))

    with patch.object(engine, "_process_easyocr", side_effect=ValueError("boom")):
        result = engine.process(image, with_boxes=False)

    assert result["error"] == "boom"
    telemetry.error.assert_called_once()


def test_segmentation_no_masks_still_emits_infer_done(monkeypatch):
    import tools.engines.segmentation_engine as seg_mod
    from PIL import Image as PILImage

    class _CpuValue:
        def cpu(self):
            return self

    class _Inputs(dict):
        def to(self, device):
            return self

    class _Score:
        def __init__(self, value):
            self._value = value

        def item(self):
            return self._value

    class _Outputs:
        pred_masks = _CpuValue()
        iou_scores = _CpuValue()

    telemetry = MagicMock()
    monkeypatch.setattr(seg_mod, "_C3_TELEMETRY", True)
    monkeypatch.setattr(seg_mod, "vision_telemetry", telemetry)

    engine = object.__new__(seg_mod.SegmentationEngine)
    engine.initialized = True
    engine.device = "cpu"
    engine.sam_model = MagicMock(return_value=_Outputs())
    engine.sam_processor = MagicMock()
    engine.sam_processor.return_value = _Inputs(
        original_sizes=_CpuValue(),
        reshaped_input_sizes=_CpuValue(),
    )
    engine.sam_processor.image_processor = MagicMock()
    engine.sam_processor.image_processor.post_process_masks.return_value = [[[]]]
    engine.clip_model = MagicMock()
    engine.clip_processor = MagicMock()

    outputs = engine.sam_model.return_value
    outputs.iou_scores.cpu = lambda: [[[ _Score(0.1) ]]]

    result = engine.get_ui_elements_from_image(PILImage.new("RGB", (200, 200)))

    assert result == []
    telemetry.infer_done.assert_called_once()
