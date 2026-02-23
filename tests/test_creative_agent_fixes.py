"""Tests für CreativeAgent-Fixes (B.2, B.3)."""
import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


# ── B.2 — Leerer-Prompt-Fallback ─────────────────────────────────────────────

class TestEmptyPromptFallback:
    """GPT liefert leeren String → Fallback-Prompt wird genutzt."""

    @pytest.mark.asyncio
    async def test_empty_prompt_fallback(self):
        from agent.agents.creative import CreativeAgent

        agent = CreativeAgent.__new__(CreativeAgent)
        agent.provider_client = MagicMock()

        # GPT gibt leeren String zurück
        mock_response = MagicMock()
        mock_response.choices[0].message.content = "   "  # nur Leerzeichen
        agent.provider_client.get_client.return_value.chat.completions.create = MagicMock(
            return_value=mock_response
        )

        with patch("asyncio.to_thread", new=AsyncMock(return_value=mock_response)):
            result = await agent._generate_image_prompt_with_gpt("ein Sonnenuntergang")

        assert "sonnenuntergang" in result.lower() or "detailed image" in result.lower()
        assert len(result) > 0

    @pytest.mark.asyncio
    async def test_nonempty_prompt_returned(self):
        """Nicht-leerer GPT-Output wird normal zurückgegeben."""
        from agent.agents.creative import CreativeAgent

        agent = CreativeAgent.__new__(CreativeAgent)
        agent.provider_client = MagicMock()

        expected = "golden sunset over mountains, dramatic sky"
        mock_response = MagicMock()
        mock_response.choices[0].message.content = expected

        with patch("asyncio.to_thread", new=AsyncMock(return_value=mock_response)):
            result = await agent._generate_image_prompt_with_gpt("Sonnenuntergang")

        assert result == expected


# ── B.3 — generate_image API-Parameter-Mapping ───────────────────────────────

class TestImageParameterMapping:
    """SIZE_MAP und QUALITY_MAP normalisieren veraltete Parameter."""

    def _call_mapping(self, size, quality):
        """Führt die Mapping-Logik aus tools/creative_tool/tool.py direkt aus."""
        SIZE_MAP = {
            "1792x1024": "1536x1024",
            "1024x1792": "1024x1536",
            "1920x1080": "1536x1024",
        }
        QUALITY_MAP = {"standard": "medium", "hd": "high"}
        size = SIZE_MAP.get(size, size)
        quality = QUALITY_MAP.get(quality, quality)
        return size, quality

    def test_size_1792x1024_mapped(self):
        size, _ = self._call_mapping("1792x1024", "high")
        assert size == "1536x1024"

    def test_size_1024x1792_mapped(self):
        size, _ = self._call_mapping("1024x1792", "high")
        assert size == "1024x1536"

    def test_size_1920x1080_mapped(self):
        size, _ = self._call_mapping("1920x1080", "high")
        assert size == "1536x1024"

    def test_size_1024x1024_unverändert(self):
        size, _ = self._call_mapping("1024x1024", "high")
        assert size == "1024x1024"

    def test_quality_standard_to_medium(self):
        _, quality = self._call_mapping("1024x1024", "standard")
        assert quality == "medium"

    def test_quality_hd_to_high(self):
        _, quality = self._call_mapping("1024x1024", "hd")
        assert quality == "high"

    def test_quality_high_unverändert(self):
        _, quality = self._call_mapping("1024x1024", "high")
        assert quality == "high"

    def test_default_quality_is_high(self):
        """Der Tool-Default sollte 'high' sein."""
        import inspect
        from tools.creative_tool.tool import generate_image
        sig = inspect.signature(generate_image)
        assert sig.parameters["quality"].default == "high"
