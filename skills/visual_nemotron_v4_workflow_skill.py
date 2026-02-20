import json
import logging
from typing import Any, Dict, List, Optional

# Tools import – bitte die tatsächlichen Module anpassen, falls nötig
from tools import (
    open_url,
    capture_screen_before_action,
    dismiss_overlays,
    analyze_screen_verified,
    click_by_text,
    type_text,
    verify_action_result,
    save_annotated_screenshot,
    save_screenshot,
    get_text,
    verify_screen_condition,
    wait_until_stable,
)

# Logger konfigurieren
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Metadata
skill_name = "visual_nemotron_v4_workflow"
description = "Workflow-Skill für Visual Nemotron v4: Öffnen, Überprüfen, Interagieren, Verifizieren, Aufräumen."
version = "1.0"
author = "Timus (auto-generated)"


def retry_action(
    action_func,
    max_attempts: int = 2,
    *args,
    **kwargs,
) -> Dict[str, Any]:
    """
    Hilfsfunktion zum Ausführen einer kritischen Aktion mit maximal zwei Versuchen.
    Gibt ein Ergebnisdict zurück, das den Erfolg, die Nachricht und ggf. Screenshots enthält.
    """
    result = {
        "name": action_func.__name__,
        "attempt_count": 0,
        "success": False,
        "message": "",
        "screenshot_path": None,
        "ocr_excerpt": None,
    }
    for attempt in range(1, max_attempts + 1):
        result["attempt_count"] = attempt
        try:
            logger.info(f"Versuch {attempt}/{max_attempts}: {action_func.__name__}")
            response = action_func(*args, **kwargs)

            # Defensive Prüfung auf Fehlermeldungen in der Rückgabe
            if response is None or (isinstance(response, dict) and "error" in response):
                raise RuntimeError(f"Tool {action_func.__name__} failed: {response}")

            result["success"] = True
            result["message"] = f"{action_func.__name__} erfolgreich."
            return result
        except Exception as exc:
            logger.exception(f"Fehler bei {action_func.__name__}: {exc}")
            result["message"] = str(exc)
            # Screenshot nur bei ersten Fehlversuch speichern
            if attempt == 1:
                screenshot_path = capture_screen_before_action()
                result["screenshot_path"] = screenshot_path
    return result


def run(params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Führt den 5‑Phasen‑Workflow aus, um eine Webseite zu bedienen.
    """
    # Standardwerte setzen
    url: str = params.get("url")
    actions: List[Dict[str, Any]] = params.get("actions", [])
    wait_for_load_seconds: int = params.get("wait_for_load_seconds", 5)
    save_debug_screenshots: bool = params.get("save_debug_screenshots", True)

    # Ergebnisinitialisierung
    result: Dict[str, Any] = {
        "success": True,
        "steps": [],
        "errors": [],
    }

    # ---------- Phase 1: Init ----------
    if not url:
        error_msg = "Parameter 'url' ist erforderlich."
        logger.error(error_msg)
        result["success"] = False
        result["errors"].append(error_msg)
        return result

    logger.info("Phase 1: Initialisierung")
    # URL öffnen
    open_result = retry_action(open_url, url=url)
    result["steps"].append(open_result)
    if not open_result["success"]:
        result["success"] = False
        result["errors"].append("Konnte die URL nicht öffnen.")
        return result

    # Warten bis die Seite stabil ist
    stable_result = retry_action(wait_until_stable, timeout=wait_for_load_seconds)
    result["steps"].append(stable_result)
    if not stable_result["success"]:
        result["success"] = False
        result["errors"].append("Seite ist nicht stabil.")
        return result

    # Screenshot vor Aktionen
    pre_action_screenshot = capture_screen_before_action()
    result["steps"].append(
        {
            "name": "capture_screen_before_action",
            "attempt_count": 1,
            "success": True,
            "message": "Screenshot vor Aktionen erstellt.",
            "screenshot_path": pre_action_screenshot,
        }
    )

    # ---------- Phase 2: Cleanup/Consent ----------
    logger.info("Phase 2: Overlays entfernen")
    for attempt in range(1, 3):
        try:
            dismiss_result = dismiss_overlays(max_secs=8)
            if dismiss_result is None or (isinstance(dismiss_result, dict) and "error" in dismiss_result):
                raise RuntimeError(fdismissdismiss_overlays fehlgeschlagen: {dismiss_result}")
            logger.info(f"Overlays entfernt (Versuch {attempt})")
            break
        except Exception as exc:
            logger.exception(f"Fehler beim Entfernen von Overlays: {exc}")
            if attempt == 2:
                result["success"] = False
                result["errors"].append("Konnte Overlays nicht entfernen.")
                return result

    # Re‑Analyse nach Overlay‑Entfernung
    logger.info("Phase 2: Re‑Analyse der Seite")
    analysis_result = retry_action(
        analyze_screen_verified,
        verify_with_ocr=True,
        min_confidence=0.6,
    )
    result["steps"].append(analysis_result)

    # ---------- Phase 3: Analyse ----------
    logger.info("Phase 3: Analyse der Seite")
    if not analysis_result["success"]:
        result["success"] = False
        result["errors"].append("Analyse der Seite fehlgeschlagen.")
        return result

    # Hier könnte man weitere Extraktionen vornehmen, z. B. Buttons/Textfelder.
    # Für diese Implementierung gehen wir davon aus, dass die Analyse bereits die relevanten Infos liefert.
    # Falls nichts gefunden wurde, wird ein Fehler protokolliert.
    if not analysis_result.get("data"):
        error_msg = "Analyse ergab keine Daten."
        logger.error(error_msg)
        result["success"] = False
        result["errors"].append(error_msg)
        return result

    # ---------- Phase 4: Interaction ----------
    logger.info("Phase 4: Interaktion mit der Seite")
    for idx, act in enumerate(actions, start=1):
        act_type = act.get("type")
        logger.info(f"Aktion {idx}: {act_type}")

        # Screenshot vor jeder Aktion
        pre_act_scr = capture_screen_before_action()

        # Aktion ausführen
        if act_type == "click":
            by_text = act.get("by_text")
            if not by_text:
                error_msg = f"Aktion {idx} (click) fehlt 'by_text'."
                logger.error(error_msg)
                result["errors"].append(error_msg)
                continue
            action_result = retry_action(click_by_text, by_text=by_text)
        elif act_type == "type":
            text = act.get("text")
            field_hint = act.get("field_hint")
            if not text or not field_hint:
                error_msg = f"Aktion {idx} (type) fehlt 'text' oder 'field_hint'."
                logger.error(error_msg)
                result["errors"].append(error_msg)
                continue
            action_result = retry_action(type_text, field_hint=field_hint, text=text)
        else:
            error_msg = f"Unbekannter Aktionstyp '{act_type}' bei Aktion {idx}."
            logger.error(error_msg)
            result["errors"].append(error_msg)
            continue

        action_result["screenshot_path"] = pre_act_scr
        result["steps"].append(action_result)

        # Ergebnis der Aktion verifizieren
        verify_result = retry_action(verify_action_result, timeout=6)
        verify_result["screenshot_path"] = capture_screen_before_action()
        result["steps"].append(verify_result)

        if not verify_result["success"]:
            # Einmaliger Retry
            logger.info(f"Retry für Aktion {idx} nach Verifizierung")
            retry_verify = retry_action(verify_action_result, timeout=6)
            retry_verify["screenshot_path"] = capture_screen_before_action()
            result["steps"].append(retry_verify)
            if not retry_verify["success"]:
                error_msg = f"Aktion {idx} ({act_type}) konnte nicht verifiziert werden."
                logger.error(error_msg)
                result["errors"].append(error_msg)

    # ---------- Phase 5: Verify & Teardown ----------
    logger.info("Phase 5: Endgültige Analyse und Aufräumen")
    final_analysis = retry_action(
        analyze_screen_verified,
        verify_with_ocr=True,
        min_confidence=0.6,
    )
    result["steps"].append(final_analysis)

    if final_analysis["success"]:
        result["success"] = True
        logger.info("Workflow erfolgreich abgeschlossen.")
    else:
        result["success"] = False
        result["errors"].append("Endgültige Analyse fehlgeschlagen.")

    # Debug‑Screenshots speichern, falls aktiviert
    if save_debug_screenshots:
        debug_path = save_annotated_screenshot()
        logger.info(f"Debug‑Screenshot gespeichert unter {debug_path}")

    return result


# ----------------------------------------------------------------------
# Beispiel‑Usage
# ----------------------------------------------------------------------
if __name__ == "__main__":
    test_params = {
        "url": "https://example.com",
        "actions": [
            {"type": "click", "by_text": "Login"},
            {"type": "type", "text": "me@example.com", "field_hint": "email"},
            {"type": "type", "text": "secret", "field_hint": "password"},
            {"type": "click", "by_text": "Submit"},
        ],
        "wait_for_load_seconds": 5,
        "save_debug_screenshots": True,
    }

    result = run(test_params)
    print(json.dumps(result, indent=2, ensure_ascii=False))