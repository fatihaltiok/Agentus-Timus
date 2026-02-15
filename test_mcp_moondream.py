#!/usr/bin/env python3
"""
Test Moondream Tools über MCP Server (JSON-RPC Integration)
"""
import httpx
import asyncio
import json

MCP_SERVER_URL = "http://127.0.0.1:5000"

async def call_mcp_method(method_name: str, params: dict = None):
    """Ruft eine JSON-RPC Methode auf dem MCP Server auf."""
    payload = {
        "jsonrpc": "2.0",
        "method": method_name,
        "params": params or {},
        "id": 1
    }
    
    async with httpx.AsyncClient(timeout=120.0) as client:
        response = await client.post(MCP_SERVER_URL, json=payload)
        return response.json()

async def test_mcp_moondream():
    print("=" * 60)
    print("TEST 1: describe_ui_with_moondream via MCP")
    print("=" * 60)
    
    try:
        result = await call_mcp_method("describe_ui_with_moondream")
        print(f"RPC Result: {json.dumps(result, indent=2)}")
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
    
    print("\n" + "=" * 60)
    print("TEST 2: find_element_with_moondream via MCP")
    print("=" * 60)
    
    try:
        result = await call_mcp_method("find_element_with_moondream", {"element_description": "submit button"})
        print(f"RPC Result: {json.dumps(result, indent=2)}")
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
    
    print("\n" + "=" * 60)
    print("TEST 3: scan_ui_elements via MCP (SOM Tool)")
    print("=" * 60)
    
    try:
        result = await call_mcp_method("scan_ui_elements", {"element_types": ["button", "text field"]})
        print(f"RPC Result: {json.dumps(result, indent=2)}")
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_mcp_moondream())
