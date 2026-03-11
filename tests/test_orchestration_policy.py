from __future__ import annotations

from types import SimpleNamespace

import pytest

from orchestration.orchestration_policy import (
    evaluate_parallel_tasks,
    evaluate_query_orchestration,
)


def test_evaluate_query_orchestration_routes_multi_capability_to_meta():
    decision = evaluate_query_orchestration(
        "Recherchiere KI-Agenten und sende mir danach eine PDF per E-Mail"
    )

    assert decision["route_to_meta"] is True
    assert "research" in decision["capabilities"]
    assert "document" in decision["capabilities"]
    assert "communication" in decision["capabilities"]


def test_evaluate_query_orchestration_keeps_single_lane_simple_browser_step():
    decision = evaluate_query_orchestration("Starte den Browser und gehe auf booking.com")

    assert decision["route_to_meta"] is False
    assert "visual" in decision["capabilities"]


def test_evaluate_query_orchestration_routes_login_workflow_to_meta():
    decision = evaluate_query_orchestration(
        "Öffne github.com/login, gib Benutzername und Passwort ein und klicke auf Sign in"
    )

    assert decision["route_to_meta"] is True
    assert decision["reason"] in {"login_workflow", "multi_action"}


def test_evaluate_query_orchestration_routes_interactive_youtube_and_x_workflows_to_meta():
    youtube_decision = evaluate_query_orchestration(
        "Öffne YouTube, suche nach KI News März 2026 und öffne das erste relevante Video"
    )
    x_decision = evaluate_query_orchestration(
        "Öffne x.com und schreibe Hallo aus Timus in einen neuen Beitrag"
    )

    assert youtube_decision["route_to_meta"] is True
    assert youtube_decision["reason"] in {"interactive_browser_workflow", "multi_action"}
    assert x_decision["route_to_meta"] is True
    assert x_decision["reason"] in {"interactive_browser_workflow", "multi_action"}


def test_evaluate_parallel_tasks_blocks_explicit_dependencies():
    decision = evaluate_parallel_tasks(
        [
            {"task_id": "t1", "agent": "research", "task": "Recherchiere X"},
            {
                "task_id": "t2",
                "agent": "communication",
                "task": "Sende das Ergebnis aus Schritt 1 per E-Mail",
            },
        ]
    )

    assert decision["allowed"] is False
    assert decision["policy_state"] == "blocked"
    assert "t2" in decision["dependent_task_ids"]


def test_evaluate_parallel_tasks_allows_independent_fan_out():
    decision = evaluate_parallel_tasks(
        [
            {"task_id": "t1", "agent": "research", "task": "Recherchiere OpenAI News"},
            {"task_id": "t2", "agent": "research", "task": "Recherchiere Anthropic News"},
        ]
    )

    assert decision["allowed"] is True
    assert decision["policy_state"] == "allowed"
    assert decision["dependent_task_ids"] == []


@pytest.mark.asyncio
async def test_delegate_parallel_blocks_dependent_tasks_before_execution(monkeypatch):
    from agent.agent_registry import AgentRegistry, AgentSpec

    run_calls = []

    def _factory(_tools_desc, **_kw):
        async def _run(_task):
            run_calls.append(_task)
            return "ok"

        return SimpleNamespace(run=_run)

    registry = AgentRegistry()
    registry._specs["research"] = AgentSpec("research", "research", ["research"], factory=_factory)
    registry._specs["communication"] = AgentSpec("communication", "communication", ["communication"], factory=_factory)

    result = await registry.delegate_parallel(
        tasks=[
            {"task_id": "t1", "agent": "research", "task": "Recherchiere X"},
            {"task_id": "t2", "agent": "communication", "task": "Sende das Ergebnis aus Schritt 1 per E-Mail"},
        ],
        max_parallel=2,
    )

    assert result["policy_state"] == "blocked"
    assert result["policy_reason"] in {"workflow_connector", "deliverable_chain", "explicit_dependency"}
    assert result["effective_max_parallel"] == 0
    assert run_calls == []
