"""Deterministic parity harness for the delegation runtime path."""

from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping, Sequence
from unittest.mock import patch

from agent import agent_registry as registry_module
from orchestration.approval_auth_contract import build_auth_required_workflow_payload


@dataclass(frozen=True, slots=True)
class DelegationParityScenario:
    scenario_id: str
    from_agent: str
    to_agent: str
    task: str
    agent_factory: Callable[[], Any]
    expected_status: str
    expected_transport_kind: str = ""
    expected_transport_stage: str = ""
    expected_sse_terminal: str = ""
    expected_timeout_phase: str = ""
    expected_note_fragment: str = ""
    env_overrides: Mapping[str, str] = field(default_factory=dict)


class _SuccessExecutor:
    async def run(self, task: str) -> str:
        callback = getattr(self, "_delegation_progress_callback", None)
        if callable(callback):
            callback(
                stage="lookup_started",
                payload={
                    "kind": "progress",
                    "message": "Delegation hat den Lookup gestartet.",
                },
            )
        return "Delegation erfolgreich abgeschlossen."


class _WorkflowPartialExecutor:
    async def run(self, task: str) -> Mapping[str, Any]:
        callback = getattr(self, "_delegation_progress_callback", None)
        if callable(callback):
            callback(
                stage="auth_wall_detected",
                payload={
                    "kind": "progress",
                    "message": "Login-Wall erkannt.",
                },
            )
        return build_auth_required_workflow_payload(
            url="https://x.com/example/status/1",
            platform="twitter",
            message="X/Twitter verlangt Login.",
            user_action_required="Bitte bestaetige den Login selbst.",
        )


class _SlowResearchAgent:
    async def run(self, task: str) -> str:
        await asyncio.sleep(0.2)
        return "zu spaet"


class _ErrorExecutor:
    async def run(self, task: str) -> str:
        callback = getattr(self, "_delegation_progress_callback", None)
        if callable(callback):
            callback(
                stage="delegation_precheck",
                payload={
                    "kind": "progress",
                    "message": "Delegation prueft den Task.",
                },
            )
        raise RuntimeError("Kontrollierter Delegationsfehler")


def build_default_delegation_parity_scenarios() -> list[DelegationParityScenario]:
    return [
        DelegationParityScenario(
            scenario_id="delegation_executor_success",
            from_agent="meta",
            to_agent="executor",
            task="Bitte recherchiere kurz die letzten Aenderungen.",
            agent_factory=_SuccessExecutor,
            expected_status="success",
            expected_transport_kind="progress",
            expected_transport_stage="lookup_started",
            expected_sse_terminal="completed",
        ),
        DelegationParityScenario(
            scenario_id="delegation_executor_workflow_partial",
            from_agent="meta",
            to_agent="executor",
            task="Bitte oeffne X/Twitter und lies den Beitrag.",
            agent_factory=_WorkflowPartialExecutor,
            expected_status="partial",
            expected_transport_kind="partial_result",
            expected_transport_stage="delegation_partial",
            expected_note_fragment="nicht vollstaendig abgeschlossen",
        ),
        DelegationParityScenario(
            scenario_id="delegation_research_timeout_partial",
            from_agent="meta",
            to_agent="research",
            task="Suche sehr langsam nach allen Quellen.",
            agent_factory=_SlowResearchAgent,
            expected_status="partial",
            expected_transport_kind="partial_result",
            expected_transport_stage="delegation_partial_timeout",
            expected_timeout_phase="run",
            expected_note_fragment="Recherche-Timeout",
            env_overrides={
                "RESEARCH_TIMEOUT": "0.05",
                "DELEGATION_MAX_RETRIES": "1",
            },
        ),
        DelegationParityScenario(
            scenario_id="delegation_executor_error",
            from_agent="meta",
            to_agent="executor",
            task="Bitte fuehre eine Aktion mit Fehler aus.",
            agent_factory=_ErrorExecutor,
            expected_status="error",
            expected_transport_kind="progress",
            expected_transport_stage="delegation_precheck",
            expected_sse_terminal="error",
        ),
    ]


def _normalize_mapping(value: Mapping[str, Any] | None) -> dict[str, Any]:
    return dict(value or {})


def _transport_event_exists(
    events: Sequence[Mapping[str, Any]],
    *,
    kind: str,
    stage: str = "",
) -> bool:
    normalized_kind = str(kind or "").strip().lower()
    normalized_stage = str(stage or "").strip().lower()
    for raw in list(events or []):
        event = _normalize_mapping(raw)
        event_kind = str(event.get("kind") or "").strip().lower()
        event_stage = str(event.get("stage") or "").strip().lower()
        if event_kind != normalized_kind:
            continue
        if normalized_stage and event_stage != normalized_stage:
            continue
        return True
    return False


def evaluate_delegation_parity_result(
    scenario: DelegationParityScenario,
    payload: Mapping[str, Any],
) -> dict[str, Any]:
    result = _normalize_mapping(payload.get("result") if isinstance(payload, Mapping) else {})
    transport_events = list(payload.get("transport_events") or []) if isinstance(payload, Mapping) else []
    sse_events = list(payload.get("sse_events") or []) if isinstance(payload, Mapping) else []
    checks: list[str] = []
    failures: list[str] = []

    if str(result.get("status") or "") == scenario.expected_status:
        checks.append("status")
    else:
        failures.append("status")

    if scenario.expected_transport_kind:
        if _transport_event_exists(
            transport_events,
            kind=scenario.expected_transport_kind,
            stage=scenario.expected_transport_stage,
        ):
            checks.append("transport_event")
        else:
            failures.append("transport_event")

    if scenario.expected_sse_terminal:
        terminal_statuses = [str(item.get("status") or "") for item in sse_events if isinstance(item, Mapping)]
        if terminal_statuses and terminal_statuses[-1] == scenario.expected_sse_terminal:
            checks.append("sse_terminal")
        else:
            failures.append("sse_terminal")

    if scenario.expected_timeout_phase:
        metadata = _normalize_mapping(result.get("metadata") if isinstance(result.get("metadata"), Mapping) else {})
        if str(metadata.get("timeout_phase") or "") == scenario.expected_timeout_phase and bool(metadata.get("timed_out")):
            checks.append("timeout_metadata")
        else:
            failures.append("timeout_metadata")

    if scenario.expected_note_fragment:
        note = str(result.get("note") or "")
        if scenario.expected_note_fragment.lower() in note.lower():
            checks.append("note")
        else:
            failures.append("note")

    return {
        "scenario_id": scenario.scenario_id,
        "passed": not failures,
        "checks": checks,
        "failures": failures,
        "status": str(result.get("status") or ""),
        "transport_kinds": [str(_normalize_mapping(item).get("kind") or "") for item in transport_events],
        "sse_statuses": [str(_normalize_mapping(item).get("status") or "") for item in sse_events],
    }


def summarize_delegation_parity_results(results: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    rows = [_normalize_mapping(item) for item in list(results or [])]
    failed = [row for row in rows if not bool(row.get("passed"))]
    return {
        "total": len(rows),
        "passed": len(rows) - len(failed),
        "failed": len(failed),
        "failed_scenarios": [str(row.get("scenario_id") or "") for row in failed],
    }


async def run_delegation_parity_harness_scenario(
    scenario: DelegationParityScenario,
) -> dict[str, Any]:
    registry = registry_module.AgentRegistry()

    async def _fake_tools_description() -> str:
        return "tools"

    registry._get_tools_description = _fake_tools_description  # type: ignore[method-assign]
    registry.register_spec(
        scenario.to_agent,
        scenario.to_agent,
        [scenario.to_agent],
        lambda tools_description_string: scenario.agent_factory(),
    )

    sse_events: list[dict[str, Any]] = []
    transport_events: list[dict[str, Any]] = []

    with (
        patch.object(
            registry_module.AgentRegistry,
            "_auto_write_to_blackboard",
            new=staticmethod(lambda *args, **kwargs: f"bb_{scenario.scenario_id}"),
        ),
        patch.object(
            registry_module,
            "_delegation_sse_hook",
            lambda from_agent, to_agent, status: sse_events.append(
                {
                    "from_agent": str(from_agent or ""),
                    "to_agent": str(to_agent or ""),
                    "status": str(status or ""),
                }
            ),
        ),
        patch.object(
            registry_module,
            "_delegation_transport_hook",
            lambda payload: transport_events.append(_normalize_mapping(payload)),
        ),
        patch.dict(os.environ, dict(scenario.env_overrides or {}), clear=False),
    ):
        result = await registry.delegate(
            from_agent=scenario.from_agent,
            to_agent=scenario.to_agent,
            task=scenario.task,
            session_id=f"f3_{scenario.scenario_id}",
        )

    evaluation = evaluate_delegation_parity_result(
        scenario,
        {
            "result": result,
            "transport_events": transport_events,
            "sse_events": sse_events,
        },
    )
    return {
        "scenario_id": scenario.scenario_id,
        "result": result,
        "transport_events": transport_events,
        "sse_events": sse_events,
        "evaluation": evaluation,
    }


async def run_delegation_parity_harness(
    scenarios: Sequence[DelegationParityScenario] | None = None,
) -> dict[str, Any]:
    selected = list(scenarios or build_default_delegation_parity_scenarios())
    results: list[dict[str, Any]] = []
    for scenario in selected:
        results.append(await run_delegation_parity_harness_scenario(scenario))
    evaluations = [_normalize_mapping(item.get("evaluation")) for item in results]
    return {
        "contract_version": "delegation_parity_harness_v1",
        "results": results,
        "summary": summarize_delegation_parity_results(evaluations),
    }


def run_delegation_parity_harness_sync(
    scenarios: Sequence[DelegationParityScenario] | None = None,
) -> dict[str, Any]:
    return asyncio.run(run_delegation_parity_harness(scenarios=scenarios))
