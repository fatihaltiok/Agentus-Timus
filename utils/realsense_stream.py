"""Background Intel RealSense RGB stream manager."""

from __future__ import annotations

import glob
import logging
import os
import re
import shutil
import subprocess
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

try:
    import cv2
    import numpy as np
except ImportError:
    cv2 = None  # type: ignore[assignment]
    np = None   # type: ignore[assignment]


log = logging.getLogger("timus.realsense_stream")


class RealSenseStreamError(RuntimeError):
    """Raised for RealSense stream lifecycle and frame errors."""


def _extract_video_index(dev_path: str) -> Optional[int]:
    match = re.search(r"/dev/video(\d+)$", str(dev_path))
    if not match:
        return None
    return int(match.group(1))


def _score_v4l2_formats(text: str) -> int:
    body = (text or "").upper()
    score = 0

    if "YUYV" in body:
        score += 25
    if "UYVY" in body:
        score += 15
    if "MJPG" in body or "RGB3" in body:
        score += 20
    if "1920X1080" in body:
        score += 15
    if "1280X720" in body:
        score += 10
    if "30.000 FPS" in body:
        score += 8
    if "15.000 FPS" in body:
        score += 4

    # Depth / IR penalties
    if "Z16" in body or "16-BIT DEPTH" in body:
        score -= 40
    if "GREY" in body or "Y8I" in body:
        score -= 12

    return score


def _list_video_nodes() -> list[str]:
    nodes = sorted(glob.glob("/dev/video*"))
    return [n for n in nodes if _extract_video_index(n) is not None]


def _score_device_with_v4l2(dev_path: str) -> Optional[int]:
    if not shutil.which("v4l2-ctl"):
        return None
    try:
        proc = subprocess.run(
            ["v4l2-ctl", "-d", dev_path, "--list-formats-ext"],
            capture_output=True,
            text=True,
            timeout=2.0,
            check=False,
        )
    except Exception:
        return None
    txt = "\n".join([(proc.stdout or ""), (proc.stderr or "")])
    return _score_v4l2_formats(txt)


def _score_device_with_opencv(index: int) -> Optional[float]:
    cap = cv2.VideoCapture(index)
    if not cap.isOpened():
        return None
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
    ok, frame = cap.read()
    cap.release()
    if not ok or frame is None:
        return None

    if frame.ndim != 3 or frame.shape[2] < 3:
        return 0.0

    b = frame[:, :, 0].astype(np.int16)
    g = frame[:, :, 1].astype(np.int16)
    r = frame[:, :, 2].astype(np.int16)
    color_delta = float(
        (np.mean(np.abs(b - g)) + np.mean(np.abs(g - r)) + np.mean(np.abs(b - r))) / 3.0
    )
    resolution_bonus = min(float(frame.shape[0] * frame.shape[1]) / 50000.0, 40.0)
    return color_delta + resolution_bonus


def select_realsense_rgb_device() -> int:
    """Best-effort selection of the most likely RGB-capable RealSense video device."""
    env_value = (os.getenv("REALSENSE_STREAM_DEVICE") or "").strip()
    if env_value:
        try:
            return int(env_value)
        except ValueError as exc:
            raise RealSenseStreamError(
                f"Ungültiger REALSENSE_STREAM_DEVICE Wert: '{env_value}'"
            ) from exc

    nodes = _list_video_nodes()
    if not nodes:
        raise RealSenseStreamError("Keine /dev/video* Geräte gefunden.")

    v4l2_scores: list[tuple[int, str]] = []
    for node in nodes:
        s = _score_device_with_v4l2(node)
        if s is None:
            continue
        v4l2_scores.append((s, node))

    if v4l2_scores:
        v4l2_scores.sort(reverse=True)
        best_node = v4l2_scores[0][1]
        idx = _extract_video_index(best_node)
        if idx is not None:
            return idx

    cv_scores: list[tuple[float, int]] = []
    for node in nodes:
        idx = _extract_video_index(node)
        if idx is None:
            continue
        s = _score_device_with_opencv(idx)
        if s is None:
            continue
        cv_scores.append((s, idx))

    if cv_scores:
        cv_scores.sort(reverse=True)
        return int(cv_scores[0][1])

    raise RealSenseStreamError("Kein nutzbarer RealSense-Video-Stream gefunden.")


@dataclass
class StreamConfig:
    device_index: int
    width: int = 1280
    height: int = 720
    fps: float = 10.0


class RealSenseStreamManager:
    """Background thread that continuously keeps latest RGB frame in memory."""

    def __init__(self):
        self._lock = threading.Lock()
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._running = False
        self._config: Optional[StreamConfig] = None
        self._latest_frame: Optional[np.ndarray] = None
        self._latest_ts: Optional[float] = None
        self._frame_count = 0
        self._last_error: Optional[str] = None
        self._started_at: Optional[float] = None

    def is_running(self) -> bool:
        with self._lock:
            return bool(self._running)

    def _run_loop(self):
        cfg = self._config
        if cfg is None:
            with self._lock:
                self._running = False
                self._last_error = "missing_stream_config"
            return

        cap = cv2.VideoCapture(cfg.device_index)
        if not cap.isOpened():
            with self._lock:
                self._running = False
                self._last_error = f"Kamera-Device {cfg.device_index} konnte nicht geöffnet werden."
            return

        cap.set(cv2.CAP_PROP_FRAME_WIDTH, float(cfg.width))
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, float(cfg.height))
        cap.set(cv2.CAP_PROP_FPS, float(cfg.fps))
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

        with self._lock:
            self._running = True
            self._last_error = None
            self._started_at = time.time()

        frame_interval = 1.0 / max(1.0, float(cfg.fps))

        try:
            while not self._stop_event.is_set():
                t0 = time.time()
                ok, frame = cap.read()
                if ok and frame is not None:
                    with self._lock:
                        self._latest_frame = frame.copy()
                        self._latest_ts = time.time()
                        self._frame_count += 1
                        self._last_error = None
                else:
                    with self._lock:
                        self._last_error = "Frame read fehlgeschlagen."

                elapsed = time.time() - t0
                sleep_for = frame_interval - elapsed
                if sleep_for > 0:
                    time.sleep(sleep_for)
        finally:
            cap.release()
            with self._lock:
                self._running = False

    def start(
        self,
        width: int = 1280,
        height: int = 720,
        fps: float = 10.0,
        device_index: Optional[int] = None,
    ) -> Dict[str, Any]:
        with self._lock:
            if self._running:
                return self.status()

        idx = int(device_index) if device_index is not None else select_realsense_rgb_device()
        self._config = StreamConfig(
            device_index=idx,
            width=max(320, int(width)),
            height=max(240, int(height)),
            fps=max(1.0, float(fps)),
        )

        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run_loop, daemon=True, name="realsense-stream")
        self._thread.start()

        # Give the thread a short warm-up period for first frame.
        deadline = time.time() + 2.5
        while time.time() < deadline:
            with self._lock:
                if self._latest_ts is not None and self._running:
                    break
                if self._last_error and not self._running:
                    break
            time.sleep(0.05)

        return self.status()

    def stop(self) -> Dict[str, Any]:
        self._stop_event.set()
        t = self._thread
        if t and t.is_alive():
            t.join(timeout=2.5)
        with self._lock:
            self._running = False
        return self.status()

    def status(self) -> Dict[str, Any]:
        with self._lock:
            cfg = self._config
            latest_ts = self._latest_ts
            running = bool(self._running)
            frame_count = int(self._frame_count)
            last_error = self._last_error
            started_at = self._started_at
            shape = tuple(self._latest_frame.shape) if self._latest_frame is not None else None

        now = time.time()
        age_sec = None if latest_ts is None else max(0.0, now - latest_ts)
        return {
            "running": running,
            "device_index": (cfg.device_index if cfg else None),
            "width": (cfg.width if cfg else None),
            "height": (cfg.height if cfg else None),
            "fps": (cfg.fps if cfg else None),
            "frame_count": frame_count,
            "latest_frame_age_sec": age_sec,
            "latest_frame_shape": shape,
            "last_error": last_error,
            "started_at_utc": (
                datetime.utcfromtimestamp(started_at).isoformat(timespec="seconds") + "Z"
                if started_at
                else None
            ),
        }

    def get_frame_jpeg(self, quality: int = 75) -> Optional[bytes]:
        """Gibt den neuesten Frame als JPEG-Bytes zurück (für MJPEG-Streaming).

        Returns:
            JPEG-kodierte Bytes oder None wenn kein Frame verfügbar / cv2 fehlt.
        """
        if cv2 is None or np is None:
            return None
        with self._lock:
            frame = None if self._latest_frame is None else self._latest_frame.copy()
        if frame is None:
            return None
        ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, quality])
        return buf.tobytes() if ok else None

    def export_latest_frame(
        self,
        output_dir: Optional[str] = None,
        prefix: str = "realsense_live",
        max_age_sec: float = 3.0,
        ext: str = "jpg",
    ) -> Dict[str, Any]:
        with self._lock:
            frame = None if self._latest_frame is None else self._latest_frame.copy()
            ts = self._latest_ts

        if frame is None or ts is None:
            raise RealSenseStreamError("Noch kein Live-Frame verfügbar.")

        age_sec = max(0.0, time.time() - ts)
        if max_age_sec > 0 and age_sec > float(max_age_sec):
            raise RealSenseStreamError(
                f"Letzter Live-Frame ist zu alt ({age_sec:.2f}s > {max_age_sec:.2f}s)."
            )

        fmt = "png" if str(ext).lower() == "png" else "jpg"
        dir_path = (
            Path(output_dir).expanduser().resolve()
            if output_dir
            else (Path(__file__).resolve().parents[1] / "data" / "realsense_stream").resolve()
        )
        dir_path.mkdir(parents=True, exist_ok=True)

        safe_prefix = re.sub(r"[^A-Za-z0-9_.-]+", "_", prefix or "realsense_live").strip("._")
        if not safe_prefix:
            safe_prefix = "realsense_live"
        ts_label = datetime.utcfromtimestamp(ts).strftime("%Y%m%d_%H%M%S_%f")
        out_path = dir_path / f"{safe_prefix}_{ts_label}.{fmt}"

        ok = cv2.imwrite(str(out_path), frame)
        if not ok:
            raise RealSenseStreamError(f"Konnte Live-Frame nicht speichern: {out_path}")

        return {
            "success": True,
            "path": str(out_path),
            "timestamp_utc": datetime.utcfromtimestamp(ts).isoformat(timespec="seconds") + "Z",
            "age_sec": age_sec,
            "width": int(frame.shape[1]),
            "height": int(frame.shape[0]),
            "channels": int(frame.shape[2]) if frame.ndim == 3 else 1,
        }


_stream_manager: Optional[RealSenseStreamManager] = None
_stream_manager_lock = threading.Lock()


def get_realsense_stream_manager() -> RealSenseStreamManager:
    global _stream_manager
    if _stream_manager is not None:
        return _stream_manager
    with _stream_manager_lock:
        if _stream_manager is None:
            _stream_manager = RealSenseStreamManager()
    return _stream_manager

