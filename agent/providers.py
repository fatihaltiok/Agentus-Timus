"""Multi-Provider Infrastruktur fuer Timus-Agenten.

Enthaelt:
- ModelProvider Enum
- MultiProviderClient (Lazy Init)
- AgentModelConfig
- get_provider_client() Factory
"""

import os
import logging
from typing import Dict, Any, Optional, Tuple, Set
from enum import Enum

log = logging.getLogger("TimusAgent-v4.4")


class ModelProvider(str, Enum):
    """Unterstuetzte LLM-Provider."""
    OPENAI = "openai"
    ZAI = "zai"
    ANTHROPIC = "anthropic"
    DEEPSEEK = "deepseek"
    INCEPTION = "inception"
    NVIDIA = "nvidia"
    OPENROUTER = "openrouter"
    GOOGLE = "google"


class ModelConfigurationError(ValueError):
    """Konfiguriertes Modell passt nicht zum gewählten Provider."""


class MultiProviderClient:
    """
    Verwaltet API-Clients fuer verschiedene LLM-Provider.
    Lazy Initialization - Clients werden erst bei Bedarf erstellt.
    """

    BASE_URLS = {
        ModelProvider.OPENAI: "https://api.openai.com/v1",
        ModelProvider.ZAI: "https://api.z.ai/api/paas/v4",
        ModelProvider.ANTHROPIC: "https://api.anthropic.com",
        ModelProvider.DEEPSEEK: "https://api.deepseek.com/v1",
        ModelProvider.INCEPTION: "https://api.inceptionlabs.ai/v1",
        ModelProvider.NVIDIA: "https://integrate.api.nvidia.com/v1",
        ModelProvider.OPENROUTER: "https://openrouter.ai/api/v1",
        ModelProvider.GOOGLE: "https://generativelanguage.googleapis.com/v1beta",
    }

    API_KEY_ENV = {
        ModelProvider.OPENAI: "OPENAI_API_KEY",
        ModelProvider.ZAI: "ZAI_API_KEY",
        ModelProvider.ANTHROPIC: "ANTHROPIC_API_KEY",
        ModelProvider.DEEPSEEK: "DEEPSEEK_API_KEY",
        ModelProvider.INCEPTION: "INCEPTION_API_KEY",
        ModelProvider.NVIDIA: "NVIDIA_API_KEY",
        ModelProvider.OPENROUTER: "OPENROUTER_API_KEY",
        ModelProvider.GOOGLE: "GOOGLE_API_KEY",
    }

    API_KEY_ALIASES = {
        ModelProvider.GOOGLE: ("GEMINI_API_KEY",),
    }

    # Abweichende Basis-URLs für OpenAI-SDK-Compat-Calls (wenn nötig).
    # BASE_URLS bleibt der kanonische native Endpunkt (z.B. für den Dispatcher).
    OPENAI_COMPAT_URLS = {
        ModelProvider.GOOGLE: "https://generativelanguage.googleapis.com/v1beta/openai",
    }

    def __init__(self):
        self._clients: Dict[ModelProvider, Any] = {}
        self._api_keys: Dict[ModelProvider, str] = {}
        self._available_models_cache: Dict[ModelProvider, Set[str]] = {}
        self._validated_models: set[tuple[ModelProvider, str]] = set()
        self._load_api_keys()

    def _load_api_keys(self):
        for provider, env_var in self.API_KEY_ENV.items():
            key = os.getenv(env_var)
            if not key:
                for alias in self.API_KEY_ALIASES.get(provider, ()):
                    key = os.getenv(alias)
                    if key:
                        break
            if key:
                key = key.strip()
            if key:
                self._api_keys[provider] = key
                log.debug(f"API Key geladen fuer: {provider.value}")

    def get_api_key(self, provider: ModelProvider) -> Optional[str]:
        return self._api_keys.get(provider)

    def get_base_url(self, provider: ModelProvider) -> str:
        """Nativer Endpunkt des Providers (z.B. für direkten httpx-Call im Dispatcher)."""
        env_override = os.getenv(f"{provider.value.upper()}_API_BASE")
        return env_override or self.BASE_URLS.get(provider, "")

    def get_openai_compat_base_url(self, provider: ModelProvider) -> str:
        """OpenAI-SDK-kompatibler Endpunkt. Fallback auf get_base_url() wenn kein Compat-URL hinterlegt."""
        env_override = os.getenv(f"{provider.value.upper()}_API_BASE")
        if env_override:
            return env_override
        return self.OPENAI_COMPAT_URLS.get(provider) or self.BASE_URLS.get(provider, "")

    def has_provider(self, provider: ModelProvider) -> bool:
        return provider in self._api_keys

    def _validation_enabled(self) -> bool:
        return os.getenv("TIMUS_VALIDATE_CONFIGURED_MODELS", "true").strip().lower() not in {
            "0", "false", "no", "off"
        }

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
            ModelProvider.OPENAI, ModelProvider.ZAI, ModelProvider.DEEPSEEK,
            ModelProvider.INCEPTION, ModelProvider.NVIDIA,
            ModelProvider.OPENROUTER, ModelProvider.GOOGLE,
        ]:
            client = self._init_openai_compatible(provider)
        elif provider == ModelProvider.ANTHROPIC:
            client = self._init_anthropic()
        else:
            raise ValueError(f"Unbekannter Provider: {provider}")

        self._clients[provider] = client
        log.info(f"Client initialisiert: {provider.value}")
        return client

    def _provider_supports_model_listing(self, provider: ModelProvider) -> bool:
        return provider in {
            ModelProvider.OPENAI,
            ModelProvider.ZAI,
            ModelProvider.DEEPSEEK,
            ModelProvider.INCEPTION,
            ModelProvider.NVIDIA,
            ModelProvider.OPENROUTER,
        }

    def _fetch_available_models(self, provider: ModelProvider) -> Set[str]:
        if provider in self._available_models_cache:
            return self._available_models_cache[provider]
        client = self.get_client(provider)
        try:
            models_response = client.models.list()
            models = {
                str(getattr(model, "id", "") or "").strip()
                for model in getattr(models_response, "data", []) or []
                if str(getattr(model, "id", "") or "").strip()
            }
        except Exception as e:
            raise ModelConfigurationError(
                f"Modellvalidierung fehlgeschlagen fuer Provider '{provider.value}': "
                f"Model-Liste konnte nicht geladen werden ({e})"
            ) from e

        if not models:
            raise ModelConfigurationError(
                f"Modellvalidierung fehlgeschlagen fuer Provider '{provider.value}': "
                "Provider lieferte keine Modelle zurueck."
            )

        self._available_models_cache[provider] = models
        return models

    def validate_model_or_raise(
        self,
        provider: ModelProvider,
        model: str,
        *,
        agent_type: str = "",
    ) -> None:
        if not self._validation_enabled():
            return

        normalized_model = str(model or "").strip()
        if not normalized_model:
            raise ModelConfigurationError(
                f"Leeres Modell fuer Provider '{provider.value}' konfiguriert"
            )

        cache_key = (provider, normalized_model)
        if cache_key in self._validated_models:
            return

        if not self.has_provider(provider):
            raise ModelConfigurationError(
                f"Provider '{provider.value}' fuer Modell '{normalized_model}' ist nicht konfiguriert. "
                f"Fehlender API-Key: {self.API_KEY_ENV[provider]}"
            )

        if not self._provider_supports_model_listing(provider):
            log.info(
                "Modellvalidierung uebersprungen: provider=%s model=%s reason=no-model-listing",
                provider.value,
                normalized_model,
            )
            self._validated_models.add(cache_key)
            return

        available_models = self._fetch_available_models(provider)
        if normalized_model not in available_models:
            scope = f" fuer Agent '{agent_type}'" if agent_type else ""
            examples = ", ".join(sorted(list(available_models))[:8])
            raise ModelConfigurationError(
                f"Konfiguriertes Modell '{normalized_model}' existiert nicht beim Provider "
                f"'{provider.value}'{scope}. Verfuegbare Beispiele: {examples}"
            )

        self._validated_models.add(cache_key)

    def _init_openai_compatible(self, provider: ModelProvider):
        from openai import OpenAI
        return OpenAI(
            api_key=self.get_api_key(provider),
            base_url=self.get_openai_compat_base_url(provider),
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
        "executor": ("FAST_MODEL", "FAST_MODEL_PROVIDER", "gemini-3-flash-preview", ModelProvider.GOOGLE),
        "deep_research": ("RESEARCH_MODEL", "RESEARCH_MODEL_PROVIDER", "deepseek/deepseek-v3.2", ModelProvider.OPENROUTER),
        "creative": ("CREATIVE_MODEL", "CREATIVE_MODEL_PROVIDER", "gpt-5.2", ModelProvider.OPENAI),
        "developer": ("CODE_MODEL", "CODE_MODEL_PROVIDER", "mercury-2", ModelProvider.INCEPTION),
        "development": ("CODE_MODEL", "CODE_MODEL_PROVIDER", "mercury-2", ModelProvider.INCEPTION),
        "meta": ("PLANNING_MODEL", "PLANNING_MODEL_PROVIDER", "z-ai/glm-5", ModelProvider.OPENROUTER),
        "visual": ("VISUAL_MODEL", "VISUAL_MODEL_PROVIDER", "gpt-5.4-2026-03-05", ModelProvider.OPENAI),
        "reasoning": ("REASONING_MODEL", "REASONING_MODEL_PROVIDER", "nvidia/nemotron-3-nano-30b-a3b", ModelProvider.OPENROUTER),
        # M1: neue Agenten
        "data":     ("DATA_MODEL",     "DATA_MODEL_PROVIDER",     "deepseek/deepseek-v3.2",         ModelProvider.OPENROUTER),
        "document": ("DOCUMENT_MODEL", "DOCUMENT_MODEL_PROVIDER", "amazon/nova-2-lite-v1", ModelProvider.OPENROUTER),
        # M2: neue Agenten
        "communication": ("COMMUNICATION_MODEL", "COMMUNICATION_MODEL_PROVIDER", "google/gemini-3.1-flash-lite-preview", ModelProvider.OPENROUTER),
        # M3: neue Agenten
        "system": ("SYSTEM_MODEL", "SYSTEM_MODEL_PROVIDER", "qwen/qwen3.5-plus-02-15", ModelProvider.OPENROUTER),
        # M4: neue Agenten
        "shell": ("SHELL_MODEL", "SHELL_MODEL_PROVIDER", "inception/mercury-2", ModelProvider.OPENROUTER),
        # M5: Bild-Analyse
        "image": ("IMAGE_MODEL", "IMAGE_MODEL_PROVIDER", "qwen/qwen3.5-plus-02-15", ModelProvider.OPENROUTER),
    }

    @classmethod
    def get_model_and_provider(cls, agent_type: str) -> Tuple[str, ModelProvider]:
        if agent_type not in cls.AGENT_CONFIGS:
            log.warning(f"Unbekannter Agent-Typ: {agent_type}, nutze Defaults")
            model, provider = "gpt-4o", ModelProvider.OPENAI
            get_provider_client().validate_model_or_raise(provider, model, agent_type=agent_type)
            return model, provider

        model_env, provider_env, fallback_model, fallback_provider = cls.AGENT_CONFIGS[agent_type]
        model, provider = resolve_model_provider_env(
            model_env=model_env,
            provider_env=provider_env,
            fallback_model=fallback_model,
            fallback_provider=fallback_provider,
        )

        get_provider_client().validate_model_or_raise(provider, model, agent_type=agent_type)
        return model, provider


def resolve_model_provider_env(
    *,
    model_env: str,
    provider_env: str,
    fallback_model: str,
    fallback_provider: ModelProvider,
) -> Tuple[str, ModelProvider]:
    model = str(os.getenv(model_env, fallback_model) or fallback_model).strip() or fallback_model
    provider_str = str(os.getenv(provider_env, fallback_provider.value) or fallback_provider.value).strip().lower()

    try:
        provider = ModelProvider(provider_str)
    except ValueError:
        log.warning(
            "Unbekannter Provider '%s' fuer %s/%s, nutze Fallback %s",
            provider_str,
            model_env,
            provider_env,
            fallback_provider.value,
        )
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


def validate_configured_model_or_raise(
    provider: ModelProvider,
    model: str,
    *,
    agent_type: str = "",
) -> None:
    """Oeffentliche Helferfunktion fuer Sonderpfade ausserhalb von BaseAgent."""
    get_provider_client().validate_model_or_raise(
        provider,
        model,
        agent_type=agent_type,
    )
