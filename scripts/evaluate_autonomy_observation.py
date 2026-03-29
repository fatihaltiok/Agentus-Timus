from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from orchestration.autonomy_observation import (
    build_autonomy_observation_summary,
    render_autonomy_observation_markdown,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Wertet das laufende Timus-Autonomiebeobachtungsfenster aus.")
    parser.add_argument("--since", default="", help="Optionales ISO-Startdatum fuer die Auswertung.")
    parser.add_argument("--until", default="", help="Optionales ISO-Enddatum fuer die Auswertung.")
    parser.add_argument(
        "--output",
        default="",
        help="Optionaler Dateipfad fuer einen Markdown-Report, z. B. results/autonomy_observation_week1.md",
    )
    args = parser.parse_args()

    summary = build_autonomy_observation_summary(since=args.since, until=args.until)
    markdown = render_autonomy_observation_markdown(summary)
    print(markdown, end="")

    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(markdown, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
