"""Screenshot-Capture Utilities fuer alle Timus-Agenten."""

import os
import io
import base64
import logging
from typing import Optional

log = logging.getLogger("screenshot")

# Lazy-load mss + PIL
_mss = None
_Image = None
_available: Optional[bool] = None


def _ensure_loaded() -> bool:
    global _mss, _Image, _available
    if _available is not None:
        return _available
    try:
        import mss as mss_mod
        from PIL import Image as pil_image
        _mss = mss_mod
        _Image = pil_image
        _available = True
    except ImportError:
        _available = False
    return _available


def capture_screenshot_base64(
    monitor_index: Optional[int] = None,
    max_size: tuple = (1280, 720),
    fmt: str = "JPEG",
    quality: int = 70,
) -> str:
    """Screenshot als Base64 mit konfigurierbarem Format.

    Args:
        monitor_index: Monitor-Index (None = aus ACTIVE_MONITOR env).
        max_size: Maximale Bildgroesse (Breite, Hoehe).
        fmt: Bildformat ("JPEG" oder "PNG").
        quality: JPEG-Qualitaet (nur bei fmt="JPEG").

    Returns:
        Base64-kodierter String oder "" bei Fehler.
    """
    if not _ensure_loaded():
        log.error("mss/PIL nicht verfuegbar")
        return ""

    if monitor_index is None:
        monitor_index = int(os.getenv("ACTIVE_MONITOR", "1"))

    try:
        with _mss.mss() as sct:
            monitors = sct.monitors
            if monitor_index < len(monitors):
                monitor = monitors[monitor_index]
            else:
                monitor = monitors[1] if len(monitors) > 1 else monitors[0]
            raw = sct.grab(monitor)
            img = _Image.frombytes("RGB", raw.size, raw.bgra, "raw", "BGRX")

        img.thumbnail(max_size)
        buf = io.BytesIO()
        save_kwargs = {"format": fmt}
        if fmt.upper() == "JPEG":
            save_kwargs["quality"] = quality
        img.save(buf, **save_kwargs)
        return base64.b64encode(buf.getvalue()).decode()
    except Exception as e:
        log.debug(f"Screenshot fehlgeschlagen: {e}")
        return ""


def capture_screenshot_image(monitor_index: Optional[int] = None):
    """Screenshot als PIL Image (fuer DesktopController u.a.).

    Returns:
        PIL.Image.Image oder None bei Fehler.
    """
    if not _ensure_loaded():
        return None

    if monitor_index is None:
        monitor_index = int(os.getenv("ACTIVE_MONITOR", "1"))

    try:
        with _mss.mss() as sct:
            monitors = sct.monitors
            if monitor_index < len(monitors):
                monitor = monitors[monitor_index]
            else:
                monitor = monitors[1] if len(monitors) > 1 else monitors[0]
            raw = sct.grab(monitor)
            return _Image.frombytes("RGB", raw.size, raw.bgra, "raw", "BGRX")
    except Exception as e:
        log.debug(f"Screenshot fehlgeschlagen: {e}")
        return None
