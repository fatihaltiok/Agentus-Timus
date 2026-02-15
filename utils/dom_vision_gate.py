# utils/dom_vision_gate.py
"""
Entscheidungslogik: DOM-first, Vision-Fallback fuer UI-Aktionen.
"""
import logging
from typing import Dict, Any, Tuple, Callable, Awaitable, Optional

log = logging.getLogger("dom_vision_gate")


async def try_dom_first(
    action: Dict[str, Any],
    dom_fn: Callable[[Dict], Awaitable[Any]],
    vision_fn: Callable[[Dict], Awaitable[Any]],
    has_dom_access: Optional[Callable[[], Awaitable[bool]]] = None,
) -> Tuple[Any, str]:
    """
    Versucht DOM-basierte Aktion zuerst; faellt auf Vision zurueck wenn DOM scheitert.

    Args:
        action: Die auszufuehrende Aktion (mit Beschreibung, Selector, etc.)
        dom_fn: async (action) -> result via DOM/Playwright
        vision_fn: async (action) -> result via Vision/Koordinaten
        has_dom_access: optionaler Check ob DOM ueberhaupt verfuegbar ist

    Returns:
        (result, method_used)  wobei method_used "dom" oder "vision" ist
    """
    action_name = action.get("action", "unknown")

    # Pruefen ob DOM verfuegbar
    dom_available = True
    if has_dom_access:
        try:
            dom_available = await has_dom_access()
        except Exception:
            dom_available = False

    if dom_available:
        try:
            result = await dom_fn(action)
            if _is_success(result):
                log.info(f"[gate] DOM-Erfolg fuer '{action_name}'")
                return result, "dom"
            else:
                log.info(f"[gate] DOM fehlgeschlagen fuer '{action_name}', Fallback auf Vision")
        except Exception as e:
            log.warning(f"[gate] DOM-Exception: {e}, Fallback auf Vision")
    else:
        log.info(f"[gate] Kein DOM-Zugang, nutze Vision direkt fuer '{action_name}'")

    # Vision-Fallback
    try:
        result = await vision_fn(action)
        if _is_success(result):
            log.info(f"[gate] Vision-Erfolg fuer '{action_name}'")
        else:
            log.warning(f"[gate] Vision auch fehlgeschlagen fuer '{action_name}'")
        return result, "vision"
    except Exception as e:
        log.error(f"[gate] Vision-Exception: {e}")
        return {"error": str(e)}, "vision"


def _is_success(result: Any) -> bool:
    """Prueft ob ein Ergebnis Erfolg signalisiert."""
    if isinstance(result, dict):
        if result.get("error"):
            return False
        if result.get("success") is False:
            return False
    if isinstance(result, tuple):
        # DesktopController.execute_action gibt (done, error) zurueck
        return result[1] is None
    return True
