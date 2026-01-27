"""
planner_helpers.py – verbesserte interne Tool‑Aufrufe (jsonrpcserver ≥ 6)
=======================================================================

Nutzen:
    call_tool_internal() ruft ein bereits im MCP‑Server registriertes JSON‑RPC‑Tool **ohne HTTP**
    über jsonrpcserver.async_dispatch auf. Damit vermeidest du Netzwerklatenz im Planner‑/ReAct‑Loop.

Hauptpunkte:
    • funktioniert mit jsonrpcserver‑v6.x (und abwärts bis v4)
    • automatische Timeout‑Abbruch‑Logik
    • einheitliches Error‑Objekt {"error": <msg>} für alle Fehlerfälle
    • schlanke Codebasis – keine Erfolg/Error‑Wrapper nötig, reine Python‑Objekte werden zurückgegeben
"""
from __future__ import annotations

import asyncio
import json
import logging
import uuid
from typing import Any, Dict, Optional, Union

# jsonrpcserver >=6: async_dispatch liefert JSON-String zurück
try:
    from jsonrpcserver import async_dispatch
except ImportError:
    from jsonrpcserver import async_dispatch  # type: ignore

logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())

DEFAULT_TIMEOUT = 30  # Sekunden
ResultT = Union[Dict[str, Any], list, str]

# ---------------------------------------------------------------------------
async def call_tool_internal(
    method: str,
    params: Optional[Dict[str, Any]] = None,
    timeout: int = DEFAULT_TIMEOUT,
) -> ResultT:
    """Rufe ein Tool intern an (ohne HTTP‑Overhead).

    Args:
        method: RPC‑Methodenname (z. B. "open_url")
        params: Parameter‑Dict
        timeout: Max. Sekunden bis Abbruch (Default 30)

    Returns:
        Ergebnis des Tools (dict/list/str) oder {"error": <msg>}
    """
    rpc_request = {
        "jsonrpc": "2.0",
        "method": method,
        "params": params or {},
        "id": str(uuid.uuid4()),
    }
    request_str = json.dumps(rpc_request, ensure_ascii=False)

    try:
        # In jsonrpcserver 6.x gibt async_dispatch einen JSON-String zurück
        response_str = await asyncio.wait_for(
            async_dispatch(request_str), timeout=timeout
        )
        
        # Wenn response_str leer ist (Notification), gib Success zurück
        if not response_str:
            return {"result": "ok"}
        
        # Parse die JSON-Response
        try:
            response_dict = json.loads(response_str)
        except json.JSONDecodeError as e:
            logger.error(f"JSON-Decode-Fehler für {method}: {e}")
            return {"error": f"JSON-Decode-Fehler: {e}"}
        
        # Prüfe auf result oder error
        if "result" in response_dict:
            return response_dict["result"]
        elif "error" in response_dict:
            error_info = response_dict["error"]
            if isinstance(error_info, dict):
                return {"error": error_info.get("message", str(error_info))}
            else:
                return {"error": str(error_info)}
        else:
            logger.warning(f"Unerwartete Response-Struktur für {method}: {response_dict}")
            return response_dict

    except asyncio.TimeoutError:
        msg = f"Tool '{method}' Timeout nach {timeout}s"
        logger.error(msg)
        return {"error": msg}
    except Exception as exc:
        logger.exception("Interner Fehler bei Tool‑Call %s", method)
        return {"error": f"Interner Fehler: {exc}"}
