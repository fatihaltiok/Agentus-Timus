"""DocumentAgent — Dokumenten-Spezialist für PDF, DOCX, XLSX, TXT."""

from __future__ import annotations

import re
import logging
from typing import Optional

from agent.base_agent import BaseAgent
from agent.prompts import DOCUMENT_PROMPT_TEMPLATE
from agent.shared.delegation_handoff import DelegationHandoff, parse_delegation_handoff

log = logging.getLogger("TimusAgent-v4.4")

# Reihenfolge: spezifischste Begriffe zuerst (DOCX vor PDF wegen "Angebot")
_FORMAT_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("XLSX", re.compile(r"\b(excel|xlsx|tabelle|spreadsheet|kalkulat)\b", re.I)),
    ("DOCX", re.compile(r"\b(word|docx|angebot|brief|letter|anschreiben|editierbar|lebenslauf)\b", re.I)),
    ("TXT",  re.compile(r"\b(txt|plaintext|notiz|entwurf|rohtext)\b", re.I)),
    ("PDF",  re.compile(r"\b(pdf|bericht|report|zusammenfassung|summary|protokoll|projektdoku)\b", re.I)),
]
_DEFAULT_FORMAT = "PDF"


def _detect_format(task: str) -> str:
    for fmt, pattern in _FORMAT_PATTERNS:
        if pattern.search(task):
            return fmt
    return _DEFAULT_FORMAT


class DocumentAgent(BaseAgent):
    def __init__(self, tools_description_string: str):
        super().__init__(
            DOCUMENT_PROMPT_TEMPLATE,
            tools_description_string,
            max_iterations=15,
            agent_type="document",
        )

    async def run(self, task: str) -> str:
        handoff = parse_delegation_handoff(task)
        effective_task = handoff.goal if handoff and handoff.goal else str(task or "").strip()
        handoff_context = self._build_delegation_document_context(handoff)
        fmt = _detect_format(effective_task)
        log.info(f"DocumentAgent | Format erkannt: {fmt}")
        parts = [effective_task, f"ERKANNTES_FORMAT: {fmt}"]
        if handoff_context:
            parts.append(handoff_context)
        return await super().run("\n\n".join(part for part in parts if part))

    def _build_delegation_document_context(self, handoff: Optional[DelegationHandoff]) -> str:
        if not handoff:
            return ""

        lines: list[str] = ["# STRUKTURIERTER DOCUMENT-HANDOFF"]
        if handoff.expected_output:
            lines.append(f"Erwarteter Output: {handoff.expected_output}")
        if handoff.success_signal:
            lines.append(f"Erfolgssignal: {handoff.success_signal}")
        if handoff.constraints:
            lines.append("Constraints: " + " | ".join(handoff.constraints))

        for key, label in (
            ("recipe_id", "Rezept"),
            ("stage_id", "Stage"),
            ("artifact_name", "Artefaktname"),
            ("output_format", "Zielformat"),
            ("source_urls", "Quell-URLs"),
            ("captured_context", "Bereits erfasster Kontext"),
            ("previous_stage_result", "Vorheriges Stage-Ergebnis"),
            ("previous_blackboard_key", "Blackboard-Key"),
        ):
            value = handoff.handoff_data.get(key)
            if value:
                lines.append(f"{label}: {value}")
        return "\n".join(lines)
