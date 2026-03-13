from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from orchestration.self_modification_policy import SelfModificationPolicyDecision


@dataclass(frozen=True)
class CanaryCheckResult:
    name: str
    status: str
    command: tuple[str, ...] = ()
    detail: str = ""


@dataclass(frozen=True)
class SelfModificationCanaryResult:
    state: str
    checks: tuple[CanaryCheckResult, ...] = ()
    rollback_required: bool = False

    @property
    def summary(self) -> str:
        return ", ".join(f"{check.name}:{check.status}" for check in self.checks)


def _run_command(command: tuple[str, ...], cwd: Path) -> CanaryCheckResult:
    completed = subprocess.run(
        list(command),
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=300,
    )
    detail = (completed.stdout or completed.stderr or "").strip()[:400]
    return CanaryCheckResult(
        name=command[2] if len(command) > 2 and command[1:3] == ("-m", "py_compile") else command[0],
        status="passed" if completed.returncode == 0 else "failed",
        command=command,
        detail=detail,
    )


def run_self_modification_canary(
    *,
    project_root: Path,
    relative_path: str,
    policy: SelfModificationPolicyDecision,
    pytest_runner: Callable[..., str],
) -> SelfModificationCanaryResult:
    checks: list[CanaryCheckResult] = []

    if "py_compile" in policy.required_checks:
        command = (sys.executable, "-m", "py_compile", relative_path)
        result = _run_command(command, cwd=project_root)
        checks.append(CanaryCheckResult("py_compile", result.status, command, result.detail))
        if result.status != "passed":
            return SelfModificationCanaryResult("failed", tuple(checks), rollback_required=True)

    if policy.required_test_targets:
        pytest_status = pytest_runner(
            relative_path,
            policy_test_targets=policy.required_test_targets,
            project_root=project_root,
        )
        checks.append(CanaryCheckResult("pytest_targeted", pytest_status))
        if pytest_status != "passed":
            return SelfModificationCanaryResult("failed", tuple(checks), rollback_required=True)

    gates_script = project_root / "scripts" / "run_production_gates.py"
    if gates_script.exists():
        command = (sys.executable, "scripts/run_production_gates.py")
        result = _run_command(command, cwd=project_root)
        checks.append(CanaryCheckResult("production_gates", result.status, command, result.detail))
        if result.status != "passed":
            return SelfModificationCanaryResult("failed", tuple(checks), rollback_required=True)

    return SelfModificationCanaryResult("passed", tuple(checks), rollback_required=False)
