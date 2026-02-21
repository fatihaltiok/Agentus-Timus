"""Milestone 0 baseline inventory checks for the vision rollout plan."""

from __future__ import annotations

import re
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]


REQUIRED_PATHS = [
    "main_dispatcher.py",
    "server/mcp_server.py",
    "tools/verification_tool/tool.py",
    "tools/debug_screenshot_tool/tool.py",
    "tools/browser_tool/tool.py",
    "tools/som_tool/tool.py",
    "tools/visual_grounding_tool/tool.py",
    "tools/florence2_tool/tool.py",
    "tests/test_browser_isolation.py",
    "tests/test_florence2_hybrid_paddleocr.py",
    "tests/vision/test_debug_screenshot_tool.py",
    "tests/vision/test_verification_overlay_integration.py",
]

REQUIRED_TOOL_DECLARATIONS = {
    "tools/browser_tool/tool.py": [
        'name="open_url"',
        'name="click_by_text"',
        'name="browser_session_status"',
    ],
    "tools/florence2_tool/tool.py": [
        'name="florence2_hybrid_analysis"',
        'name="florence2_detect_ui"',
    ],
    "tools/verification_tool/tool.py": [
        'name="capture_screen_before_action"',
        'name="verify_action_result"',
    ],
    "tools/debug_screenshot_tool/tool.py": [
        'name="capture_debug_screenshot"',
    ],
}

REQUIRED_DISPATCHER_MARKERS = [
    "AGENT_CLASS_MAP",
    '"visual": "SPECIAL_VISUAL_NEMOTRON"',
    '"vision_qwen": "SPECIAL_VISUAL_NEMOTRON"',
    '"visual_nemotron": "SPECIAL_VISUAL_NEMOTRON"',
    "lane_manager.set_registry(registry_v2)",
]

REQUIRED_CI_PINS = {
    "pytest": "8.3.5",
    "pytest-asyncio": "0.24.0",
    "openai": "1.101.0",
    "httpx": "0.27.2",
    "chromadb": "0.4.24",
    "numpy": "1.26.4",
}


def _read(relative_path: str) -> str:
    return (PROJECT_ROOT / relative_path).read_text(encoding="utf-8")


def test_m0_required_paths_exist() -> None:
    missing = [path for path in REQUIRED_PATHS if not (PROJECT_ROOT / path).exists()]
    assert not missing, f"Missing required baseline files: {missing}"


def test_m0_required_tool_declarations_present() -> None:
    for relative_path, snippets in REQUIRED_TOOL_DECLARATIONS.items():
        content = _read(relative_path)
        for snippet in snippets:
            assert snippet in content, f"Missing tool declaration {snippet} in {relative_path}"


def test_m0_dispatcher_paths_and_visual_routing_present() -> None:
    dispatcher_source = _read("main_dispatcher.py")
    for marker in REQUIRED_DISPATCHER_MARKERS:
        assert marker in dispatcher_source, f"Missing dispatcher marker: {marker}"


def test_m0_ci_versions_are_pinned_for_reproducibility() -> None:
    requirements_ci = _read("requirements-ci.txt")
    for package, version in REQUIRED_CI_PINS.items():
        pattern = rf"^{re.escape(package)}=={re.escape(version)}$"
        assert re.search(pattern, requirements_ci, flags=re.MULTILINE), (
            f"Missing pinned CI dependency: {package}=={version}"
        )

    assert sys.version_info >= (3, 11), (
        "Baseline requires Python >= 3.11 for async tooling and tests."
    )
