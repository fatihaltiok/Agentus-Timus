from pathlib import Path

from orchestration.self_modification_canary import run_self_modification_canary
from orchestration.self_modification_policy import evaluate_self_modification_policy


def test_canary_runs_targeted_checks_and_gates(monkeypatch, tmp_path: Path) -> None:
    project = tmp_path
    (project / "orchestration").mkdir(parents=True)
    (project / "tests").mkdir(parents=True)
    (project / "scripts").mkdir(parents=True)
    (project / "orchestration" / "meta_orchestration.py").write_text("def demo():\n    return 1\n", encoding="utf-8")
    (project / "scripts" / "run_production_gates.py").write_text("print('ok')\n", encoding="utf-8")
    calls: list[tuple[str, ...]] = []

    def _fake_command(command: tuple[str, ...], cwd: Path):
        calls.append(command)
        from orchestration.self_modification_canary import CanaryCheckResult

        return CanaryCheckResult(name=command[0], status="passed", command=command)

    monkeypatch.setattr("orchestration.self_modification_canary._run_command", _fake_command)
    result = run_self_modification_canary(
        project_root=project,
        relative_path="orchestration/meta_orchestration.py",
        policy=evaluate_self_modification_policy("orchestration/meta_orchestration.py"),
        pytest_runner=lambda *_args, **_kwargs: "passed",
    )
    assert result.state == "passed"
    assert [check.name for check in result.checks] == ["py_compile", "pytest_targeted", "production_gates"]
    assert any(command[-1].endswith("run_production_gates.py") for command in calls)


def test_canary_requests_rollback_when_targeted_tests_fail(tmp_path: Path) -> None:
    project = tmp_path
    (project / "orchestration").mkdir(parents=True)
    (project / "scripts").mkdir(parents=True)
    (project / "orchestration" / "meta_orchestration.py").write_text("def demo():\n    return 1\n", encoding="utf-8")
    (project / "scripts" / "run_production_gates.py").write_text("print('ok')\n", encoding="utf-8")

    result = run_self_modification_canary(
        project_root=project,
        relative_path="orchestration/meta_orchestration.py",
        policy=evaluate_self_modification_policy("orchestration/meta_orchestration.py"),
        pytest_runner=lambda *_args, **_kwargs: "failed",
    )
    assert result.state == "failed"
    assert result.rollback_required is True
    assert any(check.name == "pytest_targeted" and check.status == "failed" for check in result.checks)
