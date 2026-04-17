from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from orchestration.phase_f_parity_harness_suite import run_phase_f_parity_harness_suite


def _render_text_report(report: dict) -> str:
    summary = dict(report.get("summary") or {})
    lines = [
        "Phase F Parity Harness Suite",
        f"contract_version: {report.get('contract_version', '')}",
        f"suite_total: {summary.get('suite_total', 0)}",
        f"suite_passed: {summary.get('suite_passed', 0)}",
        f"suite_failed: {summary.get('suite_failed', 0)}",
        f"scenario_total: {summary.get('scenario_total', 0)}",
        f"scenario_failed: {summary.get('scenario_failed', 0)}",
    ]
    failed_suites = list(summary.get("failed_suites") or [])
    if failed_suites:
        lines.append("failed_suites: " + ", ".join(str(item) for item in failed_suites))

    lines.append("")
    lines.append("Suites:")
    for item in report.get("results") or []:
        suite_summary = dict(item.get("summary") or {})
        lines.append(
            f"- {item.get('suite_id', '')}: "
            f"{'PASS' if item.get('passed') else 'FAIL'} "
            f"(scenarios={suite_summary.get('total', 0)}, failed={suite_summary.get('failed', 0)})"
        )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Runs the unified Phase F parity harness suite.")
    parser.add_argument("--json", action="store_true", help="Emit JSON instead of text.")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Return non-zero when any suite fails.",
    )
    args = parser.parse_args()

    report = run_phase_f_parity_harness_suite()
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(_render_text_report(report))

    failed = int(dict(report.get("summary") or {}).get("suite_failed", 0) or 0)
    return 1 if args.strict and failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
