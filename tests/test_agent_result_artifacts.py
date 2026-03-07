"""Tests für artifacts + Fallback-Policy im Delegationspfad."""

from unittest.mock import MagicMock, patch

from agent.agent_registry import AgentRegistry


def test_declared_artifacts_are_preferred_over_metadata_and_regex():
    raw = {
        "result": "PDF gespeichert unter /tmp/regex.pdf",
        "artifacts": [
            {
                "type": "pdf",
                "path": "/tmp/declared.pdf",
                "label": "Declared PDF",
                "source": "research",
            }
        ],
        "metadata": {"pdf_filepath": "/tmp/meta.pdf"},
    }

    with patch("agent.agent_registry.log.warning") as warn_mock:
        metadata, artifacts = AgentRegistry._build_result_metadata_and_artifacts(raw, "research")

    assert artifacts[0]["path"] == "/tmp/declared.pdf"
    assert metadata["pdf_filepath"] == "/tmp/meta.pdf"
    warn_mock.assert_not_called()


def test_metadata_artifacts_are_preferred_over_regex():
    raw = {
        "result": "PDF gespeichert unter /tmp/regex.pdf",
        "metadata": {"pdf_filepath": "/tmp/meta.pdf"},
    }

    with patch("agent.agent_registry.log.warning") as warn_mock:
        metadata, artifacts = AgentRegistry._build_result_metadata_and_artifacts(raw, "research")

    assert metadata["pdf_filepath"] == "/tmp/meta.pdf"
    assert artifacts[0]["path"] == "/tmp/meta.pdf"
    warn_mock.assert_called_once()
    assert "Metadata-Fallback" in warn_mock.call_args.args[0]


def test_regex_fallback_builds_artifacts_and_warns():
    raw = 'Final Answer: PDF gespeichert unter /tmp/fallback.pdf und Bild unter /tmp/cover.png'

    with patch("agent.agent_registry.log.warning") as warn_mock:
        metadata, artifacts = AgentRegistry._build_result_metadata_and_artifacts(raw, "research")

    assert metadata["pdf_filepath"] == "/tmp/fallback.pdf"
    assert any(item["path"] == "/tmp/fallback.pdf" for item in artifacts)
    assert any(item["origin"] == "regex" for item in artifacts)
    warn_mock.assert_called_once()


def test_declared_metadata_keeps_auxiliary_fields():
    raw = {
        "result": "ok",
        "metadata": {
            "pdf_filepath": "/tmp/report.pdf",
            "session_id": "sess-xyz-123",
            "word_count": 2345,
        },
    }

    metadata, artifacts = AgentRegistry._build_result_metadata_and_artifacts(raw, "research")

    assert metadata["session_id"] == "sess-xyz-123"
    assert metadata["word_count"] == 2345
    assert artifacts[0]["type"] == "pdf"


def test_auto_blackboard_write_persists_metadata_and_artifacts():
    bb = MagicMock()
    with patch("memory.agent_blackboard.get_blackboard", return_value=bb):
        key = AgentRegistry._auto_write_to_blackboard(
            "research",
            "task",
            "result",
            "success",
            metadata={"pdf_filepath": "/tmp/report.pdf"},
            artifacts=[{"type": "pdf", "path": "/tmp/report.pdf"}],
        )

    payload = bb.write.call_args.kwargs["value"]
    assert payload["metadata"]["pdf_filepath"] == "/tmp/report.pdf"
    assert payload["artifacts"][0]["path"] == "/tmp/report.pdf"
    assert key.startswith("delegation:research:")
