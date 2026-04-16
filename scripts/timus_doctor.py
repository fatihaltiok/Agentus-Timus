#!/usr/bin/env python3
"""Unified Timus stack doctor for operators and automation."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from orchestration.timus_doctor import collect_timus_doctor_report, render_timus_doctor_report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Unified Timus stack doctor.")
    parser.add_argument("--json", action="store_true", help="Machine-readable JSON output")
    parser.add_argument("--strict", action="store_true", help="Return non-zero if doctor does not report ready=true")
    parser.add_argument("--mcp-base-url", default="", help="Override MCP base URL, e.g. http://127.0.0.1:5000")
    parser.add_argument("--dispatcher-health-url", default="", help="Override dispatcher health URL")
    args = parser.parse_args(argv)

    report = asyncio.run(
        collect_timus_doctor_report(
            mcp_base_url=str(args.mcp_base_url or "").strip() or None,
            dispatcher_health_url=str(args.dispatcher_health_url or "").strip() or None,
        )
    )
    if args.json:
        print(json.dumps(report, ensure_ascii=True, indent=2))
    else:
        print(render_timus_doctor_report(report))
    return 0 if (not args.strict or bool(report.get("ready"))) else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
