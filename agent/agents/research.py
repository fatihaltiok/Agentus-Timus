"""DeepResearchAgent - Tiefenrecherche."""

from typing import Optional
import httpx

from agent.base_agent import BaseAgent
from agent.prompts import DEEP_RESEARCH_PROMPT_TEMPLATE


class DeepResearchAgent(BaseAgent):
    def __init__(self, tools_description_string: str):
        super().__init__(DEEP_RESEARCH_PROMPT_TEMPLATE, tools_description_string, 8, "deep_research")
        self.http_client = httpx.AsyncClient(timeout=600.0)
        self.current_session_id: Optional[str] = None

    async def _call_tool(self, method: str, params: dict) -> dict:
        result = await super()._call_tool(method, params)
        if isinstance(result, dict) and "session_id" in result:
            self.current_session_id = result["session_id"]
        if method == "generate_research_report" and self.current_session_id:
            params.setdefault("session_id", self.current_session_id)
        return result
