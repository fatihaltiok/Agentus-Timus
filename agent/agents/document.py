"""DocumentAgent — Dokumenten-Spezialist für PDF, DOCX, XLSX, TXT."""

from agent.base_agent import BaseAgent
from agent.prompts import DOCUMENT_PROMPT_TEMPLATE


class DocumentAgent(BaseAgent):
    def __init__(self, tools_description_string: str):
        super().__init__(
            DOCUMENT_PROMPT_TEMPLATE,
            tools_description_string,
            max_iterations=15,
            agent_type="document",
        )
