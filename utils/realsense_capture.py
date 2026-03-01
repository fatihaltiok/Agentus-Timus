"""Helpers for Intel RealSense camera probing and frame capture."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional


class RealSenseError(RuntimeError):
    """Raised when RealSense camera operations fail."""


def _short(text: str, limit: int = 400) -> str:
    value = (text or "").strip()
    if len(value) <= limit:
        return value
    return value[: limit - 3] + "..."


def _command_exists(name: str) -> bool:
    return bool(shutil.which(name))


def get_realsense_status(timeout_sec: float = 8.0) -> Dict[str, Any]:
    """Return camera availability and basic metadata via rs-enumerate-devices."""
    status: Dict[str, Any] = {
        "available": False,
        "tooling": {
            "rs_enumerate_devices": _command_exists("rs-enumerate-devices"),
            "rs_save_to_disk": _command_exists("rs-save-to-disk"),
        },
    }

    if not status["tooling"]["rs_enumerate_devices"]:
        status["reason"] = "rs-enumerate-devices_not_found"
        return status

    try:
        proc = subprocess.run(
            ["rs-enumerate-devices"],
            capture_output=True,
            text=True,
            timeout=max(2.0, float(timeout_sec)),
            check=False,
        )
    except Exception as exc:
        status["reason"] = f"enumerate_exception: {exc}"
        return status

    combined = "\n".join([proc.stdout or "", proc.stderr or ""]).strip()
    has_device = ("Intel RealSense" in combined) or ("Device info:" in combined)
    status["available"] = bool(has_device)
    status["returncode"] = int(proc.returncode)
    status["raw_excerpt"] = _short(combined, limit=600)

    serial_match = re.search(r"Serial Number\s*:\s*([A-Za-z0-9_-]+)", combined)
    firmware_match = re.search(r"Firmware Version\s*:\s*([0-9.]+)", combined)
    recommended_match = re.search(
        r"Recommended Firmware Version\s*:\s*([0-9.]+)", combined
    )
    product_match = re.search(r"Name\s*:\s*(.+)", combined)

    status["device"] = {
        "name": (product_match.group(1).strip() if product_match else None),
        "serial": (serial_match.group(1).strip() if serial_match else None),
        "firmware": (firmware_match.group(1).strip() if firmware_match else None),
        "recommended_firmware": (
            recommended_match.group(1).strip() if recommended_match else None
        ),
    }

    if not has_device:
        status["reason"] = "no_realsense_device_detected"

    return status


def _pick_first(paths: list[Path]) -> Optional[Path]:
    existing = [p for p in paths if p.exists() and p.is_file()]
    if not existing:
        return None
    existing.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return existing[0]


def _default_capture_dir() -> Path:
    configured = os.getenv("REALSENSE_CAPTURE_DIR", "").strip()
    if configured:
        return Path(configured).expanduser().resolve()
    return (Path(__file__).resolve().parents[1] / "data" / "realsense_captures").resolve()


def capture_realsense_frame(
    output_dir: Optional[str] = None,
    prefix: str = "d435",
    include_depth: bool = True,
    timeout_sec: float = 12.0,
) -> Dict[str, Any]:
    """Capture a single RealSense frame via rs-save-to-disk and persist it."""
    if not _command_exists("rs-save-to-disk"):
        raise RealSenseError("rs-save-to-disk nicht gefunden. Installiere librealsense2-utils.")

    target_dir = Path(output_dir).expanduser().resolve() if output_dir else _default_capture_dir()
    target_dir.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="timus_rs_capture_") as tmp:
        temp_dir = Path(tmp)
        try:
            proc = subprocess.run(
                ["rs-save-to-disk"],
                cwd=str(temp_dir),
                capture_output=True,
                text=True,
                timeout=max(3.0, float(timeout_sec)),
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise RealSenseError(f"Capture-Timeout nach {timeout_sec:.1f}s") from exc
        except Exception as exc:
            raise RealSenseError(f"Capture fehlgeschlagen: {exc}") from exc

        color_file = _pick_first(
            [
                temp_dir / "rs-save-to-disk-output-Color.png",
                temp_dir / "rs-save-to-disk-output-Color.jpg",
                temp_dir / "Color.png",
                temp_dir / "Color.jpg",
            ]
        )
        depth_file = _pick_first(
            [
                temp_dir / "rs-save-to-disk-output-Depth.png",
                temp_dir / "Depth.png",
            ]
        )

        if color_file is None:
            stderr_txt = _short(proc.stderr or "")
            stdout_txt = _short(proc.stdout or "")
            raise RealSenseError(
                f"Keine Farbaufnahme erzeugt (rc={proc.returncode}, stdout='{stdout_txt}', stderr='{stderr_txt}')"
            )

        ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S_%f")
        safe_prefix = re.sub(r"[^A-Za-z0-9_.-]+", "_", prefix or "d435").strip("._") or "d435"

        color_target = target_dir / f"{safe_prefix}_{ts}_color.png"
        shutil.move(str(color_file), str(color_target))

        depth_target: Optional[Path] = None
        if include_depth and depth_file is not None:
            depth_target = target_dir / f"{safe_prefix}_{ts}_depth.png"
            shutil.move(str(depth_file), str(depth_target))

        return {
            "success": True,
            "capture_method": "rs-save-to-disk",
            "output_dir": str(target_dir),
            "color_path": str(color_target),
            "depth_path": str(depth_target) if depth_target else None,
            "timestamp_utc": datetime.utcnow().isoformat(timespec="seconds") + "Z",
            "returncode": int(proc.returncode),
            "stdout": _short(proc.stdout or "", limit=1200),
            "stderr": _short(proc.stderr or "", limit=1200),
        }
