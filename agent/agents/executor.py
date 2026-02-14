"""ExecutorAgent - Schnelle einfache Tasks."""

from agent.base_agent import BaseAgent
from agent.prompts import EXECUTOR_PROMPT_TEMPLATE


class ExecutorAgent(BaseAgent):
    def __init__(self, tools_description_string: str):
        super().__init__(EXECUTOR_PROMPT_TEMPLATE, tools_description_string, 30, "executor")
