from pathlib import Path

import pytest

from tools.save_results.tool import save_research_result


@pytest.mark.asyncio
async def test_save_research_result_returns_artifact(tmp_path, monkeypatch):
    monkeypatch.setattr("tools.save_results.tool.RESULTS_DIR", tmp_path)

    result = await save_research_result(
        title="Quarterly Report",
        content="Body",
        format="markdown",
        metadata={"topic": "finance"},
    )

    assert result["status"] == "success"
    assert "filepath" in result
    assert result["artifacts"]
    artifact = result["artifacts"][0]
    saved_path = Path(result["filepath"]).resolve()

    assert artifact["path"] == str(saved_path)
    assert artifact["label"] == Path(result["filename"]).name
    assert artifact["source"] == "save_results"
    assert artifact["origin"] == "tool"
    assert artifact["type"] == "document"
    assert saved_path.exists()

