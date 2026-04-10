import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.mouse_tool import tool as mouse_tool_module


class _FakePyAutoGUI:
    FAILSAFE = True

    class FailSafeException(Exception):
        pass

    @staticmethod
    def size():
        return (1920, 1080)

    @staticmethod
    def position():
        return (120, 140)

    @staticmethod
    def moveTo(*args, **kwargs):
        return None

    @staticmethod
    def write(*args, **kwargs):
        return None

    @staticmethod
    def hotkey(*keys):
        return None

    @staticmethod
    def press(key):
        return None


@pytest.mark.asyncio
async def test_type_text_promotes_url_like_input_to_clipboard(monkeypatch):
    clipboard = {}
    pressed = []
    write_calls = []

    class _RecordingPyAutoGUI(_FakePyAutoGUI):
        @staticmethod
        def hotkey(*keys):
            pressed.append(list(keys))

        @staticmethod
        def write(*args, **kwargs):
            write_calls.append((args, kwargs))

    def _fake_set_clipboard(text):
        clipboard["text"] = text
        return "xclip"

    monkeypatch.setattr(mouse_tool_module, "pyautogui", _RecordingPyAutoGUI)
    monkeypatch.setattr(mouse_tool_module, "_set_clipboard_text", _fake_set_clipboard)

    result = await mouse_tool_module.type_text(
        "https://github.com/login",
        press_enter_after=False,
        method="auto",
    )

    assert result["status"] == "typed"
    assert result["method"] == "clipboard"
    assert result["requested_method"] == "auto"
    assert clipboard["text"] == "https://github.com/login"
    assert pressed[-1] == ["ctrl", "v"]
    assert not write_calls


@pytest.mark.asyncio
async def test_type_text_does_not_fallback_to_write_for_url_when_clipboard_fails(monkeypatch):
    write_calls = []

    class _RecordingPyAutoGUI(_FakePyAutoGUI):
        @staticmethod
        def write(*args, **kwargs):
            write_calls.append((args, kwargs))

    def _raise_clipboard(_text):
        raise RuntimeError("clipboard unavailable")

    monkeypatch.setattr(mouse_tool_module, "pyautogui", _RecordingPyAutoGUI)
    monkeypatch.setattr(mouse_tool_module, "_set_clipboard_text", _raise_clipboard)

    with pytest.raises(Exception, match="Typ-Operation fehlgeschlagen"):
        await mouse_tool_module.type_text(
            "https://github.com/login",
            press_enter_after=False,
            method="clipboard",
        )

    assert not write_calls

