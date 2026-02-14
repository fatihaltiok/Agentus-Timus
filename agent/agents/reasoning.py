"""ReasoningAgent - Komplexe Analyse mit Nemotron."""

import os
import logging

from agent.base_agent import BaseAgent
from agent.prompts import REASONING_PROMPT_TEMPLATE

log = logging.getLogger("TimusAgent-v4.4")


class ReasoningAgent(BaseAgent):
    def __init__(self, tools_description_string: str, enable_thinking: bool = True):
        os.environ["NEMOTRON_ENABLE_THINKING"] = "true" if enable_thinking else "false"
        super().__init__(REASONING_PROMPT_TEMPLATE, tools_description_string, 10, "reasoning")
        log.info(f"ReasoningAgent | enable_thinking={enable_thinking}")

    async def analyze(self, problem: str, context: str = "") -> str:
        prompt = f"Analysiere:\n\nPROBLEM:\n{problem}"
        if context:
            prompt += f"\n\nKONTEXT:\n{context}"
        return await self.run(prompt)
