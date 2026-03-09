from types import SimpleNamespace

import scripts.run_production_gates as runner
from orchestration.production_gates import ProductionGate


def test_run_gate_skips_missing_security_tool_when_allowed(monkeypatch):
    gate = ProductionGate(name="security_bandit", command=["python", "-m", "bandit"])
    monkeypatch.setattr(runner, "_is_missing_optional_gate", lambda _gate: True)

    result = runner._run_gate(gate, allow_missing_security_tools=True)

    assert result.status == "skipped"
    assert result.blocking is False


def test_run_gate_fails_on_nonzero_exit(monkeypatch):
    gate = ProductionGate(name="syntax_compile", command=["python", "-m", "py_compile", "x.py"])
    monkeypatch.setattr(runner, "_is_missing_optional_gate", lambda _gate: False)
    monkeypatch.setattr(
        runner.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(returncode=1, stdout="", stderr="boom"),
    )

    result = runner._run_gate(gate, allow_missing_security_tools=False)

    assert result.status == "failed"
    assert result.detail == "boom"
