"""
ResultAggregator — Formatiert und injiziert Fan-In-Ergebnisse.

Macht parallele Ergebnisse für den MetaAgenten lesbar.
Timus SessionMemory.add_message() hat kein metadata-Parameter —
daher wird der formatierte Block als System-Nachricht injiziert.
"""
from typing import Dict, Any, List


class ResultAggregator:

    @staticmethod
    def format_results(aggregated: Dict[str, Any]) -> str:
        """Erstellt LLM-lesbare Markdown-Zusammenfassung der parallelen Ergebnisse."""
        results: List[Dict] = aggregated.get("results", [])
        lines = [
            "## Parallele Delegation — Ergebnisse",
            f"**TraceID:** {aggregated.get('trace_id', 'N/A')}",
            f"**Status:** {aggregated.get('summary', '')}",
            "",
        ]

        for r in results:
            task_id = r.get("task_id", "?")
            agent   = r.get("agent", "?")
            status  = r.get("status", "?").upper()
            content = r.get("result", r.get("error", ""))

            lines.append(f"### [{task_id}] {agent} → {status}")
            if content:
                # Max 800 Zeichen pro Ergebnis — Context-Window schonen
                lines.append(str(content)[:800])
            lines.append("")

        return "\n".join(lines)

    @staticmethod
    def inject_into_session(session_memory, aggregated: Dict[str, Any]) -> None:
        """
        Injiziert Ergebnisse als EINEN Block ins SessionMemory.

        Timus SessionMemory.add_message() hat kein metadata-Parameter —
        daher wird nur role + content übergeben.
        """
        formatted = ResultAggregator.format_results(aggregated)
        session_memory.add_message(
            role="system",
            content=formatted,
        )

    @staticmethod
    def success_count(aggregated: Dict[str, Any]) -> int:
        return aggregated.get("success", 0)

    @staticmethod
    def has_errors(aggregated: Dict[str, Any]) -> bool:
        return aggregated.get("errors", 0) > 0

    @staticmethod
    def has_partial(aggregated: Dict[str, Any]) -> bool:
        return aggregated.get("partial", 0) > 0
