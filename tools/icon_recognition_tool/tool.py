# tools/icon_recognition_tool/tool.py (FINAL, mit korrektem Import)

import logging
import asyncio
# import pyautogui # Nicht hier benötigt, da es in _find_icon_sync verwendet wird
# import cv2 # Nicht hier benötigt, da es in _find_icon_sync verwendet wird
# import numpy as np # Nicht hier benötigt, da es in _find_icon_sync verwendet wird
from typing import Union, Optional, Dict # <--- HIER IST DIE KORREKTUR
from pathlib import Path

from jsonrpcserver import method, Success, Error
from tools.universal_tool_caller import register_tool


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

@method
async def find_icon_by_template(template_name: str, threshold: float = 0.8) -> Union[Success, Error]:
    try:
        location = await asyncio.to_thread(_find_icon_sync, template_name, threshold)
        if location:
            return Success({"status": "icon_found", "location": location})
        else:
            return Success({"status": "icon_not_found",
                            "message": f"Icon '{template_name}' nicht sicher gefunden.",
                            "threshold": threshold})
    except FileNotFoundError as e:
        return Error(code=-32070, message=str(e))
    except Exception as e:
        log.error(f"Fehler beim Template Matching: {e}", exc_info=True)
        return Error(code=-32071, message=f"Unerwarteter Fehler: {e}")

register_tool("find_icon_by_template", find_icon_by_template)
log.info("✅ Icon Recognition Tool registriert.")