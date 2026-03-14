from orchestration.production_gates import (
    GateResult,
    P0_SMOKE_TESTS,
    P0_SYNTAX_TARGETS,
    blocking_gate_names,
    default_production_gates,
    format_gate_summary,
    normalize_gate_status,
    summarize_gate_results,
)
from utils.stable_hash import stable_hex_digest, stable_text_digest


def test_normalize_gate_status_falls_back_to_failed():
    assert normalize_gate_status("passed") == "passed"
    assert normalize_gate_status("skipped") == "skipped"
    assert normalize_gate_status("unknown") == "failed"


def test_default_production_gates_include_security_and_smoke(monkeypatch):
    monkeypatch.setenv("QDRANT_MODE", "embedded")
    gates = default_production_gates("python")
    names = [gate.name for gate in gates]
    assert names == [
        "syntax_compile",
        "security_bandit",
        "security_pip_audit",
        "production_smoke",
    ]
    assert blocking_gate_names(gates) == names


def test_default_production_gates_include_qdrant_health_in_server_mode(monkeypatch):
    monkeypatch.setenv("QDRANT_MODE", "server")
    monkeypatch.setenv("QDRANT_URL", "http://127.0.0.1:6333")

    gates = default_production_gates("python")
    names = [gate.name for gate in gates]

    assert names[-1] == "qdrant_server_health"
    assert gates[-1].command[-1] == "http://127.0.0.1:6333/readyz"


def test_p0_targets_are_nonempty():
    assert P0_SMOKE_TESTS
    assert P0_SYNTAX_TARGETS
    assert all(item.endswith(".py") for item in P0_SMOKE_TESTS)
    assert all(item.endswith(".py") for item in P0_SYNTAX_TARGETS)


def test_summarize_gate_results_tracks_blocking_failures():
    results = [
        GateResult(name="syntax_compile", status="passed", blocking=True),
        GateResult(name="security_bandit", status="failed", blocking=True),
        GateResult(name="production_smoke", status="skipped", blocking=False),
    ]
    summary = summarize_gate_results(results)
    assert summary == {
        "total": 3,
        "passed": 1,
        "failed": 1,
        "skipped": 1,
        "blocking_failed": 1,
        "ready": False,
    }


def test_format_gate_summary_ready():
    summary = format_gate_summary(
        [GateResult(name="syntax_compile", status="passed", blocking=True)]
    )
    assert summary.startswith("READY | total=1")


def test_stable_hash_digests_are_short_and_deterministic():
    payload = b"booking-ui-state"
    assert stable_hex_digest(payload, hex_chars=8) == stable_hex_digest(payload, hex_chars=8)
    assert len(stable_hex_digest(payload, hex_chars=8)) == 8
    assert len(stable_text_digest("booking-ui-state", hex_chars=12)) == 12
