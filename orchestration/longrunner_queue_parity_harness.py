"""Deterministic parity harness for longrunner and queue runtime paths."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
import tempfile
from typing import Any, Callable, Mapping, Sequence

from orchestration.approval_auth_contract import (
    build_challenge_required_workflow_payload,
    build_user_mediated_login_workflow_payload,
    derive_user_action_blocker_reason,
)
from orchestration.longrunner_transport import (
    bind_longrun_context,
    is_terminal_event_type,
    make_blocker_event,
    make_progress_event,
    make_run_completed_event,
    make_run_failed_event,
    make_run_started_event,
    next_event_seq,
)
from orchestration.pending_workflow_state import (
    classify_pending_workflow_reply,
    pending_workflow_state_to_dict,
)
from orchestration.task_queue import TaskQueue, TaskType


@dataclass(frozen=True, slots=True)
class LongrunnerQueueParityScenario:
    scenario_id: str
    runner: Callable[[Path], Mapping[str, Any]]


def _normalize_mapping(value: Mapping[str, Any] | None) -> dict[str, Any]:
    return dict(value or {})


def _event_payloads(events: Sequence[Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for raw in list(events or []):
        if hasattr(raw, "to_dict"):
            rows.append(dict(raw.to_dict()))
        elif isinstance(raw, Mapping):
            rows.append(dict(raw))
    return rows


def _run_longrunner_success(_: Path) -> dict[str, Any]:
    with bind_longrun_context(run_id="run_f3_longrunner_success") as ctx:
        run_id = str(ctx.get("run_id") or "")
        events = [
            make_run_started_event(
                request_id="req-f3-longrunner-success",
                run_id=run_id,
                session_id="sess-f3-longrunner-success",
                agent="executor",
                seq=next_event_seq(),
                message="Lauf gestartet.",
            ),
            make_progress_event(
                request_id="req-f3-longrunner-success",
                run_id=run_id,
                session_id="sess-f3-longrunner-success",
                agent="executor",
                stage="fetching_sources",
                seq=next_event_seq(),
                message="Quellen werden gesammelt.",
                progress_hint="working",
                next_expected_update_s=12,
            ),
            make_run_completed_event(
                request_id="req-f3-longrunner-success",
                run_id=run_id,
                session_id="sess-f3-longrunner-success",
                agent="executor",
                seq=next_event_seq(),
                message="Lauf abgeschlossen.",
            ),
        ]
    return {"events": _event_payloads(events)}


def _run_longrunner_failure(_: Path) -> dict[str, Any]:
    with bind_longrun_context(run_id="run_f3_longrunner_failure") as ctx:
        run_id = str(ctx.get("run_id") or "")
        events = [
            make_run_started_event(
                request_id="req-f3-longrunner-failure",
                run_id=run_id,
                session_id="sess-f3-longrunner-failure",
                agent="research",
                seq=next_event_seq(),
                message="Lauf gestartet.",
            ),
            make_progress_event(
                request_id="req-f3-longrunner-failure",
                run_id=run_id,
                session_id="sess-f3-longrunner-failure",
                agent="research",
                stage="querying_sources",
                seq=next_event_seq(),
                message="Recherche laeuft.",
                progress_hint="working",
                next_expected_update_s=20,
            ),
            make_run_failed_event(
                request_id="req-f3-longrunner-failure",
                run_id=run_id,
                session_id="sess-f3-longrunner-failure",
                agent="research",
                stage="query_failed",
                seq=next_event_seq(),
                message="Recherche fehlgeschlagen.",
                error_class="provider_error",
                error_code="upstream_timeout",
            ),
        ]
    return {"events": _event_payloads(events)}


def _run_pending_login_resume(_: Path) -> dict[str, Any]:
    workflow = build_user_mediated_login_workflow_payload(
        service="github",
        url="https://github.com/login",
    )
    state = pending_workflow_state_to_dict(
        workflow,
        updated_at="2026-04-17T10:00:00Z",
        source_agent="visual",
        source_stage="login_form_ready",
    )
    blocker = make_blocker_event(
        request_id="req-f3-login-resume",
        run_id="run-f3-login-resume",
        session_id="sess-f3-login-resume",
        agent="visual",
        stage="login_form_ready",
        seq=1,
        message=str(state.get("message") or ""),
        blocker_reason=derive_user_action_blocker_reason(workflow),
        user_action_required=str(state.get("user_action_required") or ""),
        workflow_id=str(state.get("workflow_id") or ""),
        workflow_status=str(state.get("status") or ""),
        workflow_service=str(state.get("service") or ""),
        workflow_reason=str(state.get("reason") or ""),
        workflow_message=str(state.get("message") or ""),
        workflow_resume_hint=str(state.get("resume_hint") or ""),
    ).to_dict()
    reply = classify_pending_workflow_reply("ich bin eingeloggt", state)
    return {"state": state, "blocker_event": blocker, "reply": reply}


def _run_pending_challenge_resolution(_: Path) -> dict[str, Any]:
    workflow = build_challenge_required_workflow_payload(
        service="github",
        challenge_type="2fa",
    )
    state = pending_workflow_state_to_dict(
        workflow,
        updated_at="2026-04-17T10:05:00Z",
        source_agent="visual",
        source_stage="security_challenge",
    )
    blocker = make_blocker_event(
        request_id="req-f3-challenge-resolution",
        run_id="run-f3-challenge-resolution",
        session_id="sess-f3-challenge-resolution",
        agent="visual",
        stage="challenge_required",
        seq=1,
        message=str(state.get("message") or ""),
        blocker_reason=derive_user_action_blocker_reason(workflow),
        user_action_required=str(state.get("user_action_required") or ""),
        workflow_id=str(state.get("workflow_id") or ""),
        workflow_status=str(state.get("status") or ""),
        workflow_service=str(state.get("service") or ""),
        workflow_reason=str(state.get("reason") or ""),
        workflow_message=str(state.get("message") or ""),
        workflow_resume_hint=str(state.get("resume_hint") or ""),
        workflow_challenge_type=str(state.get("challenge_type") or ""),
    ).to_dict()
    reply = classify_pending_workflow_reply("2fa erledigt, ich bin weiter", state)
    return {"state": state, "blocker_event": blocker, "reply": reply}


def _run_queue_retry_then_complete(root: Path) -> dict[str, Any]:
    queue = TaskQueue(db_path=root / "queue_retry_then_complete.db")
    task_id = queue.add(
        "F3 Queue Retry und Abschluss pruefen",
        task_type=TaskType.DELEGATED,
        target_agent="executor",
        max_retries=2,
    )
    first_claim = queue.claim_next()
    retry_scheduled = queue.fail(task_id, "voruebergehender fehler")
    second_claim = queue.claim_next()
    queue.complete(task_id, "fertig")
    final_state = queue.get_by_id(task_id)
    return {
        "task_id": task_id,
        "first_claim": first_claim or {},
        "retry_scheduled": retry_scheduled,
        "second_claim": second_claim or {},
        "final_state": final_state or {},
    }


def _run_queue_stale_recovery(root: Path) -> dict[str, Any]:
    queue = TaskQueue(db_path=root / "queue_stale_recovery.db")
    task_id = queue.add(
        "F3 Queue Stale Recovery pruefen",
        task_type=TaskType.DELEGATED,
        target_agent="executor",
        max_retries=3,
    )
    claimed = queue.claim_next()
    stale_started_at = (datetime.now() - timedelta(minutes=10)).isoformat()
    with queue._conn() as conn:  # type: ignore[attr-defined]
        conn.execute(
            "UPDATE tasks SET status=?, started_at=? WHERE id=?",
            ("in_progress", stale_started_at, task_id),
        )
    recovery = queue.recover_stale_in_progress(stale_after_minutes=1)
    final_state = queue.get_by_id(task_id)
    return {
        "task_id": task_id,
        "claimed": claimed or {},
        "recovery": recovery,
        "final_state": final_state or {},
    }


def build_default_longrunner_queue_parity_scenarios() -> list[LongrunnerQueueParityScenario]:
    return [
        LongrunnerQueueParityScenario(
            scenario_id="longrunner_success_terminal",
            runner=_run_longrunner_success,
        ),
        LongrunnerQueueParityScenario(
            scenario_id="longrunner_failure_terminal",
            runner=_run_longrunner_failure,
        ),
        LongrunnerQueueParityScenario(
            scenario_id="pending_login_resume",
            runner=_run_pending_login_resume,
        ),
        LongrunnerQueueParityScenario(
            scenario_id="pending_challenge_resolution",
            runner=_run_pending_challenge_resolution,
        ),
        LongrunnerQueueParityScenario(
            scenario_id="queue_retry_then_complete",
            runner=_run_queue_retry_then_complete,
        ),
        LongrunnerQueueParityScenario(
            scenario_id="queue_stale_recovery",
            runner=_run_queue_stale_recovery,
        ),
    ]


def evaluate_longrunner_queue_parity_result(
    scenario: LongrunnerQueueParityScenario,
    payload: Mapping[str, Any],
) -> dict[str, Any]:
    data = _normalize_mapping(payload)
    checks: list[str] = []
    failures: list[str] = []

    if scenario.scenario_id == "longrunner_success_terminal":
        events = list(data.get("events") or [])
        event_types = [str(_normalize_mapping(item).get("type") or "") for item in events]
        run_ids = {str(_normalize_mapping(item).get("run_id") or "") for item in events}
        if event_types == ["run_started", "progress", "run_completed"]:
            checks.append("event_sequence")
        else:
            failures.append("event_sequence")
        if len(run_ids) == 1 and "" not in run_ids:
            checks.append("shared_run_id")
        else:
            failures.append("shared_run_id")
        if events and is_terminal_event_type(event_types[-1]):
            checks.append("terminal_completion")
        else:
            failures.append("terminal_completion")
    elif scenario.scenario_id == "longrunner_failure_terminal":
        events = list(data.get("events") or [])
        last_event = _normalize_mapping(events[-1]) if events else {}
        if str(last_event.get("type") or "") == "run_failed":
            checks.append("failed_terminal_event")
        else:
            failures.append("failed_terminal_event")
        if is_terminal_event_type(str(last_event.get("type") or "")):
            checks.append("terminal_failure")
        else:
            failures.append("terminal_failure")
        if str(last_event.get("error_class") or "") and str(last_event.get("error_code") or ""):
            checks.append("error_metadata")
        else:
            failures.append("error_metadata")
    elif scenario.scenario_id == "pending_login_resume":
        state = _normalize_mapping(data.get("state"))
        blocker = _normalize_mapping(data.get("blocker_event"))
        reply = _normalize_mapping(data.get("reply"))
        if str(state.get("status") or "") == "awaiting_user":
            checks.append("pending_status")
        else:
            failures.append("pending_status")
        if str(blocker.get("blocker_reason") or "") == "user_action_required":
            checks.append("blocker_reason")
        else:
            failures.append("blocker_reason")
        if str(reply.get("reply_kind") or "") == "resume_requested":
            checks.append("resume_reply")
        else:
            failures.append("resume_reply")
        if str(blocker.get("workflow_id") or "") == str(reply.get("workflow_id") or ""):
            checks.append("workflow_id")
        else:
            failures.append("workflow_id")
    elif scenario.scenario_id == "pending_challenge_resolution":
        state = _normalize_mapping(data.get("state"))
        blocker = _normalize_mapping(data.get("blocker_event"))
        reply = _normalize_mapping(data.get("reply"))
        if str(state.get("status") or "") == "challenge_required":
            checks.append("pending_status")
        else:
            failures.append("pending_status")
        if str(blocker.get("workflow_challenge_type") or "") == "2fa":
            checks.append("challenge_type")
        else:
            failures.append("challenge_type")
        if str(reply.get("reply_kind") or "") == "challenge_resolved":
            checks.append("challenge_reply")
        else:
            failures.append("challenge_reply")
        if str(reply.get("challenge_type") or "") == "2fa":
            checks.append("reply_challenge_type")
        else:
            failures.append("reply_challenge_type")
    elif scenario.scenario_id == "queue_retry_then_complete":
        first_claim = _normalize_mapping(data.get("first_claim"))
        second_claim = _normalize_mapping(data.get("second_claim"))
        final_state = _normalize_mapping(data.get("final_state"))
        if str(first_claim.get("status") or "") == "in_progress":
            checks.append("first_claim")
        else:
            failures.append("first_claim")
        if bool(data.get("retry_scheduled")) is True:
            checks.append("retry_scheduled")
        else:
            failures.append("retry_scheduled")
        if str(second_claim.get("status") or "") == "in_progress":
            checks.append("second_claim")
        else:
            failures.append("second_claim")
        if str(final_state.get("status") or "") == "completed":
            checks.append("final_status")
        else:
            failures.append("final_status")
    elif scenario.scenario_id == "queue_stale_recovery":
        recovery = _normalize_mapping(data.get("recovery"))
        final_state = _normalize_mapping(data.get("final_state"))
        if int(recovery.get("requeued") or 0) == 1:
            checks.append("requeued")
        else:
            failures.append("requeued")
        if str(final_state.get("status") or "") == "pending":
            checks.append("final_status")
        else:
            failures.append("final_status")
        if int(final_state.get("retry_count") or 0) == 1:
            checks.append("retry_count")
        else:
            failures.append("retry_count")
    else:
        failures.append("unknown_scenario")

    return {
        "scenario_id": scenario.scenario_id,
        "passed": not failures,
        "checks": checks,
        "failures": failures,
    }


def summarize_longrunner_queue_parity_results(results: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    rows = [_normalize_mapping(item) for item in list(results or [])]
    failed = [row for row in rows if not bool(row.get("passed"))]
    return {
        "total": len(rows),
        "passed": len(rows) - len(failed),
        "failed": len(failed),
        "failed_scenarios": [str(row.get("scenario_id") or "") for row in failed],
    }


def run_longrunner_queue_parity_harness_scenario(
    scenario: LongrunnerQueueParityScenario,
) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix=f"timus_{scenario.scenario_id}_") as temp_dir:
        payload = _normalize_mapping(scenario.runner(Path(temp_dir)))
    evaluation = evaluate_longrunner_queue_parity_result(scenario, payload)
    return {
        "scenario_id": scenario.scenario_id,
        "payload": payload,
        "evaluation": evaluation,
    }


def run_longrunner_queue_parity_harness(
    scenarios: Sequence[LongrunnerQueueParityScenario] | None = None,
) -> dict[str, Any]:
    selected = list(scenarios or build_default_longrunner_queue_parity_scenarios())
    results = [run_longrunner_queue_parity_harness_scenario(scenario) for scenario in selected]
    evaluations = [_normalize_mapping(item.get("evaluation")) for item in results]
    return {
        "contract_version": "longrunner_queue_parity_harness_v1",
        "results": results,
        "summary": summarize_longrunner_queue_parity_results(evaluations),
    }
