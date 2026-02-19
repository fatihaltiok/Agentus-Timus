import sys
import types
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import tools.florence2_tool.tool as florence_tool


def _reset_paddle_state():
    florence_tool._paddle_ocr = None
    florence_tool._paddle_ocr_init_failed = False


def test_get_paddle_ocr_uses_cpu_safe_config_after_legacy_failure(monkeypatch):
    _reset_paddle_state()
    calls = []

    class FakePaddleOCR:
        def __init__(self, **kwargs):
            calls.append(kwargs)
            if "use_gpu" in kwargs:
                raise ValueError("Unknown argument: use_gpu")

    monkeypatch.setitem(
        sys.modules,
        "paddleocr",
        types.SimpleNamespace(PaddleOCR=FakePaddleOCR),
    )

    ocr = florence_tool._get_paddle_ocr()
    assert ocr is not None
    assert len(calls) == 2
    assert calls[1]["device"] == "cpu"
    assert calls[1]["enable_hpi"] is False
    assert calls[1]["enable_mkldnn"] is False
    assert calls[1]["cpu_threads"] == 4

    # Cached instance should be reused without extra init attempts.
    same = florence_tool._get_paddle_ocr()
    assert same is ocr
    assert len(calls) == 2


def test_get_paddle_ocr_marks_failed_if_all_configs_fail(monkeypatch):
    _reset_paddle_state()
    calls = []

    class AlwaysFailPaddleOCR:
        def __init__(self, **kwargs):
            calls.append(kwargs)
            raise RuntimeError("init failed")

    monkeypatch.setitem(
        sys.modules,
        "paddleocr",
        types.SimpleNamespace(PaddleOCR=AlwaysFailPaddleOCR),
    )

    first = florence_tool._get_paddle_ocr()
    assert first is None
    assert florence_tool._paddle_ocr_init_failed is True
    assert len(calls) == 3  # all config variants tried

    # After failure flag, no further init attempts.
    second = florence_tool._get_paddle_ocr()
    assert second is None
    assert len(calls) == 3


def test_paddle_ocr_texts_falls_back_without_cls_and_parses_dict_format(monkeypatch):
    class FakeOCR:
        def ocr(self, _arr, cls=None):
            if cls is not None:
                raise TypeError("unexpected keyword argument 'cls'")
            return [
                {
                    "rec_texts": ["HELLO 123", ""],
                    "rec_scores": [0.954, 0.2],
                    "dt_polys": [
                        np.array([[10, 10], [40, 10], [40, 20], [10, 20]]),
                        np.array([[0, 0], [2, 0], [2, 2], [0, 2]]),
                    ],
                }
            ]

    monkeypatch.setattr(florence_tool, "_get_paddle_ocr", lambda: FakeOCR())
    img = Image.new("RGB", (100, 40), "white")
    texts, backend = florence_tool._paddle_ocr_texts(img)

    assert backend == "paddleocr"
    assert len(texts) == 1
    assert texts[0]["text"] == "HELLO 123"
    assert texts[0]["bbox"] == [10, 10, 40, 20]
    assert texts[0]["center"] == [25, 15]
    assert texts[0]["confidence"] == 0.95


def test_hybrid_analysis_propagates_paddle_runtime_status(monkeypatch):
    img = Image.new("RGB", (320, 200), "white")
    monkeypatch.setattr(florence_tool, "_caption", lambda _img: "dummy caption")
    monkeypatch.setattr(
        florence_tool,
        "_detect_ui",
        lambda _img: {"elements": [{"label": "btn", "bbox": [0, 0, 50, 50], "center": [25, 25]}]},
    )
    monkeypatch.setattr(florence_tool, "_paddle_ocr_texts", lambda _img: ([], "paddleocr_error"))

    result = florence_tool._hybrid_analysis(img)
    assert result["ocr_backend"] == "paddleocr_error"
    assert result["text_count"] == 0
