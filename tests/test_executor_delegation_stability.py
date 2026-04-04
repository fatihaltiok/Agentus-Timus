from __future__ import annotations

import asyncio
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def _base_registry():
    from agent.agent_registry import AgentRegistry

    registry = AgentRegistry()

    async def _fake_tools():
        return "tools"

    registry._get_tools_description = _fake_tools
    return registry


def _simple_lookup_handoff(task: str) -> str:
    return "\n".join(
        [
            "# DELEGATION HANDOFF",
            "target_agent: executor",
            "goal: Fuehre eine kompakte aktuelle Live-Recherche aus.",
            "expected_output: quick_summary, top_results, source_urls",
            "success_signal: Stage 'live_lookup_scan' erfolgreich abgeschlossen",
            "constraints: bleibe_kurz_und_vermeide_deep_research",
            "handoff_data:",
            "- task_type: simple_live_lookup",
            "- recipe_id: simple_live_lookup",
            "- stage_id: live_lookup_scan",
            f"- original_user_task: {task}",
            "",
            "# TASK",
            "Fuehre eine kompakte aktuelle Live-Recherche aus.",
        ]
    )


def test_select_delegation_timeout_uses_executor_lookup_timeout_for_simple_live_lookup(monkeypatch):
    from agent.agent_registry import AgentRegistry

    monkeypatch.setenv("DELEGATION_TIMEOUT", "120")
    monkeypatch.setenv("EXECUTOR_LOOKUP_TIMEOUT", "45")

    simple_timeout = AgentRegistry._select_delegation_timeout(
        "executor",
        _simple_lookup_handoff("Was gibt es Neues aus der Wissenschaft?"),
    )
    general_timeout = AgentRegistry._select_delegation_timeout("executor", "normale executor aufgabe")

    assert simple_timeout == pytest.approx(45.0)
    assert general_timeout == pytest.approx(120.0)


@pytest.mark.asyncio
async def test_executor_progress_watchdog_fails_fast_when_no_progress(monkeypatch):
    registry = _base_registry()

    class _SilentExecutor:
        conversation_session_id = None

        async def run(self, task: str) -> str:
            await asyncio.sleep(10)
            return "never"

    monkeypatch.setenv("DELEGATION_MAX_RETRIES", "1")
    monkeypatch.setenv("EXECUTOR_LOOKUP_TIMEOUT", "5")
    monkeypatch.setenv("EXECUTOR_PROGRESS_TIMEOUT", "0.05")

    registry.register_spec(
        "executor",
        "executor",
        ["executor"],
        lambda tools_description_string: _SilentExecutor(),
    )

    started = time.monotonic()
    result = await registry.delegate(
        from_agent="meta",
        to_agent="executor",
        task=_simple_lookup_handoff("Liste aktuelle LLM-Preise auf"),
    )
    elapsed = time.monotonic() - started

    assert result["status"] == "error"
    assert result["metadata"]["timeout_phase"] == "progress"
    assert elapsed < 2.0


@pytest.mark.asyncio
async def test_executor_progress_watchdog_allows_started_lookup(monkeypatch):
    registry = _base_registry()

    class _HealthyExecutor:
        conversation_session_id = None

        async def run(self, task: str) -> str:
            callback = getattr(self, "_delegation_progress_callback", None)
            if callable(callback):
                callback(stage="simple_live_lookup_start")
            await asyncio.sleep(0.01)
            return "live lookup ok"

    monkeypatch.setenv("DELEGATION_MAX_RETRIES", "1")
    monkeypatch.setenv("EXECUTOR_LOOKUP_TIMEOUT", "1")
    monkeypatch.setenv("EXECUTOR_PROGRESS_TIMEOUT", "0.05")

    registry.register_spec(
        "executor",
        "executor",
        ["executor"],
        lambda tools_description_string: _HealthyExecutor(),
    )

    result = await registry.delegate(
        from_agent="meta",
        to_agent="executor",
        task=_simple_lookup_handoff("Was gibt es Neues aus der Wissenschaft?"),
    )

    assert result["status"] == "success"
    assert result["result"] == "live lookup ok"
