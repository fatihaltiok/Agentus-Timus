"""ReasoningAgent - Komplexe Analyse mit Nemotron."""

import os
import re
import logging

from agent.base_agent import BaseAgent
from agent.prompts import REASONING_PROMPT_TEMPLATE

log = logging.getLogger("TimusAgent-v4.4")

# Reihenfolge matters: spezifischste zuerst
_PROBLEM_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("Sicherheits-Review", re.compile(
        r"\b(sicherheit|security|injection|secret|token|passwort|password|cve|vulnerab|hardcoded)\b", re.I
    )),
    ("Root-Cause Debugging", re.compile(
        r"\b(fehler|bug|error|exception|traceback|crash|absturz|bricht.?ab|funktioniert.?nicht)\b", re.I
    )),
    ("Performance-Analyse", re.compile(
        r"\b(langsam|slow|performance|latenz|latency|timeout|speicher|memory leak|n\+1)\b", re.I
    )),
    ("Architektur-Review", re.compile(
        r"\b(architektur|architecture|design|refactor|struktur|muster|pattern|abhängigkeit)\b", re.I
    )),
    ("Multi-Step Planung", re.compile(
        r"\b(plan|planung|roadmap|vorgehen|schritte|steps|ablauf|workflow|strategie)\b", re.I
    )),
]


def _detect_problem_type(task: str) -> str:
    for label, pattern in _PROBLEM_PATTERNS:
        if pattern.search(task):
            return label
    return "Analyse"


class ReasoningAgent(BaseAgent):
    def __init__(self, tools_description_string: str, enable_thinking: bool = True):
        os.environ["NEMOTRON_ENABLE_THINKING"] = "true" if enable_thinking else "false"
        super().__init__(REASONING_PROMPT_TEMPLATE, tools_description_string, 15, "reasoning")
        log.info(f"ReasoningAgent | enable_thinking={enable_thinking}")

    async def run(self, task: str) -> str:
        problem_type = _detect_problem_type(task)
        log.info(f"ReasoningAgent | Typ erkannt: {problem_type}")
        return await super().run(f"PROBLEM_TYP: {problem_type}\n\n{task}")

    async def analyze(self, problem: str, context: str = "") -> str:
        prompt = f"Analysiere:\n\nPROBLEM:\n{problem}"
        if context:
            prompt += f"\n\nKONTEXT:\n{context}"
        return await self.run(prompt)
