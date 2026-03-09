from __future__ import annotations

import os
from types import SimpleNamespace

import tools.engines.object_detection_engine as object_detection_engine
import tools.engines.ocr_engine as ocr_engine
import tools.engines.qwen_vl_engine as qwen_vl_engine
import tools.engines.segmentation_engine as segmentation_engine
import tools.florence2_tool.tool as florence_tool


class _FakeModel:
    def __init__(self) -> None:
        self.device = None

    def to(self, device: str):
        self.device = device
        return self

    def eval(self):
        return self


def test_object_detection_engine_passes_pinned_revision(monkeypatch) -> None:
    seen: dict[str, tuple[str, str]] = {}

    class FakeYolos(_FakeModel):
        @classmethod
        def from_pretrained(cls, model_name: str, revision: str):
            seen["model"] = (model_name, revision)
            return cls()

    class FakeProcessor:
        @classmethod
        def from_pretrained(cls, model_name: str, revision: str):
            seen["processor"] = (model_name, revision)
            return cls()

    monkeypatch.delenv("YOLOS_MODEL_REVISION", raising=False)
    monkeypatch.setattr(object_detection_engine, "TRANSFORMERS_AVAILABLE", True)
    monkeypatch.setattr(object_detection_engine, "YolosForObjectDetection", FakeYolos)
    monkeypatch.setattr(object_detection_engine, "YolosImageProcessor", FakeProcessor)
    monkeypatch.setattr(object_detection_engine.torch.cuda, "is_available", lambda: False)
    object_detection_engine.ObjectDetectionEngine._instance = None

    engine = object_detection_engine.ObjectDetectionEngine()
    engine.initialize()

    assert seen["model"][0] == "hustvl/yolos-tiny"
    assert seen["model"][1] == "95a90f3c189fbfca3bcfc6d7315b9e84d95dc2de"
    assert seen["processor"] == seen["model"]


def test_ocr_engine_passes_pinned_revision(monkeypatch) -> None:
    seen: dict[str, tuple[str, str]] = {}

    class FakeProcessor:
        @classmethod
        def from_pretrained(cls, model_name: str, revision: str):
            seen["processor"] = (model_name, revision)
            return cls()

    class FakeVisionEncoderDecoder(_FakeModel):
        @classmethod
        def from_pretrained(cls, model_name: str, revision: str):
            seen["model"] = (model_name, revision)
            return cls()

    monkeypatch.delenv("TROCR_MODEL_REVISION", raising=False)
    monkeypatch.setattr(ocr_engine, "TrOCRProcessor", FakeProcessor)
    monkeypatch.setattr(ocr_engine, "VisionEncoderDecoderModel", FakeVisionEncoderDecoder)
    ocr_engine.OCREngine._instance = None

    engine = ocr_engine.OCREngine()
    engine._init_trocr()

    assert seen["processor"][0] == "microsoft/trocr-base-printed"
    assert seen["processor"][1] == "93450be3f1ed40a930690d951ef3932687cc1892"
    assert seen["model"] == seen["processor"]


def test_segmentation_engine_passes_pinned_revisions(monkeypatch) -> None:
    seen: dict[str, tuple[str, str]] = {}

    class FakeSamModel(_FakeModel):
        @classmethod
        def from_pretrained(cls, model_name: str, revision: str):
            seen["sam_model"] = (model_name, revision)
            return cls()

    class FakeSamProcessor:
        @classmethod
        def from_pretrained(cls, model_name: str, revision: str):
            seen["sam_processor"] = (model_name, revision)
            return cls()

    class FakeClipModel(_FakeModel):
        @classmethod
        def from_pretrained(cls, model_name: str, revision: str):
            seen["clip_model"] = (model_name, revision)
            return cls()

    class FakeClipProcessor:
        @classmethod
        def from_pretrained(cls, model_name: str, revision: str):
            seen["clip_processor"] = (model_name, revision)
            return cls()

    monkeypatch.delenv("SAM_MODEL_REVISION", raising=False)
    monkeypatch.delenv("CLIP_MODEL_REVISION", raising=False)
    monkeypatch.setattr(segmentation_engine, "TRANSFORMERS_AVAILABLE", True)
    monkeypatch.setattr(segmentation_engine, "SamModel", FakeSamModel)
    monkeypatch.setattr(segmentation_engine, "SamProcessor", FakeSamProcessor)
    monkeypatch.setattr(segmentation_engine, "CLIPForImageClassification", FakeClipModel)
    monkeypatch.setattr(segmentation_engine, "CLIPProcessor", FakeClipProcessor)
    monkeypatch.setattr(segmentation_engine.torch.cuda, "is_available", lambda: False)
    segmentation_engine.SegmentationEngine._instance = None

    engine = segmentation_engine.SegmentationEngine()
    engine.initialize()

    assert seen["sam_model"] == ("facebook/sam-vit-base", "70c1a07f894ebb5b307fd9eaaee97b9dfc16068f")
    assert seen["sam_processor"] == seen["sam_model"]
    assert seen["clip_model"] == ("openai/clip-vit-base-patch32", "3d74acf9a28c67741b2f4f2ea7635f0aaf6f0268")
    assert seen["clip_processor"] == seen["clip_model"]


def test_qwen_vl_engine_passes_pinned_revision(monkeypatch) -> None:
    seen: dict[str, tuple[str, str]] = {}

    class FakeProcessor:
        @classmethod
        def from_pretrained(cls, model_name: str, revision: str, trust_remote_code: bool):
            seen["processor"] = (model_name, revision)
            return cls()

    class FakeQwenModel(_FakeModel):
        @classmethod
        def from_pretrained(cls, model_name: str, revision: str, **kwargs):
            seen["model"] = (model_name, revision)
            return cls()

    monkeypatch.delenv("QWEN_VL_MODEL_REVISION", raising=False)
    monkeypatch.setenv("QWEN_VL_DEVICE", "cpu")
    monkeypatch.setenv("QWEN_VL_MODEL", "Qwen/Qwen2-VL-2B-Instruct")
    monkeypatch.setattr(qwen_vl_engine, "TRANSFORMERS_AVAILABLE", True)
    monkeypatch.setattr(qwen_vl_engine, "AutoProcessor", FakeProcessor)
    monkeypatch.setattr(qwen_vl_engine, "Qwen2VLForConditionalGeneration", FakeQwenModel)
    monkeypatch.setattr(qwen_vl_engine.torch.cuda, "is_available", lambda: False)
    qwen_vl_engine.QwenVLEngine._instance = None

    engine = qwen_vl_engine.QwenVLEngine()
    engine.initialize()

    assert seen["processor"] == ("Qwen/Qwen2-VL-2B-Instruct", "895c3a49bc3fa70a340399125c650a463535e71c")
    assert seen["model"] == seen["processor"]


def test_florence_loader_passes_pinned_revision(monkeypatch) -> None:
    import transformers
    import torch

    seen: dict[str, tuple[str, str]] = {}

    class FakeProcessor:
        @classmethod
        def from_pretrained(cls, model_name: str, revision: str, trust_remote_code: bool):
            seen["processor"] = (model_name, revision)
            return cls()

    class FakeFlorenceModel(_FakeModel):
        @classmethod
        def from_pretrained(cls, model_name: str, revision: str, **kwargs):
            seen["model"] = (model_name, revision)
            return cls()

    monkeypatch.delenv("FLORENCE2_MODEL_REVISION", raising=False)
    monkeypatch.setenv("FLORENCE2_DEVICE", "cpu")
    monkeypatch.setattr(transformers, "AutoProcessor", FakeProcessor)
    monkeypatch.setattr(transformers, "AutoModelForCausalLM", FakeFlorenceModel)
    monkeypatch.setattr(torch.cuda, "is_available", lambda: False)

    florence_tool._model = None
    florence_tool._processor = None
    florence_tool._device = "cpu"
    florence_tool._model_path = "microsoft/Florence-2-large-ft"

    florence_tool._load_model()

    assert seen["processor"] == ("microsoft/Florence-2-large-ft", "4a12a2b54b7016a48a22037fbd62da90cd566f2a")
    assert seen["model"] == seen["processor"]
