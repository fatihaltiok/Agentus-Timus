"""
Browser Controller Tool - MCP Integration

Registriert HybridBrowserController als MCP-Tool.
"""

import logging
from typing import Union, Dict, Any

from tools.tool_registry_v2 import tool, ToolParameter as P, ToolCategory as C

from .controller import HybridBrowserController, ActionResult

log = logging.getLogger("browser_controller_tool")

# Globale Controller-Instanz (Singleton)
_controller: HybridBrowserController = None


async def get_controller() -> HybridBrowserController:
    """Lazy-initialisierter Controller."""
    global _controller
    if _controller is None:
        _controller = HybridBrowserController(headless=False)
        await _controller.initialize()
    return _controller


@tool(
    name="hybrid_browser_navigate",
    description="Navigiert zu URL mit DOM-First Browser Controller.",
    parameters=[
        P("url", "string", "Ziel-URL", required=True),
        P("wait_for_load", "boolean", "Auf Page-Load warten", required=False, default=True),
    ],
    capabilities=["browser", "dom"],
    category=C.BROWSER
)
async def hybrid_browser_navigate(url: str, wait_for_load: bool = True) -> dict:
    """
    Navigiert zu URL mit DOM-First Browser Controller.

    Args:
        url: Ziel-URL
        wait_for_load: Auf Page-Load warten

    Returns:
        dict mit ActionResult
    """
    try:
        controller = await get_controller()
        result = await controller.navigate(url, wait_for_load)

        return result.to_dict()

    except Exception as e:
        log.error(f"Navigation fehlgeschlagen: {e}", exc_info=True)
        raise Exception(f"Navigation fehlgeschlagen: {e}")


@tool(
    name="hybrid_browser_action",
    description="Führt Browser-Aktion aus (DOM-First!).",
    parameters=[
        P("action", "object", "Action-Dict mit type, target, expected_state", required=True),
    ],
    capabilities=["browser", "dom"],
    category=C.BROWSER
)
async def hybrid_browser_action(action: Dict[str, Any]) -> dict:
    """
    Führt Browser-Aktion aus (DOM-First!).

    Args:
        action: Action-Dict mit type, target, expected_state

    Beispiel:
        {
            "type": "click",
            "target": {
                "text": "Login",
                "selector": "#login-btn"  # Optional
            },
            "expected_state": {
                "url_contains": "dashboard"
            }
        }

    Returns:
        dict mit ActionResult
    """
    try:
        controller = await get_controller()
        result = await controller.execute_action(action)

        return result.to_dict()

    except Exception as e:
        log.error(f"Aktion fehlgeschlagen: {e}", exc_info=True)
        raise Exception(f"Aktion fehlgeschlagen: {e}")


@tool(
    name="hybrid_browser_stats",
    description="Gibt Browser-Controller Statistiken zurück.",
    parameters=[],
    capabilities=["browser", "dom"],
    category=C.BROWSER
)
async def hybrid_browser_stats() -> dict:
    """
    Gibt Browser-Controller Statistiken zurück.

    Returns:
        dict mit Stats
    """
    try:
        controller = await get_controller()
        stats = controller.get_stats()

        return stats

    except Exception as e:
        raise Exception(f"Stats-Abruf fehlgeschlagen: {e}")


@tool(
    name="hybrid_browser_cleanup",
    description="Räumt Browser-Controller auf.",
    parameters=[],
    capabilities=["browser", "dom"],
    category=C.BROWSER
)
async def hybrid_browser_cleanup() -> dict:
    """
    Räumt Browser-Controller auf.

    Returns:
        dict mit Cleanup-Status
    """
    try:
        global _controller
        if _controller:
            await _controller.cleanup()
            _controller = None

        return {"message": "Cleanup erfolgreich"}

    except Exception as e:
        raise Exception(f"Cleanup fehlgeschlagen: {e}")
