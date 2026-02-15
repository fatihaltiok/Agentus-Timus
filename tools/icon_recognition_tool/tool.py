# tools/icon_recognition_tool/tool.py (FINAL, mit korrektem Import)

import logging
import asyncio
from typing import Optional, Dict
from pathlib import Path

from tools.tool_registry_v2 import tool, ToolParameter as P, ToolCategory as C


log = logging.getLogger(__name__)

# NEU: Cache für Templates
_TEMPLATE_CACHE: Dict[str, "numpy.ndarray"] = {}

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
ICON_LIBRARY_PATH = PROJECT_ROOT / "icons"

# NEU: einmalig Icon-Liste loggen
_available_icons_logged = False
def _log_available_icons_once():
    global _available_icons_logged
    if _available_icons_logged:
        return
    try:
        names = sorted([p.name for p in ICON_LIBRARY_PATH.glob("*.*")])
        log.info(f"Icon-Bibliothek ({ICON_LIBRARY_PATH}): {len(names)} Dateien: {names[:30]}{' ...' if len(names)>30 else ''}")
    except Exception as e:
        log.warning(f"Konnte Icons nicht auflisten: {e}")
    _available_icons_logged = True

def _resolve_icon_path(template_name: str) -> Path:
    # Akzeptiere Case-Varianten und .png/.jpg/.jpeg
    cand = [f"{template_name}.png", f"{template_name}.jpg", f"{template_name}.jpeg"]
    files = list(ICON_LIBRARY_PATH.iterdir())
    lower_to_real = {f.name.lower(): f for f in files}
    for c in cand:
        p = lower_to_real.get(c.lower())
        if p and p.exists():
            return p
    return ICON_LIBRARY_PATH / f"{template_name}.png"  # Fallback (für saubere Fehlermeldung)

def _load_template_cv2(path: Path):
    import cv2
    import numpy as np
    key = str(path.resolve()).lower()
    if key in _TEMPLATE_CACHE:
        return _TEMPLATE_CACHE[key]
    img = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if img is None:
        raise FileNotFoundError(f"Vorlage nicht lesbar: {path}")
    _TEMPLATE_CACHE[key] = img
    return img

def _find_icon_sync(template_name: str, threshold: float = 0.8) -> Optional[Dict[str, float]]:
    import pyautogui
    import cv2
    import numpy as np

    _log_available_icons_once()

    template_path = _resolve_icon_path(template_name)
    if not template_path.exists():
        log.error(f"Icon-Vorlage nicht in Bibliothek gefunden: {template_path}")
        raise FileNotFoundError(f"Vorlage '{template_name}' nicht gefunden ({template_path}).")

    template_img = _load_template_cv2(template_path)
    h, w = template_img.shape[:2]

    screenshot = pyautogui.screenshot()
    screenshot_cv = cv2.cvtColor(np.array(screenshot), cv2.COLOR_RGB2BGR)

    # Template Matching
    result = cv2.matchTemplate(screenshot_cv, template_img, cv2.TM_CCOEFF_NORMED)
    _, max_val, _, max_loc = cv2.minMaxLoc(result)
    log.info(f"Template Matching '{template_name}': match={max_val:.4f}, threshold={threshold}")

    if max_val >= threshold:
        center_x = max_loc[0] + w // 2
        center_y = max_loc[1] + h // 2
        return {"x": float(center_x), "y": float(center_y), "confidence": float(max_val)}

    return None

@tool(
    name="find_icon_by_template",
    description="Findet ein Icon auf dem Bildschirm mittels Template Matching.",
    parameters=[
        P("template_name", "string", "Name des Icon-Templates (ohne Dateiendung)", required=True),
        P("threshold", "number", "Schwellenwert für die Erkennung (0.0-1.0)", required=False, default=0.8),
    ],
    capabilities=["vision", "icon"],
    category=C.VISION
)
async def find_icon_by_template(template_name: str, threshold: float = 0.8) -> dict:
    try:
        location = await asyncio.to_thread(_find_icon_sync, template_name, threshold)
        if location:
            return {"status": "icon_found", "location": location}
        else:
            return {"status": "icon_not_found",
                            "message": f"Icon '{template_name}' nicht sicher gefunden.",
                            "threshold": threshold}
    except FileNotFoundError as e:
        raise Exception(str(e))
    except Exception as e:
        log.error(f"Fehler beim Template Matching: {e}", exc_info=True)
        return {"status": "error", "message": f"Unerwarteter Fehler: {e}"}
