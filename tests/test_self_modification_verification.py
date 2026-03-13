from pathlib import Path

from orchestration.self_modification_policy import evaluate_self_modification_policy
from orchestration.self_modification_verification import run_self_modification_verification


def test_verification_runs_required_checks(monkeypatch, tmp_path: Path) -> None:
    project = tmp_path
    (project / "orchestration").mkdir(parents=True)
    (project / "tests").mkdir(parents=True)
    (project / "lean").mkdir(parents=True)
    (project / "scripts").mkdir(parents=True)
    (project / "orchestration" / "meta_orchestration.py").write_text("def demo():\n    return 1\n", encoding="utf-8")
    (project / "tests" / "test_meta_orchestration_contracts.py").write_text("def test_ok():\n    assert True\n", encoding="utf-8")
    (project / "lean" / "CiSpecs.lean").write_text("-- ok\n", encoding="utf-8")
    (project / "scripts" / "run_production_gates.py").write_text("print('ok')\n", encoding="utf-8")
    calls: list[tuple[str, ...]] = []

    def _fake_command(command: tuple[str, ...], cwd: Path):
        calls.append(command)
        from orchestration.self_modification_verification import VerificationCheckResult

        return VerificationCheckResult(name=command[0], status="passed", command=command)

    monkeypatch.setattr("orchestration.self_modification_verification._run_command", _fake_command)
    result = run_self_modification_verification(
        project_root=project,
        relative_path="orchestration/meta_orchestration.py",
        policy=evaluate_self_modification_policy("orchestration/meta_orchestration.py"),
        pytest_runner=lambda *_args, **_kwargs: "passed",
    )
    assert result.status == "passed"
    assert [check.name for check in result.checks] == [
        "py_compile",
        "pytest_targeted",
        "crosshair",
        "lean",
        "production_gates",
    ]
    assert any("crosshair" in command for command in calls)


def test_verification_fails_without_contract_targets(monkeypatch, tmp_path: Path) -> None:
    project = tmp_path
    (project / "orchestration").mkdir(parents=True)
    (project / "tests").mkdir(parents=True)
    (project / "lean").mkdir(parents=True)
    (project / "scripts").mkdir(parents=True)
    (project / "orchestration" / "meta_orchestration.py").write_text("def demo():\n    return 1\n", encoding="utf-8")
    (project / "lean" / "CiSpecs.lean").write_text("-- ok\n", encoding="utf-8")
    (project / "scripts" / "run_production_gates.py").write_text("print('ok')\n", encoding="utf-8")

    def _fake_command(command: tuple[str, ...], cwd: Path):
        from orchestration.self_modification_verification import VerificationCheckResult

        return VerificationCheckResult(name=command[0], status="passed", command=command)

    monkeypatch.setattr("orchestration.self_modification_verification._run_command", _fake_command)
    result = run_self_modification_verification(
        project_root=project,
        relative_path="orchestration/meta_orchestration.py",
        policy=evaluate_self_modification_policy("orchestration/meta_orchestration.py"),
        pytest_runner=lambda *_args, **_kwargs: "passed",
    )
    assert result.status == "failed"
    assert any(check.name == "crosshair" and check.detail == "no_contract_targets" for check in result.checks)
