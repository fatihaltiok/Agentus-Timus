"""Multi-Provider Infrastruktur fuer Timus-Agenten.

Enthaelt:
- ModelProvider Enum
- MultiProviderClient (Lazy Init)
- AgentModelConfig
- get_provider_client() Factory
"""

import os
import logging
from typing import Dict, Any, Optional, Tuple
from enum import Enum

log = logging.getLogger("TimusAgent-v4.4")


class ModelProvider(str, Enum):
    """Unterstuetzte LLM-Provider."""
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    DEEPSEEK = "deepseek"
    INCEPTION = "inception"
    NVIDIA = "nvidia"
    OPENROUTER = "openrouter"
    GOOGLE = "google"


class MultiProviderClient:
    """
    Verwaltet API-Clients fuer verschiedene LLM-Provider.
    Lazy Initialization - Clients werden erst bei Bedarf erstellt.
    """

    BASE_URLS = {
        ModelProvider.OPENAI: "https://api.openai.com/v1",
        ModelProvider.ANTHROPIC: "https://api.anthropic.com",
        ModelProvider.DEEPSEEK: "https://api.deepseek.com/v1",
        ModelProvider.INCEPTION: "https://api.inceptionlabs.ai/v1",
        ModelProvider.NVIDIA: "https://integrate.api.nvidia.com/v1",
        ModelProvider.OPENROUTER: "https://openrouter.ai/api/v1",
        ModelProvider.GOOGLE: "https://generativelanguage.googleapis.com/v1beta",
    }

    API_KEY_ENV = {
        ModelProvider.OPENAI: "OPENAI_API_KEY",
        ModelProvider.ANTHROPIC: "ANTHROPIC_API_KEY",
        ModelProvider.DEEPSEEK: "DEEPSEEK_API_KEY",
        ModelProvider.INCEPTION: "INCEPTION_API_KEY",
        ModelProvider.NVIDIA: "NVIDIA_API_KEY",
        ModelProvider.OPENROUTER: "OPENROUTER_API_KEY",
        ModelProvider.GOOGLE: "GOOGLE_API_KEY",
    }

    def __init__(self):
        self._clients: Dict[ModelProvider, Any] = {}
        self._api_keys: Dict[ModelProvider, str] = {}
        self._load_api_keys()

    def _load_api_keys(self):
        for provider, env_var in self.API_KEY_ENV.items():
            key = os.getenv(env_var)
            if key:
                key = key.strip()
            if key:
                self._api_keys[provider] = key
                log.debug(f"API Key geladen fuer: {provider.value}")

    def get_api_key(self, provider: ModelProvider) -> Optional[str]:
        return self._api_keys.get(provider)

    def get_base_url(self, provider: ModelProvider) -> str:
        env_override = os.getenv(f"{provider.value.upper()}_API_BASE")
        return env_override or self.BASE_URLS.get(provider, "")

    def has_provider(self, provider: ModelProvider) -> bool:
        return provider in self._api_keys

    def get_client(self, provider: ModelProvider):
        if provider in self._clients:
            return self._clients[provider]

        api_key = self.get_api_key(provider)
        if not api_key:
            raise ValueError(
                f"Kein API Key fuer Provider '{provider.value}' gefunden. "
                f"Setze {self.API_KEY_ENV[provider]} in .env"
            )

        if provider in [
            ModelProvider.OPENAI, ModelProvider.DEEPSEEK,
            ModelProvider.INCEPTION, ModelProvider.NVIDIA,
            ModelProvider.OPENROUTER,
        ]:
            client = self._init_openai_compatible(provider)
        elif provider == ModelProvider.ANTHROPIC:
            client = self._init_anthropic()
        elif provider == ModelProvider.GOOGLE:
            client = self._init_google()
        else:
            raise ValueError(f"Unbekannter Provider: {provider}")

        self._clients[provider] = client
        log.info(f"Client initialisiert: {provider.value}")
        return client

    def _init_openai_compatible(self, provider: ModelProvider):
        from openai import OpenAI
        return OpenAI(
            api_key=self.get_api_key(provider),
            base_url=self.get_base_url(provider),
        )

    def _init_anthropic(self):
        try:
            from anthropic import Anthropic
            return Anthropic(api_key=self.get_api_key(ModelProvider.ANTHROPIC))
        except ImportError:
            log.warning("anthropic Package nicht installiert, nutze httpx Fallback")
            return None

    def _init_google(self):
        return None


class AgentModelConfig:
    """Konfiguration welches Modell/Provider jeder Agent-Typ nutzt."""

    AGENT_CONFIGS = {
        "executor": ("FAST_MODEL", "FAST_MODEL_PROVIDER", "gpt-5-mini", ModelProvider.OPENAI),
        "deep_research": ("RESEARCH_MODEL", "RESEARCH_MODEL_PROVIDER", "deepseek-reasoner", ModelProvider.DEEPSEEK),
        "creative": ("CREATIVE_MODEL", "CREATIVE_MODEL_PROVIDER", "gpt-5.2", ModelProvider.OPENAI),
        "developer": ("CODE_MODEL", "CODE_MODEL_PROVIDER", "mercury-coder-small", ModelProvider.INCEPTION),
        "meta": ("PLANNING_MODEL", "PLANNING_MODEL_PROVIDER", "claude-sonnet-4-5-20250929", ModelProvider.ANTHROPIC),
        "visual": ("VISION_MODEL", "VISION_MODEL_PROVIDER", "claude-sonnet-4-5-20250929", ModelProvider.ANTHROPIC),
        "reasoning": ("REASONING_MODEL", "REASONING_MODEL_PROVIDER", "nvidia/nemotron-3-nano-30b-a3b", ModelProvider.OPENROUTER),
        # M1: neue Agenten
        "data":     ("DATA_MODEL",     "DATA_MODEL_PROVIDER",     "gpt-4o",                         ModelProvider.OPENAI),
        "document": ("DOCUMENT_MODEL", "DOCUMENT_MODEL_PROVIDER", "claude-sonnet-4-5-20250929",      ModelProvider.ANTHROPIC),
        # M2: neue Agenten
        "communication": ("COMMUNICATION_MODEL", "COMMUNICATION_MODEL_PROVIDER", "claude-sonnet-4-5-20250929", ModelProvider.ANTHROPIC),
        # M3: neue Agenten
        "system": ("SYSTEM_MODEL", "SYSTEM_MODEL_PROVIDER", "qwen/qwen3.5-plus-02-15", ModelProvider.OPENROUTER),
        # M4: neue Agenten
        "shell": ("SHELL_MODEL", "SHELL_MODEL_PROVIDER", "claude-sonnet-4-6", ModelProvider.ANTHROPIC),
    }

    @classmethod
    def get_model_and_provider(cls, agent_type: str) -> Tuple[str, ModelProvider]:
        if agent_type not in cls.AGENT_CONFIGS:
            log.warning(f"Unbekannter Agent-Typ: {agent_type}, nutze Defaults")
            return "gpt-4o", ModelProvider.OPENAI

        model_env, provider_env, fallback_model, fallback_provider = cls.AGENT_CONFIGS[agent_type]
        model = os.getenv(model_env, fallback_model)
        provider_str = os.getenv(provider_env, fallback_provider.value)

        try:
            provider = ModelProvider(provider_str.lower())
        except ValueError:
            log.warning(f"Unbekannter Provider '{provider_str}', nutze Fallback")
            provider = fallback_provider

        return model, provider


# Globale Provider-Client Instanz
_provider_client: Optional[MultiProviderClient] = None


def get_provider_client() -> MultiProviderClient:
    """Gibt die globale Provider-Client Instanz zurueck."""
    global _provider_client
    if _provider_client is None:
        _provider_client = MultiProviderClient()
    return _provider_client
