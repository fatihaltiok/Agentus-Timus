"""Provider-agnostische Embedding-Funktion fuer ChromaDB."""

import os
import logging
from pathlib import Path
from typing import List

from chromadb.api.types import Documents, EmbeddingFunction, Embeddings
from dotenv import dotenv_values

log = logging.getLogger("TimusAgent-v4.4")
_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_DOTENV_PATH = _PROJECT_ROOT / ".env"


def _resolve_provider_api_key(env_key: str, *, dotenv_path: Path | None = None) -> str:
    """Nutze Projekt-.env vor geerbten Prozess-Variablen.

    Das verhindert, dass alte Shell-/Service-Umgebungen einen inzwischen
    ersetzten API-Key fuer Embeddings weiter injizieren.
    """

    env_name = str(env_key or "").strip()
    if not env_name:
        return ""

    resolved_path = dotenv_path or _DOTENV_PATH
    try:
        file_values = dotenv_values(resolved_path) if resolved_path.exists() else {}
    except Exception:
        file_values = {}

    file_value = str(file_values.get(env_name) or "").strip()
    if file_value:
        return file_value
    return str(os.getenv(env_name) or "").strip()


class MultiProviderEmbeddingFunction(EmbeddingFunction[Documents]):
    """
    Embedding-Funktion die verschiedene Provider unterstuetzt.
    Implementiert ChromaDB's EmbeddingFunction Protocol.

    Unterstuetzte Provider:
    - openai (default): text-embedding-3-small, text-embedding-ada-002
    - nvidia: NV-Embed-QA etc. via NVIDIA API
    - deepseek: deepseek-embedding via DeepSeek API
    """

    PROVIDER_CONFIGS = {
        "openai": {
            "env_key": "OPENAI_API_KEY",
            "base_url": "https://api.openai.com/v1",
            "default_model": "text-embedding-3-small",
        },
        "nvidia": {
            "env_key": "NVIDIA_API_KEY",
            "base_url": "https://integrate.api.nvidia.com/v1",
            "default_model": "nvidia/nv-embedqa-e5-v5",
        },
        "deepseek": {
            "env_key": "DEEPSEEK_API_KEY",
            "base_url": "https://api.deepseek.com/v1",
            "default_model": "deepseek-embedding",
        },
    }

    def __init__(self, provider: str = None, model: str = None):
        self._provider = provider or os.getenv("EMBEDDING_PROVIDER", "openai")
        config = self.PROVIDER_CONFIGS.get(self._provider)
        if not config:
            raise ValueError(
                f"Unbekannter Embedding-Provider: {self._provider}. "
                f"Unterstuetzt: {list(self.PROVIDER_CONFIGS.keys())}"
            )

        self._model = model or os.getenv("EMBEDDING_MODEL", config["default_model"])
        api_key = _resolve_provider_api_key(config["env_key"])
        if not api_key:
            raise ValueError(
                f"API Key fehlt: {config['env_key']} muss gesetzt sein "
                f"fuer Provider '{self._provider}'"
            )

        from openai import OpenAI
        self._client = OpenAI(api_key=api_key, base_url=config["base_url"])
        log.info(f"Embedding-Provider initialisiert: {self._provider} / {self._model}")

    def __call__(self, input: Documents) -> Embeddings:
        response = self._client.embeddings.create(
            input=input,
            model=self._model,
        )
        return [item.embedding for item in response.data]


def get_embedding_function(
    provider: str = None, model: str = None
) -> MultiProviderEmbeddingFunction:
    """Factory-Funktion fuer die Embedding-Funktion."""
    return MultiProviderEmbeddingFunction(provider=provider, model=model)
