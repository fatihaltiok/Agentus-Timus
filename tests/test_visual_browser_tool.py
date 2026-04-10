import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.visual_browser_tool import tool as visual_browser_tool


def test_browser_instance_key_uses_profile_for_chrome():
    assert visual_browser_tool._browser_instance_key("chrome", "Default") == "chrome::default"
    assert visual_browser_tool._browser_instance_key("firefox", "Default") == "firefox"


def test_get_browser_command_includes_chrome_profile_on_linux(monkeypatch):
    monkeypatch.setattr(visual_browser_tool.platform, "system", lambda: "Linux")
    monkeypatch.setattr(visual_browser_tool.shutil, "which", lambda name: "/usr/bin/google-chrome" if name == "google-chrome" else None)

    cmd = visual_browser_tool._get_browser_command(
        "chrome",
        "https://github.com/login",
        "Default",
    )

    assert cmd[0] == "/usr/bin/google-chrome"
    assert "--new-window" in cmd
    assert "--profile-directory=Default" in cmd
    assert cmd[-1] == "https://github.com/login"
