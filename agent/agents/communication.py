"""CommunicationAgent — E-Mails, Briefe, LinkedIn-Posts, Anschreiben."""

from agent.base_agent import BaseAgent
from agent.prompts import COMMUNICATION_PROMPT_TEMPLATE


class CommunicationAgent(BaseAgent):
    def __init__(self, tools_description_string: str):
        super().__init__(
            COMMUNICATION_PROMPT_TEMPLATE,
            tools_description_string,
            max_iterations=10,
            agent_type="communication",
        )
