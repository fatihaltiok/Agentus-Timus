#!/usr/bin/env python3
# scripts/debug_deep_research.py
"""
CLI-Diagnose-Runner für Deep Research Engine v7.0.

Startet eine Research-Session mit vollständigem Diagnose-Output.
Kein Produktions-Eingriff — nutzt dieselbe Codebasis.

Usage:
    python scripts/debug_deep_research.py "self-monitoring AI agents"
    python scripts/debug_deep_research.py "Quantencomputer" --mode light
    python scripts/debug_deep_research.py "transformer architecture" --mode moderate --no-arxiv
"""

import argparse
import asyncio
import json
import sys
from pathlib import Path

# Timus-Root zum Pfad hinzufügen
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tools.deep_research.diagnostics import get_current, reset
from tools.deep_research.tool import start_deep_research


async def main(query: str, mode: str, no_arxiv: bool, output_json: bool) -> int:
    """Startet Research und gibt Diagnose aus. Exit-Code 0=OK, 1=Qualitäts-Gate failed."""
    import os
    if no_arxiv:
        os.environ["DEEP_RESEARCH_TRENDS_ENABLED"] = "false"

    diag = reset()
    diag.query = query
    diag.verification_mode_req = mode

    print(f"🔬 Starte Deep Research v7.0")
    print(f"   Query : {query}")
    print(f"   Modus : {mode}")
    print()

    try:
        result = await start_deep_research(
            query=query,
            verification_mode=mode,
        )
    except Exception as e:
        print(f"❌ Research fehlgeschlagen: {e}", file=sys.stderr)
        return 1

    diag.finish()

    if output_json:
        summary = diag.summary()
        summary["result_status"] = result.get("status")
        summary["result_verified_count"] = result.get("verified_count", 0)
        print(json.dumps(summary, indent=2, ensure_ascii=False))
    else:
        diag.print_report()
        print(f"Status  : {result.get('status')}")
        print(f"Report  : {result.get('report_filepath', 'nicht gespeichert')}")

    return 0 if diag.quality_gate_passed else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Deep Research v7.0 Diagnose-CLI")
    parser.add_argument("query", help="Suchanfrage")
    parser.add_argument("--mode", default="strict", choices=["strict", "moderate", "light"],
                        help="Verifikations-Modus (default: strict)")
    parser.add_argument("--no-arxiv", action="store_true",
                        help="ArXiv-Recherche deaktivieren")
    parser.add_argument("--json", action="store_true", dest="output_json",
                        help="Diagnose als JSON ausgeben")
    args = parser.parse_args()

    exit_code = asyncio.run(main(args.query, args.mode, args.no_arxiv, args.output_json))
    sys.exit(exit_code)
