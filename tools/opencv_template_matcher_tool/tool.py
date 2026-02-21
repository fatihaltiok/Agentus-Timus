"""OpenCV based template matching fallback for UI element detection."""

from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import cv2
import mss
import numpy as np
from PIL import Image

from tools.tool_registry_v2 import tool, ToolCategory as C, ToolParameter as P

log = logging.getLogger("opencv_template_matcher")

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_TEMPLATE_DIR = Path(os.getenv("TEMPLATE_MATCHER_DIR", PROJECT_ROOT / "assets/templates"))
ACTIVE_MONITOR = int(os.getenv("ACTIVE_MONITOR", "1"))


def _load_image(image_path: str) -> np.ndarray:
    image = cv2.imread(image_path, cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError(f"Bild konnte nicht geladen werden: {image_path}")
    return image


def _capture_screenshot() -> Tuple[np.ndarray, Dict[str, int]]:
    with mss.mss() as sct:
        if ACTIVE_MONITOR < len(sct.monitors):
            monitor = sct.monitors[ACTIVE_MONITOR]
        else:
            monitor = sct.monitors[1] if len(sct.monitors) > 1 else sct.monitors[0]

        raw = sct.grab(monitor)
        image = Image.frombytes("RGB", raw.size, raw.bgra, "raw", "BGRX")
        arr = cv2.cvtColor(np.array(image), cv2.COLOR_RGB2BGR)
        return arr, {
            "left": int(monitor["left"]),
            "top": int(monitor["top"]),
            "width": int(monitor["width"]),
            "height": int(monitor["height"]),
        }


def _list_template_files(template_dir: Path, template_name: Optional[str]) -> List[Path]:
    if template_name:
        candidates = [
            template_dir / template_name,
            template_dir / f"{template_name}.png",
            template_dir / f"{template_name}.jpg",
            template_dir / f"{template_name}.jpeg",
        ]
        return [p for p in candidates if p.exists() and p.is_file()]

    patterns = ("*.png", "*.jpg", "*.jpeg", "*.webp", "*.bmp")
    files: List[Path] = []
    for pattern in patterns:
        files.extend(sorted(template_dir.glob(pattern)))
    return files


def _iter_scales(multi_scale: bool) -> Iterable[float]:
    if not multi_scale:
        return (1.0,)
    return (0.6, 0.75, 0.85, 1.0, 1.15, 1.3, 1.5, 1.6, 1.75, 2.0)


def _match_single_template(
    screenshot: np.ndarray,
    template_path: Path,
    threshold: float,
    multi_scale: bool,
    max_results: int,
    monitor: Optional[Dict[str, int]],
) -> List[Dict[str, Any]]:
    template_original = _load_image(str(template_path))
    screenshot_gray = cv2.cvtColor(screenshot, cv2.COLOR_BGR2GRAY)
    template_gray_base = cv2.cvtColor(template_original, cv2.COLOR_BGR2GRAY)

    h0, w0 = template_gray_base.shape[:2]
    matches: List[Dict[str, Any]] = []

    for scale in _iter_scales(multi_scale):
        scaled_w = max(4, int(round(w0 * scale)))
        scaled_h = max(4, int(round(h0 * scale)))
        if scaled_w > screenshot_gray.shape[1] or scaled_h > screenshot_gray.shape[0]:
            continue

        template_gray = cv2.resize(
            template_gray_base,
            (scaled_w, scaled_h),
            interpolation=cv2.INTER_AREA if scale < 1.0 else cv2.INTER_CUBIC,
        )
        result = cv2.matchTemplate(screenshot_gray, template_gray, cv2.TM_CCOEFF_NORMED)
        locations = np.where(result >= threshold)

        for pt_y, pt_x in zip(locations[0], locations[1]):
            score = float(result[pt_y, pt_x])
            x1 = int(pt_x)
            y1 = int(pt_y)
            x2 = int(pt_x + scaled_w)
            y2 = int(pt_y + scaled_h)
            center_x = int(round((x1 + x2) / 2))
            center_y = int(round((y1 + y2) / 2))

            global_x = center_x + int(monitor["left"]) if monitor else center_x
            global_y = center_y + int(monitor["top"]) if monitor else center_y

            matches.append(
                {
                    "template_name": template_path.stem,
                    "template_path": str(template_path),
                    "score": score,
                    "confidence": round(score, 4),
                    "scale": float(scale),
                    "x": global_x,
                    "y": global_y,
                    "click_x": global_x,
                    "click_y": global_y,
                    "center_x": global_x,
                    "center_y": global_y,
                    "bbox": {
                        "x1": x1 + (int(monitor["left"]) if monitor else 0),
                        "y1": y1 + (int(monitor["top"]) if monitor else 0),
                        "x2": x2 + (int(monitor["left"]) if monitor else 0),
                        "y2": y2 + (int(monitor["top"]) if monitor else 0),
                        "width": scaled_w,
                        "height": scaled_h,
                    },
                }
            )

    matches.sort(key=lambda item: item["score"], reverse=True)
    deduped: List[Dict[str, Any]] = []
    for match in matches:
        if len(deduped) >= max_results:
            break
        duplicate = False
        for existing in deduped:
            if abs(existing["x"] - match["x"]) <= 4 and abs(existing["y"] - match["y"]) <= 4:
                duplicate = True
                break
        if not duplicate:
            deduped.append(match)
    return deduped


def match_templates(
    image_path: Optional[str] = None,
    template_name: Optional[str] = None,
    template_path: Optional[str] = None,
    threshold: float = 0.82,
    multi_scale: bool = True,
    max_results: int = 5,
) -> Dict[str, Any]:
    """
    Matches one or more templates against a screenshot or image.
    """
    threshold = float(max(0.0, min(1.0, threshold)))
    max_results = max(1, int(max_results))

    monitor_info: Optional[Dict[str, int]] = None
    if image_path:
        screenshot = _load_image(image_path)
    else:
        screenshot, monitor_info = _capture_screenshot()

    if template_path:
        template_files = [Path(template_path).expanduser().resolve()]
    else:
        template_dir = DEFAULT_TEMPLATE_DIR.expanduser().resolve()
        template_files = _list_template_files(template_dir, template_name)

    if not template_files:
        return {
            "found": False,
            "count": 0,
            "matches": [],
            "message": "Keine Templates gefunden",
        }

    all_matches: List[Dict[str, Any]] = []
    for candidate in template_files:
        if not candidate.exists() or not candidate.is_file():
            continue
        try:
            all_matches.extend(
                _match_single_template(
                    screenshot=screenshot,
                    template_path=candidate,
                    threshold=threshold,
                    multi_scale=multi_scale,
                    max_results=max_results,
                    monitor=monitor_info,
                )
            )
        except Exception as exc:
            log.warning("Template-Match fehlgeschlagen fuer %s: %s", candidate, exc)

    all_matches.sort(key=lambda item: item["score"], reverse=True)
    if len(all_matches) > max_results:
        all_matches = all_matches[:max_results]

    if not all_matches:
        return {
            "found": False,
            "count": 0,
            "matches": [],
            "threshold": threshold,
            "multi_scale": multi_scale,
        }

    best = all_matches[0]
    return {
        "found": True,
        "count": len(all_matches),
        "template_name": best["template_name"],
        "x": best["x"],
        "y": best["y"],
        "click_x": best["click_x"],
        "click_y": best["click_y"],
        "center_x": best["center_x"],
        "center_y": best["center_y"],
        "confidence": best["confidence"],
        "score": best["score"],
        "bbox": best["bbox"],
        "matches": all_matches,
        "threshold": threshold,
        "multi_scale": multi_scale,
    }


@tool(
    name="opencv_template_match",
    description="Fallback-Detektion via OpenCV Template Matching (single oder multi-scale).",
    parameters=[
        P("image_path", "string", "Optionaler Bildpfad. Wenn leer: aktueller Screenshot.", required=False, default=None),
        P("template_name", "string", "Template-Name aus assets/templates (ohne Endung möglich).", required=False, default=None),
        P("template_path", "string", "Optionaler direkter Template-Pfad.", required=False, default=None),
        P("threshold", "number", "Match-Schwelle (0.0 - 1.0).", required=False, default=0.82),
        P("multi_scale", "boolean", "Suche in mehreren Skalen.", required=False, default=True),
        P("max_results", "integer", "Maximale Anzahl Treffer.", required=False, default=5),
    ],
    capabilities=["vision", "opencv", "template_matching", "fallback"],
    category=C.VISION,
)
async def opencv_template_match(
    image_path: Optional[str] = None,
    template_name: Optional[str] = None,
    template_path: Optional[str] = None,
    threshold: float = 0.82,
    multi_scale: bool = True,
    max_results: int = 5,
) -> dict:
    return await asyncio.to_thread(
        match_templates,
        image_path,
        template_name,
        template_path,
        threshold,
        multi_scale,
        max_results,
    )


@tool(
    name="list_template_assets",
    description="Listet verfügbare OpenCV-Template-Dateien im Template-Verzeichnis.",
    parameters=[
        P("template_dir", "string", "Optionales Template-Verzeichnis.", required=False, default=None),
    ],
    capabilities=["vision", "opencv", "template_matching"],
    category=C.VISION,
)
async def list_template_assets(template_dir: Optional[str] = None) -> dict:
    directory = Path(template_dir).expanduser().resolve() if template_dir else DEFAULT_TEMPLATE_DIR.expanduser().resolve()
    files = _list_template_files(directory, template_name=None)
    return {
        "template_dir": str(directory),
        "count": len(files),
        "templates": [f.name for f in files],
    }
