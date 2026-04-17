from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from orchestration.canvas_chat_parity_harness import run_canvas_chat_parity_harness_sync


def _render_text_report(report: dict) -> str:
    summary = dict(report.get("summary") or {})
    lines = [
        "Canvas Chat Parity Harness",
        f"contract_version: {report.get('contract_version', '')}",
        f"total: {summary.get('total', 0)}",
        f"passed: {summary.get('passed', 0)}",
        f"failed: {summary.get('failed', 0)}",
    ]
    failed_scenarios = list(summary.get("failed_scenarios") or [])
    if failed_scenarios:
        lines.append("failed_scenarios: " + ", ".join(str(item) for item in failed_scenarios))

    lines.append("")
    lines.append("Scenarios:")
    for item in report.get("results") or []:
        evaluation = dict(item.get("evaluation") or {})
        response = dict(item.get("response") or {})
        lines.append(
            f"- {item.get('scenario_id', '')}: "
            f"{'PASS' if evaluation.get('passed') else 'FAIL'} "
            f"(status={response.get('status', '')}, checks={', '.join(evaluation.get('checks') or [])})"
        )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Runs the deterministic /chat parity harness.")
    parser.add_argument("--json", action="store_true", help="Emit JSON instead of text.")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Return non-zero when any scenario fails.",
    )
    args = parser.parse_args()

    report = run_canvas_chat_parity_harness_sync()
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(_render_text_report(report))

    failed = int(dict(report.get("summary") or {}).get("failed", 0) or 0)
    return 1 if args.strict and failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
