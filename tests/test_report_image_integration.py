from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools.deep_research.image_collector import ImageResult
from tools.deep_research.tool import _merge_report_images


def test_merge_report_images_appends_creative_images():
    base = [
        ImageResult(
            local_path="/tmp/base.png",
            caption="Basisbild",
            section_title="Einleitung",
            source="web",
        )
    ]

    merged = _merge_report_images(
        base,
        image_paths=["/tmp/creative.png"],
        image_captions=["Creative Hero"],
        image_sections=["Fazit"],
    )

    assert len(merged) == 2
    assert merged[1].local_path == "/tmp/creative.png"
    assert merged[1].caption == "Creative Hero"
    assert merged[1].section_title == "Fazit"
    assert merged[1].source == "creative"


def test_merge_report_images_uses_defaults_for_missing_caption_and_section():
    merged = _merge_report_images(
        [],
        image_paths=["/tmp/creative.png"],
        image_captions=[],
        image_sections=[],
    )

    assert len(merged) == 1
    assert merged[0].caption == "Visual 1"
    assert merged[0].section_title == "Visual 1"


def test_merge_report_images_skips_empty_paths():
    merged = _merge_report_images(
        [],
        image_paths=["", "   ", "/tmp/final.png"],
    )

    assert len(merged) == 1
    assert merged[0].local_path == "/tmp/final.png"
