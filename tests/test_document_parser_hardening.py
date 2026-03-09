import io
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


class _FakeTextPage:
    def __init__(self, text: str):
        self._text = text

    def get_text_range(self):
        return self._text


class _FakePage:
    def __init__(self, text: str):
        self._text = text

    def get_textpage(self):
        return _FakeTextPage(self._text)

    def close(self):
        return None


def test_extract_text_with_pdfium_skips_broken_pages(monkeypatch):
    from tools.document_parser import tool as document_parser_tool

    class _FakePdfDocument:
        def __init__(self, _pdf_file: io.BytesIO):
            self._pages = ["Seite 1", "BROKEN", "Seite 3"]

        def __len__(self):
            return len(self._pages)

        def get_page(self, idx: int):
            if self._pages[idx] == "BROKEN":
                raise document_parser_tool.pdfium.PdfiumError("kaputt")
            return _FakePage(self._pages[idx])

        def close(self):
            return None

    monkeypatch.setattr(document_parser_tool.pdfium, "PdfDocument", _FakePdfDocument)

    text = document_parser_tool._extract_text_with_pdfium(b"%PDF-1.7")

    assert "Seite 1" in text
    assert "Seite 3" in text


def test_extract_text_with_pdfium_raises_when_all_pages_fail(monkeypatch):
    from tools.document_parser import tool as document_parser_tool

    class _FakePdfDocument:
        def __init__(self, _pdf_file: io.BytesIO):
            self._count = 2

        def __len__(self):
            return self._count

        def get_page(self, idx: int):
            raise document_parser_tool.pdfium.PdfiumError(f"kaputt-{idx}")

        def close(self):
            return None

    monkeypatch.setattr(document_parser_tool.pdfium, "PdfDocument", _FakePdfDocument)

    try:
        document_parser_tool._extract_text_with_pdfium(b"%PDF-1.7")
    except document_parser_tool.pdfium.PdfiumError as exc:
        assert "Keine PDF-Seite" in str(exc)
    else:
        raise AssertionError("PdfiumError erwartet")
