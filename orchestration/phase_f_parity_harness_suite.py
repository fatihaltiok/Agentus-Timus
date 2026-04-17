"""Unified Phase F F3 parity harness suite."""

from __future__ import annotations

from typing import Any, Callable, Mapping, Sequence

from orchestration.approval_auth_handover_parity_harness import (
    run_approval_auth_handover_parity_harness,
)
from orchestration.canvas_chat_parity_harness import run_canvas_chat_parity_harness_sync
from orchestration.delegation_parity_harness import run_delegation_parity_harness_sync
from orchestration.longrunner_queue_parity_harness import run_longrunner_queue_parity_harness


PHASE_F_PARITY_HARNESS_SUITE_VERSION = "phase_f_parity_harness_suite_v1"


def _suite_builders() -> tuple[tuple[str, Callable[[], dict[str, Any]]], ...]:
    return (
        ("canvas_chat", run_canvas_chat_parity_harness_sync),
        ("approval_auth_handover", run_approval_auth_handover_parity_harness),
        ("delegation", run_delegation_parity_harness_sync),
        ("longrunner_queue", run_longrunner_queue_parity_harness),
    )


def summarize_phase_f_parity_suite(results: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    rows = [dict(item or {}) for item in list(results or [])]
    suite_total = len(rows)
    suite_passed = sum(1 for row in rows if bool(row.get("passed")))
    suite_failed = max(0, suite_total - suite_passed)
    scenario_total = 0
    scenario_failed = 0
    failed_suites: list[str] = []
    for row in rows:
        summary = dict(row.get("summary") or {})
        scenario_total += int(summary.get("total") or 0)
        scenario_failed += int(summary.get("failed") or 0)
        if not bool(row.get("passed")):
            failed_suites.append(str(row.get("suite_id") or ""))
    return {
        "state": "pass" if suite_failed == 0 and scenario_failed == 0 else "fail",
        "suite_total": suite_total,
        "suite_passed": suite_passed,
        "suite_failed": suite_failed,
        "scenario_total": scenario_total,
        "scenario_failed": scenario_failed,
        "failed_suites": [item for item in failed_suites if item],
    }


def run_phase_f_parity_harness_suite(
    *,
    selected_suites: Sequence[str] | None = None,
) -> dict[str, Any]:
    requested = {str(item or "").strip().lower() for item in list(selected_suites or []) if str(item or "").strip()}
    results: list[dict[str, Any]] = []
    for suite_id, runner in _suite_builders():
        if requested and suite_id not in requested:
            continue
        report = runner()
        summary = dict(report.get("summary") or {})
        results.append(
            {
                "suite_id": suite_id,
                "contract_version": str(report.get("contract_version") or ""),
                "passed": int(summary.get("failed") or 0) == 0,
                "summary": summary,
                "report": report,
            }
        )
    return {
        "contract_version": PHASE_F_PARITY_HARNESS_SUITE_VERSION,
        "results": results,
        "summary": summarize_phase_f_parity_suite(results),
    }
