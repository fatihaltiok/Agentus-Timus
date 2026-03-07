import json

import pytest
from jsonrpcserver import async_dispatch

from tools.tool_registry_v2 import registry_v2, tool, ToolParameter as P, ToolCategory as C


@tool(
    name="test_envelope_plain_dict",
    description="Testtool fuer Envelope-Normalisierung",
    parameters=[],
    capabilities=["test_envelope"],
    category=C.SYSTEM,
)
async def test_envelope_plain_dict() -> dict:
    return {
        "success": True,
        "message": "Datei gespeichert",
        "filepath": "/tmp/report.pdf",
        "filename": "report.pdf",
    }


@tool(
    name="test_envelope_idempotent",
    description="Testtool fuer idempotente Envelope-Normalisierung",
    parameters=[],
    capabilities=["test_envelope"],
    category=C.SYSTEM,
)
async def test_envelope_idempotent() -> dict:
    return {
        "status": "success",
        "data": {"ok": True},
        "summary": "Bereits normalisiert",
        "artifacts": [{"type": "pdf", "path": "/tmp/already.pdf", "source": "custom"}],
        "metadata": {"session_id": "abc123"},
        "error": "",
    }


@pytest.mark.asyncio
async def test_jsonrpc_wrapper_normalizes_plain_dict_results():
    request = json.dumps(
        {"jsonrpc": "2.0", "method": "test_envelope_plain_dict", "params": {}, "id": "1"}
    )
    response = json.loads(await async_dispatch(request))
    result = response["result"]

    assert result["status"] == "success"
    assert result["summary"] == "Datei gespeichert"
    assert result["metadata"]["filepath"] == "/tmp/report.pdf"
    assert result["artifacts"][0]["path"] == "/tmp/report.pdf"
    assert result["artifacts"][0]["type"] == "pdf"
    assert result["data"]["filename"] == "report.pdf"
    assert result["filename"] == "report.pdf"


@pytest.mark.asyncio
async def test_jsonrpc_wrapper_logs_wrapper_inference(caplog):
    request = json.dumps(
        {"jsonrpc": "2.0", "method": "test_envelope_plain_dict", "params": {}, "id": "1b"}
    )
    with caplog.at_level("WARNING", logger="ToolRegistryV2"):
        response = json.loads(await async_dispatch(request))

    result = response["result"]
    assert result["artifacts"][0]["path"] == "/tmp/report.pdf"
    assert "Wrapper-Artefakt-Inferenz" in caplog.text


@pytest.mark.asyncio
async def test_jsonrpc_wrapper_keeps_normalized_results_stable():
    request = json.dumps(
        {"jsonrpc": "2.0", "method": "test_envelope_idempotent", "params": {}, "id": "2"}
    )
    response = json.loads(await async_dispatch(request))
    result = response["result"]

    assert result["status"] == "success"
    assert result["summary"] == "Bereits normalisiert"
    assert result["artifacts"][0]["path"] == "/tmp/already.pdf"
    assert result["artifacts"][0]["source"] == "custom"
    assert result["metadata"]["session_id"] == "abc123"


@pytest.mark.asyncio
async def test_execute_can_opt_in_to_normalized_result():
    raw = await registry_v2.execute("test_envelope_plain_dict")
    normalized = await registry_v2.execute("test_envelope_plain_dict", normalize=True)

    assert "data" not in raw
    assert normalized["status"] == "success"
    assert normalized["artifacts"][0]["path"] == "/tmp/report.pdf"
