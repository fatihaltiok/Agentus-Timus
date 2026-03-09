#!/usr/bin/env python3
"""Runs the P0 production-readiness gates locally or in CI."""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import List

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from orchestration.production_gates import (
    GateResult,
    ProductionGate,
    default_production_gates,
    format_gate_summary,
    normalize_gate_status,
)


def _module_available(module_name: str) -> bool:
    try:
        return importlib.util.find_spec(module_name) is not None
    except ModuleNotFoundError:
        return False


def _is_missing_optional_gate(gate: ProductionGate) -> bool:
    if gate.name == "security_bandit":
        return not _module_available("bandit")
    if gate.name == "security_pip_audit":
        return not (_module_available("pip_audit") or _module_available("pip_audit._cli"))
    return False


def _run_gate(gate: ProductionGate, *, allow_missing_security_tools: bool) -> GateResult:
    if _is_missing_optional_gate(gate):
        if allow_missing_security_tools:
            return GateResult(
                name=gate.name,
                status="skipped",
                blocking=False,
                command=list(gate.command),
                detail="security tool not installed locally",
            )
        return GateResult(
            name=gate.name,
            status="failed",
            blocking=gate.blocking,
            command=list(gate.command),
            detail="required security tool is missing",
        )

    env = os.environ.copy()
    env.setdefault("XDG_CACHE_HOME", "/tmp/timus-production-gates-cache")
    env.setdefault("PIP_AUDIT_CACHE_DIR", "/tmp/timus-production-gates-cache/pip-audit")

    completed = subprocess.run(
        gate.command,
        capture_output=True,
        text=True,
        env=env,
    )
    detail = (completed.stdout or completed.stderr or "").strip()[:1200]
    return GateResult(
        name=gate.name,
        status="passed" if completed.returncode == 0 else "failed",
        blocking=gate.blocking,
        command=list(gate.command),
        detail=detail,
    )


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run Timus P0 production gates.")
    parser.add_argument(
        "--allow-missing-security-tools",
        action="store_true",
        help="Mark missing bandit/pip-audit as skipped instead of failed.",
    )
    args = parser.parse_args(argv)

    gates = default_production_gates(sys.executable)
    results = [
        _run_gate(gate, allow_missing_security_tools=args.allow_missing_security_tools)
        for gate in gates
    ]
    payload = {
        "summary": format_gate_summary(results),
        "results": [
            {
                "name": item.name,
                "status": normalize_gate_status(item.status),
                "blocking": item.blocking,
                "command": item.command,
                "detail": item.detail,
            }
            for item in results
        ],
    }
    print(json.dumps(payload, ensure_ascii=True, indent=2))
    return 0 if all(item.status == "passed" or normalize_gate_status(item.status) == "skipped" for item in results if not item.blocking) and all(normalize_gate_status(item.status) == "passed" for item in results if item.blocking) else 1


if __name__ == "__main__":
    raise SystemExit(main())
