"""DataAgent — Datenanalyst für CSV, XLSX, JSON."""

from agent.base_agent import BaseAgent
from agent.prompts import DATA_PROMPT_TEMPLATE


class DataAgent(BaseAgent):
    def __init__(self, tools_description_string: str):
        super().__init__(
            DATA_PROMPT_TEMPLATE,
            tools_description_string,
            max_iterations=20,
            agent_type="data",
        )
