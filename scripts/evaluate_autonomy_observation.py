from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from orchestration.autonomy_observation import (
    build_autonomy_observation_summary,
    get_incident_trace,
    render_autonomy_observation_markdown,
)


_TRACE_CORRELATION_FIELDS = (
    "request_id",
    "task_id",
    "session_id",
    "agent",
    "source",
    "route_source",
    "decision_source",
    "incident_key",
    "error_class",
    "query_preview",
    "description_preview",
    "error",
)


def _render_incident_trace_markdown(request_id: str, trace: list) -> str:
    lines = [
        f"# Incident-Trace: `{request_id}`",
        "",
        f"Events: {len(trace)}",
        "",
    ]
    if not trace:
        lines.append("_Keine Events gefunden._")
        return "\n".join(lines)
    for i, event in enumerate(trace, 1):
        payload = dict(event.get("payload") or {})
        lines.append(
            f"**{i}.** `{event.get('event_type', '?')}` — `{event.get('observed_at', '?')}`"
        )
        for key in _TRACE_CORRELATION_FIELDS:
            val = str(payload.get(key) or "").strip()
            if val:
                lines.append(f"   - {key}: `{val[:160]}`")
        lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Wertet das laufende Timus-Autonomiebeobachtungsfenster aus.")
    parser.add_argument("--since", default="", help="Optionales ISO-Startdatum fuer die Auswertung.")
    parser.add_argument("--until", default="", help="Optionales ISO-Enddatum fuer die Auswertung.")
    parser.add_argument(
        "--output",
        default="",
        help="Optionaler Dateipfad fuer einen Markdown-Report, z. B. results/autonomy_observation_week1.md",
    )
    parser.add_argument(
        "--request-id",
        default="",
        dest="request_id",
        help="Incident-Trace fuer eine einzelne request_id ausgeben statt des vollen Reports.",
    )
    args = parser.parse_args()

    # Incident-Trace-Modus: einzelne request_id nachverfolgen
    if args.request_id:
        trace = get_incident_trace(args.request_id.strip(), since=args.since, until=args.until)
        markdown = _render_incident_trace_markdown(args.request_id.strip(), trace)
        print(markdown, end="")
        if args.output:
            output_path = Path(args.output)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(markdown, encoding="utf-8")
        return 0

    # Normal-Modus: vollständiger Observation-Report
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
