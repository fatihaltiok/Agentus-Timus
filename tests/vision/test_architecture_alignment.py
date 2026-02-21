"""Milestone 6 - Architecture alignment checks for the vision pipeline."""

from __future__ import annotations

import json
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _read(relative_path: str) -> str:
    return (PROJECT_ROOT / relative_path).read_text(encoding="utf-8")


def test_m6_mcp_server_registers_required_vision_modules() -> None:
    source = _read("server/mcp_server.py")
    required_modules = [
        "tools.debug_screenshot_tool.tool",
        "tools.verification_tool.tool",
        "tools.som_tool.tool",
        "tools.visual_grounding_tool.tool",
        "tools.hybrid_detection_tool.tool",
        "tools.screen_contract_tool.tool",
        "tools.opencv_template_matcher_tool.tool",
        "tools.browser_controller.tool",
        "tools.reflection_tool.tool",
    ]
    for module_path in required_modules:
        assert module_path in source, f"Missing vision module in MCP TOOL_MODULES: {module_path}"


def test_m6_coordinate_and_dpr_contracts_are_centralized() -> None:
    som_source = _read("tools/som_tool/tool.py")
    grounding_source = _read("tools/visual_grounding_tool/tool.py")
    browser_controller_source = _read("tools/browser_controller/controller.py")
    browser_context_source = _read("tools/browser_tool/persistent_context.py")

    assert "from utils.coordinate_converter import (" in som_source
    assert "normalize_point" in som_source
    assert "denormalize_point" in som_source
    assert "from utils.coordinate_converter import sanitize_scale, to_click_point" in grounding_source
    assert "from utils.coordinate_converter import resolve_click_coordinates" in browser_controller_source
    assert '"viewport"' in browser_context_source
    assert '"device_scale_factor"' in browser_context_source
    assert "sanitize_scale" in browser_context_source


def test_m6_hybrid_pipeline_contains_recovery_and_quality_markers() -> None:
    source = _read("tools/hybrid_detection_tool/tool.py")

    required_markers = [
        "pipeline_log",
        "detect_primary",
        "detect_recovery",
        '"stage": "final"',
        '"attempt_count"',
        '"runtime_ms"',
        '"recovered"',
        "_load_active_vision_adaptive",
        "_adaptive_template_threshold",
    ]
    for marker in required_markers:
        assert marker in source, f"Missing hybrid pipeline marker: {marker}"


def test_m6_reflection_and_adaptive_policy_are_safe_by_default() -> None:
    reflection_source = _read("tools/reflection_tool/tool.py")
    for name in [
        'name="reflection_analyze_visual_patterns"',
        'name="reflection_list_pending_adaptations"',
        'name="reflection_approve_adaptation"',
        'name="reflection_reject_adaptation"',
    ]:
        assert name in reflection_source, f"Missing reflection RPC declaration: {name}"

    config = json.loads(_read("data/vision_adaptive_config.json"))
    policy = config.get("policy", {})
    assert policy.get("require_human_approval") is True
    assert policy.get("auto_apply") is False


def test_m6_required_vision_test_suites_exist() -> None:
    required_tests = [
        "tests/vision/test_m0_baseline_inventory.py",
        "tests/vision/test_debug_screenshot_tool.py",
        "tests/vision/test_coordinate_converter.py",
        "tests/vision/test_som_coordinate_contract.py",
        "tests/vision/test_opencv_template_matcher_tool.py",
        "tests/vision/test_hybrid_opencv_fallback.py",
        "tests/vision/test_reflection_visual_patterns.py",
        "tests/vision/test_reflection_adaptive_config.py",
        "tests/e2e/test_vision_pipeline_e2e.py",
        "tests/e2e/test_vision_fail_recovery_e2e.py",
    ]
    missing = [path for path in required_tests if not (PROJECT_ROOT / path).exists()]
    assert not missing, f"Missing milestone test suites: {missing}"
