from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from orchestration.autonomy_observation import start_autonomy_observation


def main() -> int:
    parser = argparse.ArgumentParser(description="Startet eine strukturierte Timus-Autonomiebeobachtung.")
    parser.add_argument("--label", default="phase3_phase4_weekly", help="Label fuer das Beobachtungsfenster.")
    parser.add_argument("--days", type=int, default=7, help="Dauer des Beobachtungsfensters in Tagen.")
    args = parser.parse_args()

    state = start_autonomy_observation(label=args.label, duration_days=args.days)
    print(f"label={state['label']}")
    print(f"started_at={state['started_at']}")
    print(f"ends_at={state['ends_at']}")
    print(f"log_path={state['log_path']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
