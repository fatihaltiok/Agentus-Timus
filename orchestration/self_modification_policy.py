from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Optional


def _normalize_relative_path(file_path: str) -> str:
    path = str(file_path or "").strip().replace("\\", "/").lstrip("./")
    while "//" in path:
        path = path.replace("//", "/")
    return path


def _matches_any(path: str, patterns: tuple[str, ...]) -> bool:
    candidate = PurePosixPath(path)
    for pattern in patterns:
        if candidate.match(pattern):
            return True
    return False


@dataclass(frozen=True)
class SelfModificationZone:
    zone_id: str
    path_patterns: tuple[str, ...]
    allowed_change_types: tuple[str, ...]
    required_test_targets: tuple[str, ...]
    required_checks: tuple[str, ...]
    require_approval: bool = False


@dataclass(frozen=True)
class SelfModificationPolicyDecision:
    allowed: bool
    reason: str
    zone_id: str = ""
    effective_change_type: str = ""
    allowed_change_types: tuple[str, ...] = ()
    required_test_targets: tuple[str, ...] = ()
    required_checks: tuple[str, ...] = ()
    require_approval: bool = False


BLOCKED_PATTERNS: tuple[str, ...] = (
    ".env",
    "*.service",
    "deploy/**",
    "gateway/**",
    "server/**",
    "main_dispatcher.py",
    "agent/base_agent.py",
    "agent/agents/**",
    "memory/soul_engine.py",
    "orchestration/autonomous_runner.py",
    "orchestration/self_healing_engine.py",
    "orchestration/self_modifier_engine.py",
    "orchestration/task_queue.py",
    "tools/code_editor_tool/**",
    "tools/email_tool/**",
    "tools/shell_tool/**",
    "tools/voice_tool/**",
    "utils/policy_gate.py",
    "requirements*.txt",
)


ALLOWED_ZONES: tuple[SelfModificationZone, ...] = (
    SelfModificationZone(
        zone_id="prompt_policy",
        path_patterns=("agent/prompts.py",),
        allowed_change_types=("prompt_policy", "documentation"),
        required_test_targets=(
            "tests/test_m4_meta_orchestrator.py",
            "tests/test_meta_orchestrator_hardening.py",
            "tests/test_meta_handoff.py",
        ),
        required_checks=("py_compile", "pytest_targeted", "production_gates"),
    ),
    SelfModificationZone(
        zone_id="meta_orchestration",
        path_patterns=(
            "orchestration/meta_*.py",
            "orchestration/orchestration_policy.py",
        ),
        allowed_change_types=("orchestration_policy", "analytics_observability"),
        required_test_targets=(
            "tests/test_meta_orchestration.py",
            "tests/test_meta_handoff.py",
            "tests/test_meta_recipe_execution.py",
            "tests/test_orchestration_policy.py",
        ),
        required_checks=("py_compile", "pytest_targeted", "crosshair", "lean", "production_gates"),
    ),
    SelfModificationZone(
        zone_id="browser_workflow",
        path_patterns=(
            "orchestration/browser_workflow_*.py",
        ),
        allowed_change_types=("orchestration_policy", "evaluation_tests"),
        required_test_targets=(
            "tests/test_browser_workflow_plan.py",
            "tests/test_browser_workflow_eval.py",
            "tests/test_visual_improvements.py",
        ),
        required_checks=("py_compile", "pytest_targeted", "lean", "production_gates"),
    ),
    SelfModificationZone(
        zone_id="tests",
        path_patterns=("tests/test_*.py",),
        allowed_change_types=("evaluation_tests",),
        required_test_targets=(),
        required_checks=("py_compile", "pytest_targeted"),
    ),
    SelfModificationZone(
        zone_id="docs",
        path_patterns=("docs/*.md",),
        allowed_change_types=("documentation",),
        required_test_targets=(),
        required_checks=("production_gates",),
    ),
)


def evaluate_self_modification_policy(file_path: str, change_type: str = "auto") -> SelfModificationPolicyDecision:
    rel = _normalize_relative_path(file_path)
    if not rel:
        return SelfModificationPolicyDecision(False, "ungueltiger Dateipfad")
    if _matches_any(rel, BLOCKED_PATTERNS):
        return SelfModificationPolicyDecision(False, f"Datei liegt in einer gesperrten Selbstmodifikationszone: {rel}")

    for zone in ALLOWED_ZONES:
        if not _matches_any(rel, zone.path_patterns):
            continue
        effective_change_type = zone.allowed_change_types[0] if change_type in {"", "auto"} else change_type
        if effective_change_type not in zone.allowed_change_types:
            return SelfModificationPolicyDecision(
                False,
                f"Aenderungstyp '{effective_change_type}' ist fuer Zone '{zone.zone_id}' nicht erlaubt",
                zone_id=zone.zone_id,
                effective_change_type=effective_change_type,
                allowed_change_types=zone.allowed_change_types,
                required_test_targets=zone.required_test_targets,
                required_checks=zone.required_checks,
                require_approval=zone.require_approval,
            )
        return SelfModificationPolicyDecision(
            True,
            "allowed",
            zone_id=zone.zone_id,
            effective_change_type=effective_change_type,
            allowed_change_types=zone.allowed_change_types,
            required_test_targets=zone.required_test_targets,
            required_checks=zone.required_checks,
            require_approval=zone.require_approval,
        )

    return SelfModificationPolicyDecision(
        False,
        f"Datei gehoert zu keiner freigegebenen Low-Risk-Selbstmodifikationszone: {rel}",
    )
