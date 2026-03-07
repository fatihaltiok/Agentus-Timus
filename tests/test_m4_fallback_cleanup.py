from tools.deep_research.image_collector import _extract_generated_image_path
from tools.report_generator.tool import _primary_saved_path


def test_image_collector_prefers_artifacts_path():
    result = {
        "artifacts": [{"type": "image", "path": "/tmp/from-artifacts.png"}],
        "metadata": {"saved_as": "results/from-metadata.png"},
        "saved_as": "results/from-legacy.png",
    }

    assert _extract_generated_image_path(result) == "/tmp/from-artifacts.png"


def test_image_collector_falls_back_to_metadata_then_legacy():
    metadata_result = {
        "metadata": {"saved_as": "results/from-metadata.png"},
        "saved_as": "results/from-legacy.png",
    }
    legacy_result = {
        "saved_as": "results/from-legacy.png",
    }

    assert _extract_generated_image_path(metadata_result) == "results/from-metadata.png"
    assert _extract_generated_image_path(legacy_result) == "results/from-legacy.png"


def test_report_generator_prefers_artifacts_path():
    save_result = {
        "artifacts": [{"type": "pdf", "path": "/tmp/report.pdf"}],
        "metadata": {"filepath": "/tmp/meta.pdf"},
        "filepath": "/tmp/legacy.pdf",
    }

    assert _primary_saved_path(save_result) == "/tmp/report.pdf"


def test_report_generator_falls_back_to_metadata_then_legacy():
    metadata_result = {
        "metadata": {"filepath": "/tmp/meta.pdf"},
        "filepath": "/tmp/legacy.pdf",
    }
    legacy_result = {"filepath": "/tmp/legacy.pdf"}

    assert _primary_saved_path(metadata_result) == "/tmp/meta.pdf"
    assert _primary_saved_path(legacy_result) == "/tmp/legacy.pdf"

