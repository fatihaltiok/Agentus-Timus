"""Create annotated debug screenshots for failed visual actions."""

import asyncio
import json
import os
import time
import uuid
from pathlib import Path
from typing import Any, Dict, Optional

import mss
from PIL import Image, ImageDraw, ImageFont

from tools.tool_registry_v2 import tool, ToolCategory as C, ToolParameter as P


ACTIVE_MONITOR = int(os.getenv("ACTIVE_MONITOR", "1"))
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


def _resolve_debug_dir() -> Path:
    configured = os.getenv("DEBUG_FAILED_CLICKS_DIR")
    if configured:
        return Path(configured).expanduser().resolve()
    return (PROJECT_ROOT / "debug_failed_clicks").resolve()


def _capture_screenshot() -> tuple[Image.Image, Dict[str, int]]:
    with mss.mss() as sct:
        if ACTIVE_MONITOR < len(sct.monitors):
            monitor = sct.monitors[ACTIVE_MONITOR]
        else:
            monitor = sct.monitors[1] if len(sct.monitors) > 1 else sct.monitors[0]

        raw = sct.grab(monitor)
        image = Image.frombytes("RGB", raw.size, raw.bgra, "raw", "BGRX")
        return image, {
            "left": int(monitor["left"]),
            "top": int(monitor["top"]),
            "width": int(monitor["width"]),
            "height": int(monitor["height"]),
        }


def _to_relative_coordinate(value: Optional[int], axis_offset: int, axis_size: int) -> Optional[int]:
    if value is None:
        return None
    if axis_offset <= value < axis_offset + axis_size:
        return value - axis_offset
    if 0 <= value < axis_size:
        return value
    return max(0, min(value - axis_offset, axis_size - 1))


def _calculate_box(
    rel_x: Optional[int],
    rel_y: Optional[int],
    width: int,
    height: int,
    image_width: int,
    image_height: int,
) -> Dict[str, int]:
    if rel_x is not None and rel_y is not None:
        if width > 0 and height > 0:
            half_w = width // 2
            half_h = height // 2
        else:
            half_w = 35
            half_h = 22
        x1 = max(0, rel_x - half_w)
        y1 = max(0, rel_y - half_h)
        x2 = min(image_width - 1, rel_x + half_w)
        y2 = min(image_height - 1, rel_y + half_h)
        return {"x1": x1, "y1": y1, "x2": x2, "y2": y2}

    center_x = image_width // 2
    center_y = image_height // 2
    return {
        "x1": max(0, center_x - 40),
        "y1": max(0, center_y - 25),
        "x2": min(image_width - 1, center_x + 40),
        "y2": min(image_height - 1, center_y + 25),
    }


def _build_paths(file_path: Optional[str]) -> tuple[Path, Path]:
    if file_path:
        screenshot_path = Path(file_path).expanduser().resolve()
        metadata_path = screenshot_path.with_suffix(".json")
        screenshot_path.parent.mkdir(parents=True, exist_ok=True)
        return screenshot_path, metadata_path

    debug_dir = _resolve_debug_dir()
    debug_dir.mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%Y%m%d_%H%M%S")
    suffix = uuid.uuid4().hex[:8]
    screenshot_path = debug_dir / f"failed_action_{ts}_{suffix}.png"
    metadata_path = debug_dir / f"failed_action_{ts}_{suffix}.json"
    return screenshot_path, metadata_path


def create_debug_artifacts(
    target_x: Optional[int] = None,
    target_y: Optional[int] = None,
    width: int = 0,
    height: int = 0,
    confidence: Optional[float] = None,
    message: str = "",
    metadata: Optional[Dict[str, Any]] = None,
    file_path: Optional[str] = None,
) -> Dict[str, Any]:
    """Capture screenshot, draw overlay, and write metadata JSON."""
    image, monitor = _capture_screenshot()
    rel_x = _to_relative_coordinate(target_x, monitor["left"], monitor["width"])
    rel_y = _to_relative_coordinate(target_y, monitor["top"], monitor["height"])
    box = _calculate_box(rel_x, rel_y, width, height, image.width, image.height)

    draw = ImageDraw.Draw(image)
    draw.rectangle([box["x1"], box["y1"], box["x2"], box["y2"]], outline=(255, 0, 0), width=3)

    if rel_x is not None and rel_y is not None:
        draw.line([(rel_x - 8, rel_y), (rel_x + 8, rel_y)], fill=(255, 0, 0), width=2)
        draw.line([(rel_x, rel_y - 8), (rel_x, rel_y + 8)], fill=(255, 0, 0), width=2)

    label_parts = ["FAILED_ACTION"]
    if confidence is not None:
        label_parts.append(f"conf={confidence:.3f}")
    if message:
        label_parts.append(message.strip())
    label_text = " | ".join(label_parts)

    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 14)
    except Exception:
        font = ImageFont.load_default()

    text_x = max(6, box["x1"])
    text_y = max(6, box["y1"] - 24)
    text_w = min(image.width - text_x - 6, max(120, len(label_text) * 7))
    draw.rectangle([text_x, text_y, text_x + text_w, text_y + 20], fill=(0, 0, 0))
    draw.text((text_x + 4, text_y + 3), label_text[:220], fill=(255, 255, 255), font=font)

    screenshot_path, metadata_path = _build_paths(file_path)
    image.save(screenshot_path)

    payload = {
        "timestamp": time.time(),
        "monitor": monitor,
        "target": {
            "x": target_x,
            "y": target_y,
            "relative_x": rel_x,
            "relative_y": rel_y,
            "width": width,
            "height": height,
            "box": box,
        },
        "confidence": confidence,
        "message": message,
        "metadata": metadata or {},
        "files": {
            "screenshot": str(screenshot_path),
            "metadata": str(metadata_path),
        },
    }
    metadata_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    return {
        "success": True,
        "screenshot_path": str(screenshot_path),
        "metadata_path": str(metadata_path),
        "monitor": monitor,
        "box": box,
        "label": label_text,
    }


@tool(
    name="capture_debug_screenshot",
    description="Erstellt einen Debug-Screenshot mit Overlay und zugehöriger Metadaten-Datei.",
    parameters=[
        P("target_x", "integer", "X-Koordinate der Zielaktion (optional)", required=False, default=None),
        P("target_y", "integer", "Y-Koordinate der Zielaktion (optional)", required=False, default=None),
        P("width", "integer", "Breite der Ziel-Bounding-Box", required=False, default=0),
        P("height", "integer", "Hoehe der Ziel-Bounding-Box", required=False, default=0),
        P("confidence", "number", "Confidence-Wert der Erkennung", required=False, default=None),
        P("message", "string", "Kurznachricht fuer den Overlay-Text", required=False, default=""),
        P("metadata", "object", "Beliebige Kontextmetadaten", required=False, default=None),
        P("file_path", "string", "Optionaler absoluter Zielpfad fuer das Bild", required=False, default=None),
    ],
    capabilities=["debug", "vision", "verification"],
    category=C.DEBUG,
)
async def capture_debug_screenshot(
    target_x: Optional[int] = None,
    target_y: Optional[int] = None,
    width: int = 0,
    height: int = 0,
    confidence: Optional[float] = None,
    message: str = "",
    metadata: Optional[Dict[str, Any]] = None,
    file_path: Optional[str] = None,
) -> dict:
    return await asyncio.to_thread(
        create_debug_artifacts,
        target_x,
        target_y,
        width,
        height,
        confidence,
        message,
        metadata,
        file_path,
    )
