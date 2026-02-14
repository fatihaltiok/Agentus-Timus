# agent/timus_consolidated.py (VERSION v5.0 - Re-Export Shim)
"""
Backwards-Compatibility: Importiert aus aufgeteilten Modulen.

Die eigentliche Implementierung befindet sich jetzt in:
- agent/providers.py       (ModelProvider, MultiProviderClient, AgentModelConfig)
- agent/prompts.py         (System Prompts)
- agent/base_agent.py      (BaseAgent)
- agent/agents/            (Spezialisierte Agenten)
- agent/shared/            (Shared Utilities)
"""

import sys
from pathlib import Path

# --- Pfad-Setup ---
try:
    CURRENT_SCRIPT_PATH = Path(__file__).resolve()
    PROJECT_ROOT = CURRENT_SCRIPT_PATH.parent.parent
    if str(PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(PROJECT_ROOT))
except NameError:
    PROJECT_ROOT = Path.cwd()

from agent.providers import (
    ModelProvider,
    MultiProviderClient,
    AgentModelConfig,
    get_provider_client,
)
from agent.base_agent import BaseAgent, AGENT_CAPABILITY_MAP
from agent.agents import (
    ExecutorAgent,
    DeepResearchAgent,
    ReasoningAgent,
    CreativeAgent,
    DeveloperAgent,
    MetaAgent,
    VisualAgent,
)

__all__ = [
    "ModelProvider",
    "MultiProviderClient",
    "AgentModelConfig",
    "get_provider_client",
    "BaseAgent",
    "AGENT_CAPABILITY_MAP",
    "ExecutorAgent",
    "DeepResearchAgent",
    "ReasoningAgent",
    "CreativeAgent",
    "DeveloperAgent",
    "MetaAgent",
    "VisualAgent",
]
