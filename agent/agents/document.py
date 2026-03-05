"""DocumentAgent — Dokumenten-Spezialist für PDF, DOCX, XLSX, TXT."""

import re
import logging

from agent.base_agent import BaseAgent
from agent.prompts import DOCUMENT_PROMPT_TEMPLATE

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
        fmt = _detect_format(task)
        log.info(f"DocumentAgent | Format erkannt: {fmt}")
        return await super().run(f"ERKANNTES_FORMAT: {fmt}\n\n{task}")
