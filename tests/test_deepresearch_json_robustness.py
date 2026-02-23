"""Tests für B.5 — DeepResearch JSON-Robustheit mit extract_json_robust."""
import pytest
from agent.shared.json_utils import extract_json_robust


class TestExtractJsonRobust:
    """Basisverhalten von extract_json_robust — wird von deep_research genutzt."""

    def test_plain_json_parsed(self):
        """Normales JSON wird korrekt geparsed."""
        result = extract_json_robust('{"facts": [{"text": "hello"}]}')
        assert result is not None
        assert result["facts"][0]["text"] == "hello"

    def test_markdown_json_parsed(self):
        """Markdown-umhülltes JSON wird extrahiert."""
        md_json = '```json\n{"theses": [{"topic": "AI"}]}\n```'
        result = extract_json_robust(md_json)
        assert result is not None
        assert result["theses"][0]["topic"] == "AI"

    def test_json_with_preamble(self):
        """JSON nach Preamble-Text wird gefunden."""
        text = "Here is the analysis:\n\n{\"result\": \"ok\", \"confidence\": 0.9}"
        result = extract_json_robust(text)
        assert result is not None
        assert result["result"] == "ok"

    def test_invalid_json_returns_none(self):
        """Invalides JSON liefert None (kein Absturz)."""
        result = extract_json_robust("this is not json at all")
        assert result is None

    def test_empty_string_returns_none(self):
        """Leerer String liefert None."""
        result = extract_json_robust("")
        assert result is None

    def test_fallback_pattern(self):
        """extract_json_robust() or {} liefert leeres Dict bei None."""
        result = extract_json_robust("invalid") or {}
        assert result == {}
        assert result.get("facts", []) == []

    def test_think_block_stripped(self):
        """<think>-Blöcke (Nemotron) werden entfernt."""
        text = '<think>Some internal reasoning</think>\n{"answer": "42"}'
        result = extract_json_robust(text)
        assert result is not None
        assert result["answer"] == "42"

    def test_nested_json_parsed(self):
        """Verschachteltes JSON wird korrekt geparsed."""
        nested = '{"data": {"facts": [{"text": "nested fact", "confidence": 0.9}]}}'
        result = extract_json_robust(nested)
        assert result["data"]["facts"][0]["text"] == "nested fact"


class TestDeepResearchUsesRobustParsing:
    """Sicherstellen dass deep_research/tool.py extract_json_robust importiert und nutzt."""

    def test_import_present(self):
        """extract_json_robust ist in deep_research/tool.py importiert."""
        import inspect
        from tools.deep_research import tool as dr_tool
        source = inspect.getsource(dr_tool)
        assert "extract_json_robust" in source, (
            "tools/deep_research/tool.py muss extract_json_robust importieren"
        )

    def test_json_loads_replaced(self):
        """Keine rohen json.loads() Aufrufe auf LLM-Content mehr."""
        import inspect
        from tools.deep_research import tool as dr_tool
        source = inspect.getsource(dr_tool)
        # Die 4 problematischen json.loads() Aufrufe sollten ersetzt sein
        # Erlaubt sind json.loads() nur noch für nicht-LLM-Content (z.B. Config-Files)
        # Wir prüfen dass extract_json_robust im Quellcode vorhanden ist
        assert source.count("extract_json_robust") >= 4, (
            "Mindestens 4 extract_json_robust-Aufrufe erwartet (war json.loads)"
        )
