"""P0 production-readiness gates for Timus.

Diese Phase kapselt die minimalen Blocker-Gates fuer produktionsnahen Betrieb:
- Syntax-/Import-Konsistenz
- Security-Scans
- kleine deterministische Smoke-Suite fuer Kernpfade
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Sequence

VALID_GATE_STATUSES = {"passed", "failed", "skipped"}

P0_SMOKE_TESTS: List[str] = [
    "tests/test_milestone5_quality_gates.py",
    "tests/test_milestone6_e2e_readiness.py",
    "tests/test_telegram_feedback_gateway.py",
    "tests/test_dispatcher_camera_intent.py",
    "tests/test_restart_service_hardening.py",
]

P0_SYNTAX_TARGETS: List[str] = [
    "main_dispatcher.py",
    "agent/base_agent.py",
    "agent/providers.py",
    "gateway/telegram_gateway.py",
    "orchestration/feedback_engine.py",
    "orchestration/production_gates.py",
    "server/mcp_server.py",
]


@dataclass(frozen=True)
class ProductionGate:
    name: str
    command: List[str]
    blocking: bool = True
    description: str = ""


@dataclass(frozen=True)
class GateResult:
    name: str
    status: str
    blocking: bool
    command: List[str] = field(default_factory=list)
    detail: str = ""


def normalize_gate_status(status: str) -> str:
    normalized = str(status or "").strip().lower()
    return normalized if normalized in VALID_GATE_STATUSES else "failed"


def summarize_gate_results(results: Sequence[GateResult]) -> Dict[str, Any]:
    total = len(results)
    passed = sum(1 for item in results if normalize_gate_status(item.status) == "passed")
    failed = sum(1 for item in results if normalize_gate_status(item.status) == "failed")
    skipped = sum(1 for item in results if normalize_gate_status(item.status) == "skipped")
    blocking_failed = sum(
        1
        for item in results
        if item.blocking and normalize_gate_status(item.status) == "failed"
    )
    return {
        "total": total,
        "passed": passed,
        "failed": failed,
        "skipped": skipped,
        "blocking_failed": blocking_failed,
        "ready": blocking_failed == 0 and failed == 0,
    }


def format_gate_summary(results: Sequence[GateResult]) -> str:
    summary = summarize_gate_results(results)
    status = "READY" if summary["ready"] else "NOT_READY"
    return (
        f"{status} | total={summary['total']} passed={summary['passed']} "
        f"failed={summary['failed']} skipped={summary['skipped']} "
        f"blocking_failed={summary['blocking_failed']}"
    )


def default_production_gates(python_executable: str = "python") -> List[ProductionGate]:
    return [
        ProductionGate(
            name="syntax_compile",
            command=[python_executable, "-m", "py_compile", *P0_SYNTAX_TARGETS],
            description="Syntax-/Import-Konsistenz fuer kritische Kernmodule",
        ),
        ProductionGate(
            name="security_bandit",
            command=[python_executable, "-m", "bandit", "-q", "-ll", "-r", "agent", "gateway", "orchestration", "server", "tools"],
            description="AST-basierter Security-Scan fuer Python-Code",
        ),
        ProductionGate(
            name="security_pip_audit",
            command=[
                python_executable,
                "-m",
                "pip_audit",
                "-r",
                "requirements.txt",
                "--progress-spinner",
                "off",
                "--disable-pip",
                "--no-deps",
            ],
            description="Dependency-Vulnerability-Scan",
        ),
        ProductionGate(
            name="production_smoke",
            command=[python_executable, "-m", "pytest", "-q", *P0_SMOKE_TESTS],
            description="Deterministische Smoke-Suite fuer Kernpfade",
        ),
    ]


def blocking_gate_names(gates: Iterable[ProductionGate]) -> List[str]:
    return [gate.name for gate in gates if gate.blocking]
