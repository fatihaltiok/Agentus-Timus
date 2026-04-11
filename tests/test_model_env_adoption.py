from types import SimpleNamespace

from agent.agents.creative import (
    _resolve_openai_creative_model,
    _resolve_openrouter_structuring_model,
)
from orchestration.meta_analyzer import MetaAnalyzer
from tools.memory_tool.tool import _resolve_memory_summary_model


def test_creative_openai_model_uses_env(monkeypatch):
    monkeypatch.setenv("CREATIVE_MODEL", "gpt-5.2")
    monkeypatch.setenv("CREATIVE_MODEL_PROVIDER", "openai")

    assert _resolve_openai_creative_model() == "gpt-5.2"


def test_creative_structuring_prefers_openrouter_reasoning(monkeypatch):
    monkeypatch.setenv("REASONING_MODEL", "deepseek/deepseek-v3.2")
    monkeypatch.setenv("REASONING_MODEL_PROVIDER", "openrouter")
    monkeypatch.setenv("FAST_MODEL", "qwen/qwen3-8b")
    monkeypatch.setenv("FAST_MODEL_PROVIDER", "openrouter")

    assert _resolve_openrouter_structuring_model() == "deepseek/deepseek-v3.2"


def test_memory_summary_model_uses_smart_openai_model(monkeypatch):
    monkeypatch.setenv("SMART_MODEL", "gpt-5.4")
    monkeypatch.setenv("SMART_MODEL_PROVIDER", "openai")

    assert _resolve_memory_summary_model() == "gpt-5.4"


def test_meta_analyzer_uses_planning_model_env(monkeypatch):
    import agent.providers as providers_mod

    class _FakeCompletions:
        def __init__(self):
            self.model = None

        def create(self, **kwargs):
            self.model = kwargs["model"]
            return SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        message=SimpleNamespace(
                            content='{"trend":"stable","weakest_pillar":"planning","key_insight":"ok","action_suggestion":"none","risk_level":"low"}'
                        )
                    )
                ]
            )

    fake_completions = _FakeCompletions()
    fake_client = SimpleNamespace(chat=SimpleNamespace(completions=fake_completions))
    fake_provider_client = SimpleNamespace(get_client=lambda provider: fake_client)

    monkeypatch.setattr(providers_mod, "get_provider_client", lambda: fake_provider_client)
    monkeypatch.setenv("PLANNING_MODEL", "glm-5")
    monkeypatch.setenv("PLANNING_MODEL_PROVIDER", "zai")

    result = MetaAnalyzer()._call_llm(history=[], incidents=[])

    assert fake_completions.model == "glm-5"
    assert result["trend"] == "stable"


def test_meta_analyzer_improvement_context_prefers_normalized_fields(monkeypatch):
    monkeypatch.setenv("AUTONOMY_SELF_IMPROVEMENT_ENABLED", "true")
    monkeypatch.setattr(
        "orchestration.self_improvement_engine.get_improvement_engine",
        lambda: SimpleNamespace(
            get_suggestions=lambda applied=False: [
                {
                    "severity": "high",
                    "category": "routing",
                    "target": "research",
                    "problem": "Normalized routing problem",
                    "finding": "Legacy finding text",
                }
            ]
        ),
    )

    context = MetaAnalyzer()._get_improvement_context()

    assert "Kritische Self-Improvement Befunde:" in context
    assert "[routing:research] Normalized routing problem" in context
    assert "Legacy finding text" not in context
