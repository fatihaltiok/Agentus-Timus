from __future__ import annotations

import subprocess
from pathlib import Path

from utils import realsense_capture as rs


def test_get_realsense_status_parses_device_output(monkeypatch):
    def _fake_which(name: str):
        return f"/usr/bin/{name}"

    def _fake_run(*args, **kwargs):
        output = """
Device info:
    Name                          : \tIntel RealSense D435
    Serial Number                 : \t923322073247
    Firmware Version              : \t5.17.0.10
    Recommended Firmware Version  : \t5.17.0.10
"""
        return subprocess.CompletedProcess(args=["rs-enumerate-devices"], returncode=0, stdout=output, stderr="")

    monkeypatch.setattr(rs.shutil, "which", _fake_which)
    monkeypatch.setattr(rs.subprocess, "run", _fake_run)

    status = rs.get_realsense_status()
    assert status["available"] is True
    assert status["device"]["name"] == "Intel RealSense D435"
    assert status["device"]["serial"] == "923322073247"
    assert status["device"]["firmware"] == "5.17.0.10"


def test_capture_realsense_frame_moves_color_and_depth_files(monkeypatch, tmp_path):
    output_dir = tmp_path / "captures"

    def _fake_which(name: str):
        if name == "rs-save-to-disk":
            return "/usr/bin/rs-save-to-disk"
        return None

    def _fake_run(*args, **kwargs):
        cwd = Path(kwargs["cwd"])
        (cwd / "rs-save-to-disk-output-Color.png").write_bytes(b"fake-color")
        (cwd / "rs-save-to-disk-output-Depth.png").write_bytes(b"fake-depth")
        return subprocess.CompletedProcess(
            args=["rs-save-to-disk"],
            returncode=0,
            stdout="Saved rs-save-to-disk-output-Color.png",
            stderr="",
        )

    monkeypatch.setattr(rs.shutil, "which", _fake_which)
    monkeypatch.setattr(rs.subprocess, "run", _fake_run)

    result = rs.capture_realsense_frame(output_dir=str(output_dir), prefix="timus", include_depth=True)
    assert result["success"] is True
    assert result["capture_method"] == "rs-save-to-disk"
    assert Path(result["color_path"]).exists()
    assert Path(result["depth_path"]).exists()

