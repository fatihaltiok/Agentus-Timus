# tools/debug_tool/tool.py
import logging
import asyncio

# V2 Tool Registry
from tools.tool_registry_v2 import tool, ToolParameter as P, ToolCategory as C

from tools.shared_context import inception_client

log = logging.getLogger(__name__)

@tool(
    name="test_inception_api",
    description="Sendet einen Prompt direkt an die Inception API und gibt die rohe, ungefilterte Antwort zurueck. Dies ist ein reines Debug-Tool.",
    parameters=[
        P("prompt", "string", "Der Prompt, der an die Inception API gesendet wird", required=True),
    ],
    capabilities=["debug", "api"],
    category=C.DEBUG
)
async def test_inception_api(prompt: str) -> dict:
    """
    Sendet einen Prompt direkt an die Inception API und gibt die rohe, ungefilterte Antwort zurück.
    Dies ist ein reines Debug-Tool.
    """
    if not inception_client:
        raise Exception("Inception Client ist nicht konfiguriert oder wurde im Server nicht initialisiert.")

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
        return {
            "status": "success",
            "message": "Rohe Antwort von Inception API erhalten.",
            "raw_response": response_dict
        }

    except Exception as e:
        log.error(f"DEBUG-TOOL: Fehler bei Inception API-Aufruf: {e}", exc_info=True)
        raise Exception(f"Inception API Fehler: {e}")
