# tools/planner/planner_helpers.py (FIXED VERSION v2.0)
"""
Verbesserte interne Tool-Aufrufe für jsonrpcserver >= 6.
Fixes:
1. Robustere Fehlerbehandlung
2. Besseres Logging
3. Unterstützung für verschiedene Response-Typen
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from typing import Any, Dict, Optional, Union, List

# Logger Setup
logger = logging.getLogger("planner_helpers")

# jsonrpcserver Import
try:
    from jsonrpcserver import async_dispatch
except ImportError:
    try:
        from jsonrpcserver import dispatch as async_dispatch  # type: ignore
    except ImportError:
        logger.error("jsonrpcserver nicht installiert!")
        async_dispatch = None  # type: ignore

# --- Konstanten ---
DEFAULT_TIMEOUT = 60  # Sekunden für normale Tools
LONG_TIMEOUT = 300    # Sekunden für langsame Tools (Deep Research, etc.)

# Tools die längere Timeouts brauchen
SLOW_TOOLS = {
    "start_deep_research",
    "generate_research_report",
    "extract_text_from_pdf",
    "search_web",
    "summarize_article"
}

# Typ-Alias für Rückgabewerte
ResultT = Union[Dict[str, Any], List[Any], str, int, float, bool, None]


async def call_tool_internal(
    method: str,
    params: Optional[Dict[str, Any]] = None,
    timeout: Optional[int] = None
) -> ResultT:
    """
    Ruft ein Tool intern an (ohne HTTP-Overhead) über den jsonrpcserver.
    
    Diese Funktion ist der Standardweg für die Kommunikation zwischen Tools.
    Sie behandelt verschiedene Response-Typen und Fehler robust.
    
    Args:
        method: Der Name der RPC-Methode (z.B. "search_web")
        params: Dictionary mit Parametern für die Methode
        timeout: Maximale Ausführungszeit in Sekunden (optional, auto-detect)
    
    Returns:
        Das Ergebnis des Tools oder ein Dictionary mit "error"-Schlüssel
    
    Examples:
        >>> result = await call_tool_internal("search_web", {"query": "AI"})
        >>> if isinstance(result, list):
        ...     print(f"Gefunden: {len(result)} Ergebnisse")
    """
    if async_dispatch is None:
        return {"error": "jsonrpcserver nicht verfügbar"}
    
    # Auto-detect Timeout
    if timeout is None:
        timeout = LONG_TIMEOUT if method in SLOW_TOOLS else DEFAULT_TIMEOUT
    
    # Request aufbauen
    request_id = str(uuid.uuid4())
    rpc_request = {
        "jsonrpc": "2.0",
        "method": method,
        "params": params or {},
        "id": request_id
    }
    
    request_str = json.dumps(rpc_request, ensure_ascii=False)
    
    logger.debug(f"🔧 Interner Call: {method}")
    logger.debug(f"   Params: {params}")
    
    try:
        # Dispatch mit Timeout
        response_str = await asyncio.wait_for(
            async_dispatch(request_str),
            timeout=timeout
        )
        
        # Notifications (Anfragen ohne 'id') geben None zurück
        if not response_str:
            logger.debug(f"   <- Notification OK für {method}")
            return {"status": "ok", "message": "Notification verarbeitet"}
        
        # Response parsen
        try:
            response_dict = json.loads(response_str)
        except json.JSONDecodeError as e:
            logger.error(f"JSON-Decode-Fehler bei {method}: {e}")
            logger.debug(f"   Raw response: {response_str[:200]}")
            return {"error": f"Ungültige JSON-Antwort: {e}"}
        
        # Erfolg
        if "result" in response_dict:
            result = response_dict["result"]
            
            # Log-Level basierend auf Ergebnis
            if isinstance(result, list):
                logger.debug(f"   <- OK: Liste mit {len(result)} Elementen")
            elif isinstance(result, dict):
                if "error" in result:
                    logger.warning(f"   <- Fehler in Result: {result.get('error')}")
                else:
                    logger.debug(f"   <- OK: Dict mit Keys {list(result.keys())[:5]}")
            else:
                logger.debug(f"   <- OK: {type(result).__name__}")
            
            return result
        
        # Fehler
        if "error" in response_dict:
            error_info = response_dict["error"]
            
            if isinstance(error_info, dict):
                error_message = error_info.get("message", str(error_info))
                error_code = error_info.get("code", -1)
            else:
                error_message = str(error_info)
                error_code = -1
            
            logger.warning(f"   <- Fehler [{error_code}]: {error_message}")
            return {"error": error_message, "code": error_code}
        
        # Unerwartete Struktur
        logger.warning(f"Unerwartete Response-Struktur von {method}")
        logger.debug(f"   Response: {response_dict}")
        return {
            "error": "Unerwartete Antwortstruktur",
            "raw_response": response_dict
        }
        
    except asyncio.TimeoutError:
        msg = f"Timeout nach {timeout}s für '{method}'"
        logger.error(msg)
        return {"error": msg}
        
    except asyncio.CancelledError:
        logger.warning(f"Task abgebrochen für '{method}'")
        return {"error": "Task wurde abgebrochen"}
        
    except Exception as e:
        logger.exception(f"Unerwarteter Fehler bei '{method}'")
        return {"error": f"Interner Fehler: {str(e)}"}


async def call_tools_parallel(
    calls: List[Dict[str, Any]],
    max_concurrent: int = 3
) -> List[ResultT]:
    """
    Führt mehrere Tool-Aufrufe parallel aus.
    
    Args:
        calls: Liste von Dictionaries mit "method" und optional "params"
        max_concurrent: Maximale Anzahl gleichzeitiger Aufrufe
    
    Returns:
        Liste der Ergebnisse in derselben Reihenfolge wie die Aufrufe
    
    Example:
        >>> calls = [
        ...     {"method": "search_web", "params": {"query": "AI"}},
        ...     {"method": "search_web", "params": {"query": "ML"}}
        ... ]
        >>> results = await call_tools_parallel(calls)
    """
    semaphore = asyncio.Semaphore(max_concurrent)
    
    async def limited_call(call: Dict[str, Any]) -> ResultT:
        async with semaphore:
            return await call_tool_internal(
                method=call.get("method", ""),
                params=call.get("params")
            )
    
    tasks = [limited_call(call) for call in calls]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    # Exceptions in Error-Dicts umwandeln
    processed_results: List[ResultT] = []
    for result in results:
        if isinstance(result, Exception):
            processed_results.append({"error": str(result)})
        else:
            processed_results.append(result)
    
    return processed_results


def is_error_result(result: ResultT) -> bool:
    """
    Prüft ob ein Ergebnis ein Fehler ist.
    
    Args:
        result: Das zu prüfende Ergebnis
    
    Returns:
        True wenn das Ergebnis einen Fehler enthält
    """
    if isinstance(result, dict):
        return "error" in result
    return False


def get_error_message(result: ResultT) -> Optional[str]:
    """
    Extrahiert die Fehlermeldung aus einem Ergebnis.
    
    Args:
        result: Das Ergebnis
    
    Returns:
        Die Fehlermeldung oder None
    """
    if isinstance(result, dict) and "error" in result:
        error = result["error"]
        if isinstance(error, str):
            return error
        if isinstance(error, dict):
            return error.get("message", str(error))
        return str(error)
    return None
