import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from tools.hybrid_input_tool.tool import hybrid_click_or_fill


class _FakeKeyboard:
    def __init__(self):
        self.inserted = []

    async def insert_text(self, value: str):
        self.inserted.append(value)


class _FakeElement:
    def __init__(self):
        self.clicked = 0
        self.filled = []

    async def scroll_into_view_if_needed(self, timeout: int = 0):
        return None

    async def click(self, timeout: int = 0):
        self.clicked += 1

    async def fill(self, value: str):
        self.filled.append(value)


class _FakeLocator:
    def __init__(self, element: _FakeElement):
        self.first = element

    async def count(self) -> int:
        return 1


class _FakePage:
    def __init__(self, active_tag: str, *, is_content_editable: bool = False):
        self.element = _FakeElement()
        self.keyboard = _FakeKeyboard()
        self._active_tag = active_tag
        self._is_content_editable = is_content_editable

    def locator(self, _selector: str):
        return _FakeLocator(self.element)

    async def evaluate(self, _script: str):
        return {
            "tag": self._active_tag,
            "isContentEditable": self._is_content_editable,
        }


@pytest.mark.asyncio
async def test_hybrid_click_or_fill_uses_insert_text_for_active_input():
    page = _FakePage("INPUT")

    success, method = await hybrid_click_or_fill(
        page=page,
        selector="input[name='q']",
        value="https://www.youtube.com/watch?v=abc",
    )

    assert success is True
    assert method == "DOM_INSERT_TEXT"
    assert page.keyboard.inserted == ["https://www.youtube.com/watch?v=abc"]
    assert page.element.filled == []


@pytest.mark.asyncio
async def test_hybrid_click_or_fill_uses_fill_for_non_input_elements():
    page = _FakePage("DIV", is_content_editable=False)

    success, method = await hybrid_click_or_fill(
        page=page,
        selector="[data-testid='search-box']",
        value="leder jacken",
    )

    assert success is True
    assert method == "DOM_FILL"
    assert page.keyboard.inserted == []
    assert page.element.filled == ["leder jacken"]
