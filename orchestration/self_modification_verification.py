from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from orchestration.self_modification_policy import SelfModificationPolicyDecision


@dataclass(frozen=True)
class VerificationCheckResult:
    name: str
    status: str
    command: tuple[str, ...] = ()
    detail: str = ""


@dataclass(frozen=True)
class SelfModificationVerificationResult:
    status: str
    checks: tuple[VerificationCheckResult, ...] = ()

    @property
    def summary(self) -> str:
        return ", ".join(f"{check.name}:{check.status}" for check in self.checks)


def _run_command(command: tuple[str, ...], cwd: Path) -> VerificationCheckResult:
    completed = subprocess.run(
        list(command),
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=300,
    )
    detail = (completed.stdout or completed.stderr or "").strip()[:400]
    return VerificationCheckResult(
        name=command[2] if len(command) > 2 and command[1:3] == ("-m", "py_compile") else command[0],
        status="passed" if completed.returncode == 0 else "failed",
        command=command,
        detail=detail,
    )


def _crosshair_targets(project_root: Path, relative_path: str, test_targets: tuple[str, ...]) -> tuple[str, ...]:
    rel = Path(relative_path)
    candidates: list[str] = []
    direct = project_root / "tests" / f"test_{rel.stem}_contracts.py"
    if direct.exists():
        candidates.append(str(direct.relative_to(project_root)))
    parent = project_root / "tests" / f"test_{rel.parent.name}_contracts.py"
    if rel.parent.name and parent.exists():
        candidates.append(str(parent.relative_to(project_root)))
    for target in test_targets:
        candidate = target.replace(".py", "_contracts.py")
        candidate_path = project_root / candidate
        if candidate_path.exists():
            candidates.append(str(candidate_path.relative_to(project_root)))
    deduped: list[str] = []
    for candidate in candidates:
        if candidate not in deduped:
            deduped.append(candidate)
    return tuple(deduped)


def run_self_modification_verification(
    *,
    project_root: Path,
    relative_path: str,
    policy: SelfModificationPolicyDecision,
    pytest_runner: Callable[..., str],
) -> SelfModificationVerificationResult:
    checks: list[VerificationCheckResult] = []
    for check_name in policy.required_checks:
        if check_name == "py_compile":
            command = (sys.executable, "-m", "py_compile", relative_path)
            result = _run_command(command, cwd=project_root)
            checks.append(VerificationCheckResult("py_compile", result.status, command, result.detail))
        elif check_name == "pytest_targeted":
            status = pytest_runner(
                relative_path,
                policy_test_targets=policy.required_test_targets,
                project_root=project_root,
            )
            checks.append(VerificationCheckResult("pytest_targeted", status))
        elif check_name == "crosshair":
            targets = _crosshair_targets(project_root, relative_path, policy.required_test_targets)
            if not targets:
                checks.append(VerificationCheckResult("crosshair", "failed", detail="no_contract_targets"))
            else:
                command = (sys.executable, "-m", "crosshair", "check", *targets, "--analysis_kind=deal")
                result = _run_command(command, cwd=project_root)
                checks.append(VerificationCheckResult("crosshair", result.status, command, result.detail))
        elif check_name == "lean":
            ci_specs = project_root / "lean" / "CiSpecs.lean"
            if not ci_specs.exists():
                checks.append(VerificationCheckResult("lean", "failed", detail="missing_CiSpecs"))
            else:
                command = ("lean", "lean/CiSpecs.lean")
                result = _run_command(command, cwd=project_root)
                checks.append(VerificationCheckResult("lean", result.status, command, result.detail))
        elif check_name == "production_gates":
            command = (sys.executable, "scripts/run_production_gates.py")
            result = _run_command(command, cwd=project_root)
            checks.append(VerificationCheckResult("production_gates", result.status, command, result.detail))
        else:
            checks.append(VerificationCheckResult(check_name, "failed", detail="unknown_check"))
        if checks[-1].status != "passed":
            return SelfModificationVerificationResult(status="failed", checks=tuple(checks))
    return SelfModificationVerificationResult(status="passed", checks=tuple(checks))
