from tools.creative_tool.tool import _build_image_artifacts
from tools.deep_research.tool import _build_report_artifacts
from tools.document_creator.tool import _output_artifact


def test_build_image_artifacts_returns_absolute_file_reference():
    artifacts = _build_image_artifacts("results/generated.png")

    assert len(artifacts) == 1
    artifact = artifacts[0]
    assert artifact["type"] == "image"
    assert artifact["path"].endswith("/results/generated.png")
    assert artifact["label"] == "generated.png"
    assert artifact["source"] == "creative_tool"


def test_build_report_artifacts_deduplicates_and_types_paths():
    artifacts = _build_report_artifacts(
        "/tmp/report.md",
        "/tmp/report.md",
        "/tmp/summary.pdf",
    )

    assert len(artifacts) == 2
    assert artifacts[0]["type"] == "document"
    assert artifacts[1]["type"] == "pdf"
    assert artifacts[1]["path"] == "/tmp/summary.pdf"


def test_output_artifact_for_document_creator_uses_absolute_path(tmp_path):
    artifact = _output_artifact(tmp_path / "artifact.txt", "txt")

    assert artifact["type"] == "document"
    assert artifact["source"] == "document_creator"
    assert artifact["path"] == str((tmp_path / "artifact.txt").resolve())
    assert artifact["label"] == "artifact.txt"
