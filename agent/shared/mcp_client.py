"""Einheitlicher JSON-RPC Client fuer MCP-Server."""

import os
import logging
import httpx

log = logging.getLogger("MCPClient")


class MCPClient:
    """Einheitlicher JSON-RPC Client fuer MCP-Server.

    Ersetzt die 4 duplizierten Varianten in:
    - timus_consolidated.py  BaseAgent._call_tool
    - visual_agent.py        call_tool
    - visual_nemotron_agent_v4.py  MCPToolClient
    - developer_agent_v2.py  call_tool (sync)
    """

    def __init__(self, url: str | None = None, timeout: float = 300.0):
        self.url = url or os.getenv("MCP_URL", "http://127.0.0.1:5000")
        self.http_client = httpx.AsyncClient(timeout=timeout)

    async def call(self, method: str, params: dict | None = None) -> dict:
        """Async JSON-RPC Call zum MCP-Server."""
        params = params or {}
        try:
            resp = await self.http_client.post(
                self.url,
                json={
                    "jsonrpc": "2.0",
                    "method": method,
                    "params": params,
                    "id": os.urandom(4).hex(),
                },
            )
            data = resp.json()
            if "result" in data:
                return data["result"]
            if "error" in data:
                error = data["error"]
                msg = error.get("message", str(error)) if isinstance(error, dict) else str(error)
                return {"error": msg}
            return {"error": "Invalid response"}
        except Exception as e:
            return {"error": str(e)}

    def call_sync(self, method: str, params: dict | None = None, timeout: int = 300) -> dict:
        """Sync JSON-RPC Call (fuer developer_agent_v2 u.a.)."""
        import requests as _requests

        params = params or {}
        payload = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params,
            "id": os.urandom(4).hex(),
        }
        try:
            resp = _requests.post(self.url, json=payload, timeout=timeout)
            resp.raise_for_status()
            data = resp.json()
            if "error" in data:
                return {"error": data.get("error", "Unbekannter Tool-Fehler")}
            return data.get("result", {})
        except Exception as e:
            return {"error": f"RPC/HTTP-Fehler: {e}"}

    async def close(self):
        await self.http_client.aclose()
