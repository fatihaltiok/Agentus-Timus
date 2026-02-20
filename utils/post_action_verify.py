# utils/post_action_verify.py
"""
Geteilte Post-Action-Verifikation fuer Visual-Agents.
Ablauf: capture_before → action → verify_after → error_check
"""
import logging
from typing import Callable, Awaitable, Dict, Any, Tuple

log = logging.getLogger("post_action_verify")


async def verified_action(
    capture_before_fn: Callable[[], Awaitable[Dict]],
    action_fn: Callable[[], Awaitable[Any]],
    verify_after_fn: Callable[..., Awaitable[Dict]],
    check_errors_fn: Callable[[], Awaitable[Dict]],
    action_name: str = "action",
    verify_timeout: float = 5.0,
) -> Tuple[Any, Dict]:
    """
    Fuehrt eine UI-Aktion mit Pflicht-Verifikation vorher/nachher aus.

    Args:
        capture_before_fn: async () -> dict  (ruft capture_screen_before_action auf)
        action_fn: async () -> result  (die eigentliche UI-Aktion)
        verify_after_fn: async (timeout) -> dict  (ruft verify_action_result auf)
        check_errors_fn: async () -> dict  (ruft check_for_errors auf)
        action_name: Name fuer Logging
        verify_timeout: Sekunden Wartezeit fuer Screen-Aenderung

    Returns:
        (action_result, verification_summary)
    """
    # 1. Screenshot vorher
    try:
        await capture_before_fn()
        log.debug(f"[verify] Before-Screenshot fuer '{action_name}' aufgenommen")
    except Exception as e:
        log.warning(f"[verify] capture_before fehlgeschlagen: {e}")

    # 2. Aktion ausfuehren
    action_result = await action_fn()

    # 3. Aenderung pruefen
    change_detected = False
    change_pct = 0.0
    debug_artifacts = None
    try:
        verify = await verify_after_fn(timeout=verify_timeout)
        if isinstance(verify, dict):
            change_detected = verify.get("change_detected", verify.get("success", False))
            change_pct = verify.get("change_percentage", 0.0)
            debug_artifacts = verify.get("debug_artifacts")
    except Exception as e:
        log.warning(f"[verify] verify_after fehlgeschlagen: {e}")

    # 4. Fehler pruefen
    has_error = False
    error_type = None
    try:
        error_check = await check_errors_fn()
        if isinstance(error_check, dict):
            has_error = error_check.get("error_detected", False)
            error_type = error_check.get("error_type")
    except Exception as e:
        log.warning(f"[verify] check_errors fehlgeschlagen: {e}")

    summary = {
        "action": action_name,
        "change_detected": change_detected,
        "change_percentage": change_pct,
        "error_detected": has_error,
        "error_type": error_type,
        "verified": change_detected and not has_error,
    }
    if debug_artifacts:
        summary["debug_artifacts"] = debug_artifacts

    if summary["verified"]:
        log.info(f"[verify] '{action_name}' VERIFIZIERT ({change_pct:.1f}% Aenderung)")
    else:
        log.warning(f"[verify] '{action_name}' NICHT verifiziert. change={change_detected}, error={has_error}")

    return action_result, summary
