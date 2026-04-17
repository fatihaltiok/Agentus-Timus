from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path


project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from orchestration.phase_f_runtime_board import collect_phase_f_runtime_board, render_phase_f_runtime_board


async def _run() -> dict:
    return await collect_phase_f_runtime_board()


def main() -> int:
    parser = argparse.ArgumentParser(description="Builds the machine-readable Phase F runtime/lane board.")
    parser.add_argument("--json", action="store_true", help="Emit JSON instead of text.")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Return non-zero when the board state is not ok.",
    )
    args = parser.parse_args()

    board = asyncio.run(_run())
    if args.json:
        print(json.dumps(board, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(render_phase_f_runtime_board(board))

    state = str((board.get("summary") or {}).get("state") or "unknown").strip().lower()
    return 1 if args.strict and state != "ok" else 0


if __name__ == "__main__":
    raise SystemExit(main())
