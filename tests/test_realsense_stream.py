from __future__ import annotations

import time
from pathlib import Path

import numpy as np

from utils import realsense_stream as rs


def test_score_v4l2_prefers_color_over_depth():
    depth_text = """
    [0]: 'Z16 ' (16-bit Depth)
    [1]: 'GREY' (8-bit Greyscale)
    """
    color_text = """
    [0]: 'YUYV' (YUYV 4:2:2)
        Size: Discrete 1920x1080
            Interval: Discrete 0.067s (15.000 fps)
    """
    assert rs._score_v4l2_formats(color_text) > rs._score_v4l2_formats(depth_text)


def test_select_realsense_rgb_device_uses_highest_scored_node(monkeypatch):
    monkeypatch.setattr(rs, "_list_video_nodes", lambda: ["/dev/video2", "/dev/video4"])

    def _fake_score(node: str):
        return {"/dev/video2": -10, "/dev/video4": 35}[node]

    monkeypatch.setattr(rs, "_score_device_with_v4l2", _fake_score)

    idx = rs.select_realsense_rgb_device()
    assert idx == 4


def test_export_latest_frame_writes_file(tmp_path):
    manager = rs.RealSenseStreamManager()
    frame = np.full((64, 96, 3), 127, dtype=np.uint8)

    manager._latest_frame = frame
    manager._latest_ts = time.time()

    result = manager.export_latest_frame(output_dir=str(tmp_path), prefix="live", max_age_sec=10.0, ext="jpg")
    assert result["success"] is True
    assert Path(result["path"]).exists()
    assert result["width"] == 96
    assert result["height"] == 64

