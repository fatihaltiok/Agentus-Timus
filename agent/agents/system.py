"""SystemAgent — Log-Analyse, Prozesse, Systemressourcen, Service-Status."""

from agent.base_agent import BaseAgent
from agent.prompts import SYSTEM_PROMPT_TEMPLATE


class SystemAgent(BaseAgent):
    def __init__(self, tools_description_string: str):
        super().__init__(
            SYSTEM_PROMPT_TEMPLATE,
            tools_description_string,
            max_iterations=12,
            agent_type="system",
        )
