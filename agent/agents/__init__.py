"""Spezialisierte Timus-Agenten."""

from agent.agents.executor import ExecutorAgent
from agent.agents.research import DeepResearchAgent
from agent.agents.reasoning import ReasoningAgent
from agent.agents.creative import CreativeAgent
from agent.agents.developer import DeveloperAgent
from agent.agents.meta import MetaAgent
from agent.agents.visual import VisualAgent
from agent.agents.data import DataAgent
from agent.agents.document import DocumentAgent
from agent.agents.communication import CommunicationAgent
from agent.agents.system import SystemAgent
from agent.agents.shell import ShellAgent

__all__ = [
    "ExecutorAgent",
    "DeepResearchAgent",
    "ReasoningAgent",
    "CreativeAgent",
    "DeveloperAgent",
    "MetaAgent",
    "VisualAgent",
    "DataAgent",
    "DocumentAgent",
    "CommunicationAgent",
    "SystemAgent",
    "ShellAgent",
]
