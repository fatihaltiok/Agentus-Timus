import os
from pathlib import Path

import pytest


INTEGRATION_TEST_FILES = {
    "test_agent_integration.py",
    "test_cookie_banner.py",
    "test_hybrid_detection.py",
    "test_inception_fix.py",
    "test_inworld_tts.py",
    "test_loop_detection.py",
    "test_mcp_moondream.py",
    "test_meta_agent.py",
    "test_moondream_tool.py",
    "test_ocr_backends.py",
    "test_optimized_moondream.py",
    "test_prompt_comparison.py",
    "test_real_auto.py",
    "test_real_scenario.py",
    "test_roi_support.py",
    "test_som_detection.py",
    "test_structured_navigation.py",
    "test_verified_vision.py",
    "test_verified_vision_auto.py",
    "test_vision_stability.py",
    "test_visual_agent_tool.py",
    "test_zoom_detection.py",
}


def pytest_collection_modifyitems(config, items):
    if os.getenv("RUN_INTEGRATION_TESTS") == "1":
        return

    skip_marker = pytest.mark.skip(
        reason="Integrationstests deaktiviert (RUN_INTEGRATION_TESTS=1 zum Aktivieren)."
    )

    for item in items:
        if Path(str(item.fspath)).name in INTEGRATION_TEST_FILES:
            item.add_marker(skip_marker)
