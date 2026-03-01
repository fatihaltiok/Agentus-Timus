"""MCP tools for Intel RealSense camera status and snapshot capture."""

from __future__ import annotations

import asyncio
import logging
from typing import Optional

from tools.tool_registry_v2 import tool, ToolCategory as C, ToolParameter as P
from utils.realsense_capture import (
    RealSenseError,
    capture_realsense_frame,
    get_realsense_status,
)
from utils.realsense_stream import (
    RealSenseStreamError,
    get_realsense_stream_manager,
)


log = logging.getLogger("timus.realsense_camera_tool")


@tool(
    name="realsense_status",
    description="Prüft, ob eine Intel RealSense Kamera erkannt wird und liefert Geräteinfos.",
    parameters=[
        P(
            "timeout_sec",
            "number",
            "Timeout in Sekunden für die Geräteabfrage (Standard: 8).",
            required=False,
            default=8.0,
        )
    ],
    capabilities=["vision", "camera", "realsense", "health"],
    category=C.VISION,
)
async def realsense_status(timeout_sec: float = 8.0) -> dict:
    status = await asyncio.to_thread(get_realsense_status, timeout_sec)
    return status


@tool(
    name="capture_realsense_snapshot",
    description=(
        "Nimmt ein aktuelles Bild von der Intel RealSense Kamera auf und speichert "
        "es als PNG-Datei."
    ),
    parameters=[
        P(
            "output_dir",
            "string",
            "Optionales Zielverzeichnis. Standard: data/realsense_captures.",
            required=False,
            default=None,
        ),
        P(
            "prefix",
            "string",
            "Dateiname-Präfix (Standard: d435).",
            required=False,
            default="d435",
        ),
        P(
            "include_depth",
            "boolean",
            "Wenn true und vorhanden, speichert zusätzlich ein Depth-PNG.",
            required=False,
            default=True,
        ),
        P(
            "timeout_sec",
            "number",
            "Timeout in Sekunden für die Aufnahme (Standard: 12).",
            required=False,
            default=12.0,
        ),
    ],
    capabilities=["vision", "camera", "realsense", "image", "ocr"],
    category=C.VISION,
)
async def capture_realsense_snapshot(
    output_dir: Optional[str] = None,
    prefix: str = "d435",
    include_depth: bool = True,
    timeout_sec: float = 12.0,
) -> dict:
    try:
        result = await asyncio.to_thread(
            capture_realsense_frame,
            output_dir,
            prefix,
            include_depth,
            timeout_sec,
        )
        return result
    except RealSenseError as exc:
        log.warning(f"RealSense-Snapshot fehlgeschlagen: {exc}")
        return {
            "success": False,
            "error": str(exc),
            "hint": "Prüfe Kamera mit realsense_status oder rs-enumerate-devices.",
        }


@tool(
    name="start_realsense_stream",
    description="Startet einen kontinuierlichen RGB-Live-Stream der Intel RealSense Kamera.",
    parameters=[
        P("width", "integer", "Zielbreite (Standard: 1280).", required=False, default=1280),
        P("height", "integer", "Zielhöhe (Standard: 720).", required=False, default=720),
        P("fps", "number", "Ziel-FPS (Standard: 10).", required=False, default=10.0),
        P(
            "device_index",
            "integer",
            "Optionaler /dev/video Index (z.B. 4). Ohne Angabe wird auto-detektiert.",
            required=False,
            default=None,
        ),
    ],
    capabilities=["vision", "camera", "realsense", "stream"],
    category=C.VISION,
)
async def start_realsense_stream(
    width: int = 1280,
    height: int = 720,
    fps: float = 10.0,
    device_index: Optional[int] = None,
) -> dict:
    manager = get_realsense_stream_manager()
    try:
        status = await asyncio.to_thread(
            manager.start, width, height, fps, device_index
        )
        return {"success": True, "status": status}
    except RealSenseStreamError as exc:
        return {"success": False, "error": str(exc)}
    except Exception as exc:
        log.error(f"start_realsense_stream Fehler: {exc}")
        return {"success": False, "error": str(exc)}


@tool(
    name="stop_realsense_stream",
    description="Stoppt den laufenden RealSense-Live-Stream.",
    parameters=[],
    capabilities=["vision", "camera", "realsense", "stream"],
    category=C.VISION,
)
async def stop_realsense_stream() -> dict:
    manager = get_realsense_stream_manager()
    status = await asyncio.to_thread(manager.stop)
    return {"success": True, "status": status}


@tool(
    name="realsense_stream_status",
    description="Liefert Status, FPS/Größe und letzte Frame-Age des RealSense-Live-Streams.",
    parameters=[],
    capabilities=["vision", "camera", "realsense", "stream", "health"],
    category=C.VISION,
)
async def realsense_stream_status() -> dict:
    manager = get_realsense_stream_manager()
    status = await asyncio.to_thread(manager.status)
    return {"success": True, "status": status}


@tool(
    name="capture_realsense_live_frame",
    description=(
        "Exportiert den neuesten Frame aus dem laufenden RealSense-Stream in eine Bilddatei."
    ),
    parameters=[
        P(
            "output_dir",
            "string",
            "Optionales Zielverzeichnis. Standard: data/realsense_stream.",
            required=False,
            default=None,
        ),
        P(
            "prefix",
            "string",
            "Datei-Präfix für den exportierten Live-Frame.",
            required=False,
            default="realsense_live",
        ),
        P(
            "max_age_sec",
            "number",
            "Maximales Alter des letzten Frames in Sekunden (Standard: 3.0).",
            required=False,
            default=3.0,
        ),
        P(
            "ext",
            "string",
            "Dateiformat: jpg oder png (Standard: jpg).",
            required=False,
            default="jpg",
            enum=["jpg", "png"],
        ),
    ],
    capabilities=["vision", "camera", "realsense", "stream", "image"],
    category=C.VISION,
)
async def capture_realsense_live_frame(
    output_dir: Optional[str] = None,
    prefix: str = "realsense_live",
    max_age_sec: float = 3.0,
    ext: str = "jpg",
) -> dict:
    manager = get_realsense_stream_manager()
    try:
        result = await asyncio.to_thread(
            manager.export_latest_frame,
            output_dir,
            prefix,
            max_age_sec,
            ext,
        )
        return result
    except RealSenseStreamError as exc:
        return {"success": False, "error": str(exc)}
    except Exception as exc:
        log.error(f"capture_realsense_live_frame Fehler: {exc}")
        return {"success": False, "error": str(exc)}
