"""Deterministic parity harness for the /chat runtime path."""

from __future__ import annotations

import asyncio
import json
import os
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Mapping, Sequence
from unittest.mock import patch


@dataclass(frozen=True, slots=True)
class CanvasChatHarnessScenario:
    scenario_id: str
    request_payload: Mapping[str, Any]
    selected_agent: str
    agent_result: Any = ""
    progress_events: tuple[Mapping[str, Any], ...] = ()
    expected_status: str = "success"
    expected_phase_d_status: str = ""
    expected_agent: str = ""
    raise_error: str = ""


class _FakeRequest:
    def __init__(self, payload: Mapping[str, Any]):
        self._payload = dict(payload)

    async def json(self) -> dict[str, Any]:
        return dict(self._payload)


def build_default_canvas_chat_parity_scenarios() -> list[CanvasChatHarnessScenario]:
    return [
        CanvasChatHarnessScenario(
            scenario_id="chat_success_progress",
            request_payload={"query": "Was ist neu?", "session_id": "f3_chat_success"},
            selected_agent="executor",
            agent_result="Hier ist die Antwort.",
            progress_events=(
                {
                    "agent": "executor",
                    "stage": "simple_live_lookup_start",
                    "payload": {"query": "KI auf X"},
                },
            ),
            expected_status="success",
            expected_agent="executor",
        ),
        CanvasChatHarnessScenario(
            scenario_id="chat_phase_d_workflow_fallback",
            request_payload={
                "query": "oeffne github.com/login und bring mich bis zur login-maske",
                "session_id": "f3_chat_phase_d",
            },
            selected_agent="visual_login",
            agent_result={
                "status": "success",
                "result": "partial_result — GitHub-Login-Maske ist sichtbar und bereit zur nutzergesteuerten Anmeldung.",
                "metadata": {
                    "phase_d_workflow": {
                        "status": "awaiting_user",
                        "workflow_id": "wf_f3_live_fallback",
                        "service": "github",
                        "url": "https://github.com/login",
                        "reason": "user_mediated_login",
                        "message": "Die Login-Maske ist bereit.",
                        "user_action_required": "Bitte fuehre den Login selbst aus.",
                        "resume_hint": "Sage danach 'weiter'.",
                        "awaiting_user": True,
                    }
                },
            },
            expected_status="success",
            expected_agent="visual_login",
            expected_phase_d_status="awaiting_user",
        ),
        CanvasChatHarnessScenario(
            scenario_id="chat_runtime_error",
            request_payload={"query": "Was ist neu?", "session_id": "f3_chat_fail"},
            selected_agent="executor",
            raise_error="boom",
            expected_status="error",
            expected_agent="executor",
        ),
    ]


def _normalize_response_payload(response: Any) -> dict[str, Any]:
    if isinstance(response, dict):
        return dict(response)
    status_code = int(getattr(response, "status_code", 0) or 0)
    body = getattr(response, "body", b"")
    try:
        decoded = json.loads(body.decode("utf-8"))
    except Exception:
        decoded = {}
    if isinstance(decoded, dict):
        decoded.setdefault("http_status", status_code)
        return decoded
    return {"status": "error", "http_status": status_code, "error": "invalid_response"}


def evaluate_canvas_chat_harness_result(
    scenario: CanvasChatHarnessScenario,
    result: Mapping[str, Any],
) -> dict[str, Any]:
    payload = dict(result or {})
    sse_events = list(payload.get("sse_events") or [])
    response = dict(payload.get("response") or {})
    checks: list[str] = []
    failures: list[str] = []

    if str(response.get("status") or "") == scenario.expected_status:
        checks.append("response_status")
    else:
        failures.append("response_status")

    if scenario.expected_agent and scenario.expected_status == "success":
        if str(response.get("agent") or "") == scenario.expected_agent:
            checks.append("response_agent")
        else:
            failures.append("response_agent")

    if scenario.expected_phase_d_status:
        workflow = dict(response.get("phase_d_workflow") or {})
        if str(workflow.get("status") or "") == scenario.expected_phase_d_status:
            checks.append("phase_d_workflow")
        else:
            failures.append("phase_d_workflow")

    event_types = [str(item.get("type") or "") for item in sse_events]
    if scenario.raise_error:
        if "run_failed" in event_types:
            checks.append("run_failed_event")
        else:
            failures.append("run_failed_event")
    else:
        if {"run_started", "run_completed"}.issubset(set(event_types)):
            checks.append("run_lifecycle_events")
        else:
            failures.append("run_lifecycle_events")
        if scenario.progress_events:
            if "progress" in event_types:
                checks.append("progress_event")
            else:
                failures.append("progress_event")

    return {
        "scenario_id": scenario.scenario_id,
        "passed": not failures,
        "checks": checks,
        "failures": failures,
        "response_status": str(response.get("status") or ""),
        "event_types": event_types,
    }


def summarize_canvas_chat_harness_results(results: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    rows = [dict(item or {}) for item in results]
    passed = [row for row in rows if bool(row.get("passed"))]
    failed = [row for row in rows if not bool(row.get("passed"))]
    return {
        "total": len(rows),
        "passed": len(passed),
        "failed": len(failed),
        "failed_scenarios": [str(row.get("scenario_id") or "") for row in failed],
    }


async def run_canvas_chat_harness_scenario(
    scenario: CanvasChatHarnessScenario,
    *,
    session_storage_root: str | Path | None = None,
) -> dict[str, Any]:
    from server import mcp_server

    temp_dir_cm = None
    if session_storage_root is None:
        temp_dir_cm = tempfile.TemporaryDirectory(prefix="timus_f3_chat_")
        session_root = Path(temp_dir_cm.name)
    else:
        session_root = Path(session_storage_root)
        session_root.mkdir(parents=True, exist_ok=True)

    mcp_server._chat_history.clear()
    sse_events: list[dict[str, Any]] = []

    async def _fake_build_tools_description() -> str:
        return "tools"

    async def _fake_get_agent_decision(query: str, session_id: str | None = None, request_id: str = "") -> str:
        return scenario.selected_agent

    async def _fake_run_agent(
        agent_name: str,
        query: str,
        tools_description: str,
        session_id: str | None = None,
    ) -> Any:
        hook = getattr(fake_dispatcher, "_agent_progress_hook", None)
        for event in scenario.progress_events:
            if callable(hook):
                hook(dict(event))
        if scenario.raise_error:
            raise RuntimeError(scenario.raise_error)
        return scenario.agent_result

    fake_dispatcher = SimpleNamespace(
        get_agent_decision=_fake_get_agent_decision,
        run_agent=_fake_run_agent,
    )

    original_module = sys.modules.get("main_dispatcher")
    try:
        with (
            patch.object(mcp_server, "_build_tools_description", _fake_build_tools_description),
            patch.object(mcp_server, "_semantic_store_chat_turn", lambda **kwargs: None),
            patch.object(mcp_server, "_semantic_recall_chat_turns", lambda **kwargs: []),
            patch.object(mcp_server, "_log_chat_interaction", lambda **kwargs: None),
            patch.object(mcp_server, "_broadcast_sse", lambda event: sse_events.append(dict(event))),
            patch.dict(os.environ, {"TIMUS_SESSION_STORAGE_ROOT": str(session_root)}, clear=False),
        ):
            sys.modules["main_dispatcher"] = fake_dispatcher
            raw_response = await mcp_server.canvas_chat(_FakeRequest(scenario.request_payload))
    finally:
        if original_module is None:
            sys.modules.pop("main_dispatcher", None)
        else:
            sys.modules["main_dispatcher"] = original_module
        if temp_dir_cm is not None:
            temp_dir_cm.cleanup()

    response_payload = _normalize_response_payload(raw_response)
    evaluation = evaluate_canvas_chat_harness_result(
        scenario,
        {
            "response": response_payload,
            "sse_events": sse_events,
        },
    )
    return {
        "scenario_id": scenario.scenario_id,
        "response": response_payload,
        "sse_events": sse_events,
        "evaluation": evaluation,
    }


async def run_canvas_chat_parity_harness(
    scenarios: Sequence[CanvasChatHarnessScenario] | None = None,
    *,
    session_storage_root: str | Path | None = None,
) -> dict[str, Any]:
    selected = list(scenarios or build_default_canvas_chat_parity_scenarios())
    results: list[dict[str, Any]] = []
    for scenario in selected:
        results.append(
            await run_canvas_chat_harness_scenario(
                scenario,
                session_storage_root=session_storage_root,
            )
        )

    evaluations = [dict(item.get("evaluation") or {}) for item in results]
    return {
        "contract_version": "canvas_chat_parity_harness_v1",
        "results": results,
        "summary": summarize_canvas_chat_harness_results(evaluations),
    }


def run_canvas_chat_parity_harness_sync(
    scenarios: Sequence[CanvasChatHarnessScenario] | None = None,
    *,
    session_storage_root: str | Path | None = None,
) -> dict[str, Any]:
    return asyncio.run(
        run_canvas_chat_parity_harness(
            scenarios=scenarios,
            session_storage_root=session_storage_root,
        )
    )
