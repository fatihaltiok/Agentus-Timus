from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from tools.deep_research.image_collector import ImageCollector
from tools.deep_research.tool import _build_report_image_status


@pytest.mark.asyncio
async def test_image_collector_accepts_extensionless_direct_image_url(monkeypatch):
    async def fake_call_tool_internal(method: str, params: dict):
        assert method == "search_images"
        return [{"image_url": "https://cdn.example.test/image-proxy?id=123"}]

    async def fake_download(self, url: str):
        assert url == "https://cdn.example.test/image-proxy?id=123"
        return "/tmp/research-image.jpg"

    monkeypatch.setattr("tools.deep_research.image_collector.call_tool_internal", fake_call_tool_internal)
    monkeypatch.setattr(ImageCollector, "_download_image", fake_download)

    collector = ImageCollector()
    images = await collector.collect_images_for_sections(["Regeln"], "Balkonkraftwerk 2026", max_images=1)

    assert len(images) == 1
    assert images[0].local_path == "/tmp/research-image.jpg"
    assert images[0].source == "web"


@pytest.mark.asyncio
async def test_image_collector_records_generate_image_error(monkeypatch):
    captured_image_params = {}

    async def fake_call_tool_internal(method: str, params: dict):
        if method == "search_images":
            return []
        if method == "generate_image":
            captured_image_params.update(params)
            return {
                "status": "error",
                "error": "invalid image model",
                "error_code": "model_not_found",
                "error_type": "invalid_request_error",
            }
        raise AssertionError(method)

    monkeypatch.setattr("tools.deep_research.image_collector.call_tool_internal", fake_call_tool_internal)

    collector = ImageCollector()
    images = await collector.collect_images_for_sections(["Produkte"], "Balkonkraftwerk 2026", max_images=1)

    assert images == []
    assert captured_image_params["quality"] == "high"
    assert any(item["code"] == "search_images_no_direct_url" for item in collector.diagnostics)
    assert any(item["code"] == "generate_image_error" for item in collector.diagnostics)


def test_report_image_status_warns_when_optional_images_missing():
    status = _build_report_image_status(
        images_enabled=True,
        image_policy="optional",
        images_count=0,
        min_images=1,
        diagnostics=[{"code": "generate_image_error"}],
    )

    assert status["status"] == "missing_optional"
    assert status["warning"]
    assert status["images_required"] is False
    assert status["diagnostics"][0]["code"] == "generate_image_error"


def test_report_image_status_marks_required_images_missing():
    status = _build_report_image_status(
        images_enabled=True,
        image_policy="required",
        images_count=0,
        min_images=2,
        diagnostics=[],
    )

    assert status["status"] == "missing_required"
    assert status["images_required"] is True
    assert "0/2" in status["warning"]


@pytest.mark.asyncio
async def test_generate_image_normalizes_dalle3_quality(monkeypatch):
    import tools.creative_tool.tool as creative_tool

    captured = {}

    class _FakeImages:
        def generate(self, **kwargs):
            captured.update(kwargs)
            return SimpleNamespace(data=[SimpleNamespace(url="https://example.test/generated.png", b64_json=None)])

    monkeypatch.setenv("IMAGE_GENERATION_MODEL", "dall-e-3")
    monkeypatch.setattr(creative_tool, "openai_client", SimpleNamespace(images=_FakeImages()))

    result = await creative_tool.generate_image("Sachliche Illustration", size="1792x1024", quality="medium")

    assert result["status"] == "success"
    assert captured["model"] == "dall-e-3"
    assert captured["size"] == "1536x1024"
    assert captured["quality"] == "standard"


@pytest.mark.asyncio
async def test_generate_image_normalizes_gpt_image_quality_and_artifact(monkeypatch, tmp_path):
    import tools.creative_tool.tool as creative_tool

    captured = {}
    one_pixel_png_b64 = (
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9WlH0s0AAAAASUVORK5CYII="
    )

    class _FakeImages:
        def generate(self, **kwargs):
            captured.update(kwargs)
            return SimpleNamespace(data=[SimpleNamespace(url=None, b64_json=one_pixel_png_b64)])

    monkeypatch.setenv("IMAGE_GENERATION_MODEL", "gpt-image-2")
    monkeypatch.setattr(creative_tool, "openai_client", SimpleNamespace(images=_FakeImages()))
    fake_tool_file = tmp_path / "tools" / "creative_tool" / "tool.py"
    fake_tool_file.parent.mkdir(parents=True)
    fake_tool_file.write_text("# fake", encoding="utf-8")
    monkeypatch.setattr(creative_tool, "__file__", str(fake_tool_file))

    result = await creative_tool.generate_image("Sachliche Illustration", quality="hd")

    assert result["status"] == "success"
    assert captured["model"] == "gpt-image-2"
    assert captured["quality"] == "high"
    assert result["artifacts"]
    assert Path(result["artifacts"][0]["path"]).exists()


@pytest.mark.asyncio
async def test_generate_image_defaults_to_gpt_image_2_high_quality(monkeypatch):
    import tools.creative_tool.tool as creative_tool

    captured = {}

    class _FakeImages:
        def generate(self, **kwargs):
            captured.update(kwargs)
            return SimpleNamespace(data=[SimpleNamespace(url="https://example.test/generated.png", b64_json=None)])

    monkeypatch.delenv("IMAGE_GENERATION_MODEL", raising=False)
    monkeypatch.setattr(creative_tool, "openai_client", SimpleNamespace(images=_FakeImages()))

    result = await creative_tool.generate_image("Sachliche Illustration")

    assert result["status"] == "success"
    assert captured["model"] == "gpt-image-2"
    assert captured["quality"] == "high"
