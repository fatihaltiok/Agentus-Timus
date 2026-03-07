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
            content = r.get("result") or r.get("error", "")
            artifacts = r.get("artifacts", []) or []
            metadata = r.get("metadata", {}) or {}
            quality = r.get("quality")
            blackboard_key = r.get("blackboard_key", "")

            lines.append(f"### [{task_id}] {agent} → {status}")
            if quality is not None:
                lines.append(f"Quality: {quality}")
            if blackboard_key:
                lines.append(f"Blackboard: {blackboard_key}")
            if content:
                # Max 800 Zeichen pro Ergebnis — Context-Window schonen
                lines.append(str(content)[:800])
            if artifacts:
                lines.append("Artifacts:")
                for item in artifacts[:5]:
                    if not isinstance(item, dict):
                        continue
                    path = str(item.get("path", ""))[:200]
                    artifact_type = str(item.get("type", "file"))
                    lines.append(f"- {artifact_type}: {path}")
            elif metadata:
                lines.append("Metadata:")
                for key, value in list(metadata.items())[:5]:
                    lines.append(f"- {key}: {str(value)[:200]}")
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
