"""DeveloperAgent - Code, Skripte, Dateien."""

from agent.base_agent import BaseAgent
from agent.prompts import DEVELOPER_SYSTEM_PROMPT


class DeveloperAgent(BaseAgent):
    def __init__(self, tools_description_string: str):
        super().__init__(DEVELOPER_SYSTEM_PROMPT, tools_description_string, 15, "developer")
