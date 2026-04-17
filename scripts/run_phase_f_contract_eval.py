from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from orchestration.phase_f_contract_eval import run_phase_f_contract_eval


def _render_text_report(report: dict[str, object]) -> str:
    summary = dict(report.get("summary") or {})
    lines = [
        "Phase F Contract Eval",
        f"contract_version: {report.get('contract_version', '')}",
        f"state: {summary.get('state', 'unknown')}",
        f"total: {summary.get('total', 0)}",
        f"passed: {summary.get('passed', 0)}",
        f"failed: {summary.get('failed', 0)}",
    ]
    failed_contracts = list(summary.get("failed_contracts") or [])
    if failed_contracts:
        lines.append("failed_contracts: " + ", ".join(str(item) for item in failed_contracts))

    lines.append("")
    lines.append("Contracts:")
    for item in report.get("results") or []:
        evidence = dict(item.get("evidence") or {})
        lines.append(
            f"- {item.get('contract_id', '')}: "
            f"{'PASS' if item.get('passed') else 'FAIL'} "
            f"(reason={item.get('reason', '')}, checks={item.get('check_count', 0)})"
        )
        if evidence:
            lines.append(
                "  evidence: "
                + ", ".join(f"{key}={value}" for key, value in list(evidence.items())[:3])
            )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Runs the deterministic Phase F architecture and behavior contracts.")
    parser.add_argument("--json", action="store_true", help="Emit JSON instead of text.")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Return non-zero when any contract fails.",
    )
    args = parser.parse_args()

    report = run_phase_f_contract_eval()
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(_render_text_report(report))

    failed = int(dict(report.get("summary") or {}).get("failed", 0) or 0)
    return 1 if args.strict and failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
