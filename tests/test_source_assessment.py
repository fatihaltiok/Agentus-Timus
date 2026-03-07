from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools.deep_research.research_contracts import (
    SourceTier,
    SourceType,
    build_source_record_from_legacy,
    infer_source_type,
)


def test_infer_source_type_for_known_domains():
    assert infer_source_type("https://www.youtube.com/watch?v=abc") == SourceType.YOUTUBE
    assert infer_source_type("https://arxiv.org/abs/2501.00001") == SourceType.PAPER
    assert infer_source_type("https://github.com/QwenLM/Qwen3") == SourceType.REPOSITORY
    assert infer_source_type("https://api-docs.deepseek.com/news/news251201") == SourceType.VENDOR


def test_build_source_record_marks_official_youtube_with_transcript_as_a():
    source = build_source_record_from_legacy(
        source_id="yt1",
        url="https://www.youtube.com/watch?v=abc",
        title="Official Launch",
        declared_type="youtube",
        metadata={"is_official": True, "has_transcript": True},
    )
    assert source.source_type == SourceType.YOUTUBE
    assert source.tier == SourceTier.A


def test_build_source_record_marks_forum_like_sources_as_d():
    source = build_source_record_from_legacy(
        source_id="f1",
        url="https://reddit.com/r/LocalLLaMA",
        title="Forum Thread",
    )
    assert source.source_type == SourceType.UNKNOWN
    assert source.tier == SourceTier.D

