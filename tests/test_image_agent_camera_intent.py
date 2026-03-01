from __future__ import annotations

import os

from agent.agents.image import ImageAgent


def test_wants_camera_capture_detection():
    agent = ImageAgent.__new__(ImageAgent)
    assert agent._wants_camera_capture("Schau mit der D435 Kamera und beschreibe das Bild.") is True
    assert agent._wants_camera_capture("Hilf mir bei der Kamera-Firmware Installation.") is False


def test_wants_camera_capture_shortcut_phrase_with_video_device(monkeypatch):
    agent = ImageAgent.__new__(ImageAgent)
    monkeypatch.setattr(os.path, "exists", lambda path: path == "/dev/video4")
    assert agent._wants_camera_capture("Kannst du mich sehen?") is True


def test_wants_camera_capture_shortcut_ignores_non_camera_context(monkeypatch):
    agent = ImageAgent.__new__(ImageAgent)
    monkeypatch.setattr(os.path, "exists", lambda path: path == "/dev/video4")
    assert agent._wants_camera_capture("Schau dir das an: https://example.com") is False
