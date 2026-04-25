from __future__ import annotations

from pathlib import Path

from utils.embedding_provider import _resolve_provider_api_key


def test_resolve_provider_api_key_prefers_dotenv_over_process_env(tmp_path, monkeypatch):
    env_path = Path(tmp_path) / ".env"
    env_path.write_text(
        "OPENAI_API_KEY=sk-proj-newkeyfromdotenv1234567890\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("OPENAI_API_KEY", "sk-proj-oldkeyfromprocess0987654321")

    resolved = _resolve_provider_api_key("OPENAI_API_KEY", dotenv_path=env_path)

    assert resolved == "sk-proj-newkeyfromdotenv1234567890"


def test_resolve_provider_api_key_falls_back_to_process_env_when_dotenv_missing(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-proj-onlyprocessvalue123")

    resolved = _resolve_provider_api_key(
        "OPENAI_API_KEY",
        dotenv_path=Path("/tmp/does-not-exist-for-embedding-provider.env"),
    )

    assert resolved == "sk-proj-onlyprocessvalue123"
