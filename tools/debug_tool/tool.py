# tools/debug_tool/tool.py
import logging
import asyncio
from typing import Union, Dict, Any

from jsonrpcserver import method, Success, Error
from tools.shared_context import inception_client
from tools.universal_tool_caller import register_tool

log = logging.getLogger(__name__)

@method
async def test_inception_api(prompt: str) -> Union[Success, Error]:
    """
    Sendet einen Prompt direkt an die Inception API und gibt die rohe, ungefilterte Antwort zurück.
    Dies ist ein reines Debug-Tool.
    """
    if not inception_client:
        return Error(code=-32090, message="Inception Client ist nicht konfiguriert oder wurde im Server nicht initialisiert.")
    
    log.info(f"DEBUG-TOOL: Sende Test-Prompt an Inception: '{prompt[:100]}...'")
    try:
        # Wir wollen die rohe Antwort sehen, also fangen wir das ganze Objekt ab
        raw_response = await asyncio.to_thread(
            inception_client.chat.completions.create,
            model="mercury-coder",
            messages=[{"role": "user", "content": prompt}]
        )
        
        # Konvertiere das Pydantic-Modell in ein Dictionary für die JSON-Ausgabe
        response_dict = raw_response.model_dump()
        
        log.info(f"DEBUG-TOOL: Rohe Antwort von Inception erhalten.")
        return Success({
            "status": "success",
            "message": "Rohe Antwort von Inception API erhalten.",
            "raw_response": response_dict
        })
        
    except Exception as e:
        log.error(f"DEBUG-TOOL: Fehler bei Inception API-Aufruf: {e}", exc_info=True)
        return Error(code=-32091, message=f"Inception API Fehler: {e}")

register_tool("test_inception_api", test_inception_api)
log.info("✅ Debug-Tool 'test_inception_api' registriert.")