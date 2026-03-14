import sys
import types


def test_skill_recorder_uses_package_ocr_import(monkeypatch):
    fake_module = types.ModuleType("tools.engines.ocr_engine")

    class FakeEngine:
        def __init__(self):
            self.ready = True

    fake_module.OCREngine = FakeEngine
    monkeypatch.setitem(sys.modules, "tools.engines.ocr_engine", fake_module)
    monkeypatch.delitem(sys.modules, "ocr_engine", raising=False)

    from tools.skill_recorder.tool import ActionRecorder

    recorder = ActionRecorder()

    assert recorder.ocr_engine is not None
    assert isinstance(recorder.ocr_engine, FakeEngine)
