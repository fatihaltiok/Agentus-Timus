from __future__ import annotations

from datetime import datetime
from typing import Any, Mapping, Sequence
from unittest.mock import patch

from orchestration.approval_auth_contract import (
    build_auth_required_workflow_payload,
    build_challenge_required_workflow_payload,
    build_user_mediated_login_workflow_payload,
    derive_user_action_blocker_reason,
)
from orchestration.longrunner_transport import (
    SCHEMA_VERSION as LONGRUNNER_SCHEMA_VERSION,
    is_terminal_event_type,
    make_blocker_event,
    make_progress_event,
    make_run_completed_event,
)
from orchestration.phase_e_operator_snapshot import build_phase_e_operator_snapshot
from orchestration.typed_task_packet import (
    REQUEST_PREFLIGHT_SCHEMA_VERSION,
    TASK_PACKET_SCHEMA_VERSION,
    build_request_preflight,
    build_typed_task_packet,
)


PHASE_F_CONTRACT_REPORT_VERSION = "phase_f_contract_eval_v1"


def _iso_now() -> str:
    return datetime.now().astimezone().replace(microsecond=0).isoformat()


def _text(value: Any, *, limit: int = 160) -> str:
    text = str(value or "").strip()
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "..."


def _normalize_refs(values: Sequence[Any] | None, *, limit: int = 6) -> list[str]:
    refs: list[str] = []
    for raw in list(values or []):
        ref = _text(raw, limit=180)
        if not ref or ref in refs:
            continue
        refs.append(ref)
        if len(refs) >= limit:
            break
    return refs


def _normalize_check_map(checks: Mapping[str, Any] | None) -> dict[str, bool]:
    normalized: dict[str, bool] = {}
    for raw_key, raw_value in dict(checks or {}).items():
        key = _text(raw_key, limit=96).lower()
        if not key:
            continue
        normalized[key] = bool(raw_value)
    return normalized


def build_phase_f_contract_result(
    *,
    contract_id: str,
    title: str,
    checks: Mapping[str, Any],
    evidence: Mapping[str, Any] | None = None,
    refs: Sequence[Any] | None = None,
    area: str = "",
) -> dict[str, Any]:
    normalized_checks = _normalize_check_map(checks)
    failed_checks = [key for key, passed in normalized_checks.items() if not passed]
    passed_checks = [key for key, passed in normalized_checks.items() if passed]
    passed = not failed_checks
    return {
        "contract_id": _text(contract_id, limit=96).lower(),
        "title": _text(title, limit=180),
        "area": _text(area, limit=96).lower(),
        "passed": passed,
        "check_count": len(normalized_checks),
        "passed_checks": passed_checks,
        "failed_checks": failed_checks,
        "reason": "ok" if passed else failed_checks[0],
        "evidence": dict(evidence or {}),
        "refs": _normalize_refs(refs),
    }


def summarize_phase_f_contract_results(results: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    total = 0
    passed_total = 0
    failed_contracts: list[str] = []
    areas: list[str] = []

    for raw in list(results or []):
        if not isinstance(raw, Mapping):
            continue
        total += 1
        passed = bool(raw.get("passed"))
        if passed:
            passed_total += 1
        else:
            contract_id = _text(raw.get("contract_id"), limit=96).lower() or "unknown_contract"
            if contract_id not in failed_contracts:
                failed_contracts.append(contract_id)
        area = _text(raw.get("area"), limit=96).lower()
        if area and area not in areas:
            areas.append(area)

    failed_total = max(0, total - passed_total)
    state = "pass" if failed_total == 0 else "fail"
    return {
        "state": state,
        "total": total,
        "passed": passed_total,
        "failed": failed_total,
        "pass_rate": round(float(passed_total) / max(total, 1), 3),
        "failed_contracts": failed_contracts[:8],
        "areas": areas[:8],
    }


def evaluate_phase_d_workflow_contract() -> dict[str, Any]:
    auth_payload = build_auth_required_workflow_payload(
        url="https://x.com/example/status/1",
        platform="twitter",
        message="X verlangt Login.",
        user_action_required="Bitte bestaetige den Login selbst.",
    )
    login_payload = build_user_mediated_login_workflow_payload(
        service="github",
        url="https://github.com/login",
    )
    challenge_payload = build_challenge_required_workflow_payload(
        service="github",
        challenge_type="2fa",
    )
    blocker_reason = derive_user_action_blocker_reason(login_payload)

    return build_phase_f_contract_result(
        contract_id="phase_d_approval_auth_workflow",
        title="Phase D approval/auth workflows stay normalized and resumable",
        area="approval_auth",
        checks={
            "auth_required_status": auth_payload.get("status") == "auth_required",
            "auth_required_flag": auth_payload.get("auth_required") is True,
            "auth_service_alias": auth_payload.get("service") == "x",
            "awaiting_user_status": login_payload.get("status") == "awaiting_user",
            "awaiting_user_resume_hint": bool(login_payload.get("resume_hint")),
            "challenge_required_status": challenge_payload.get("status") == "challenge_required",
            "challenge_has_resume_hint": bool(challenge_payload.get("resume_hint")),
            "challenge_type_preserved": challenge_payload.get("challenge_type") == "2fa",
            "legacy_blocker_reason": blocker_reason == "user_action_required",
        },
        evidence={
            "auth_workflow_id": _text(auth_payload.get("workflow_id"), limit=64),
            "login_step": _text(login_payload.get("step"), limit=64),
            "challenge_reason": _text(challenge_payload.get("reason"), limit=64),
            "challenge_user_action": _text(challenge_payload.get("user_action_required"), limit=120),
        },
        refs=[
            "docs/PHASE_D_APPROVAL_AUTH_PREP.md",
            "orchestration/approval_auth_contract.py",
            "tests/test_approval_auth_contract.py",
        ],
    )


def evaluate_longrunner_visibility_contract() -> dict[str, Any]:
    workflow_payload = build_challenge_required_workflow_payload(
        service="github",
        challenge_type="2fa",
    )
    blocker_reason = derive_user_action_blocker_reason(workflow_payload)
    blocker = make_blocker_event(
        request_id="req-f4-1",
        run_id="run-f4-1",
        session_id="sess-f4-1",
        agent="executor",
        stage="challenge_gate",
        seq=2,
        message="GitHub verlangt eine Sicherheitspruefung.",
        blocker_reason=blocker_reason,
        user_action_required=str(workflow_payload.get("user_action_required") or ""),
        workflow_id=str(workflow_payload.get("workflow_id") or ""),
        workflow_status=str(workflow_payload.get("status") or ""),
        workflow_service=str(workflow_payload.get("service") or ""),
        workflow_reason=str(workflow_payload.get("reason") or ""),
        workflow_message=str(workflow_payload.get("message") or ""),
        workflow_resume_hint=str(workflow_payload.get("resume_hint") or ""),
        workflow_challenge_type=str(workflow_payload.get("challenge_type") or ""),
        workflow_approval_scope=str(workflow_payload.get("approval_scope") or ""),
    )
    progress = make_progress_event(
        request_id="req-f4-1",
        run_id="run-f4-1",
        session_id="sess-f4-1",
        agent="executor",
        stage="precheck",
        seq=1,
        message="Workflow wird vorbereitet.",
        progress_hint="starting",
        next_expected_update_s=10,
    )
    completed = make_run_completed_event(
        request_id="req-f4-1",
        run_id="run-f4-1",
        session_id="sess-f4-1",
        agent="executor",
        seq=3,
        message="Workflow abgeschlossen.",
    )

    return build_phase_f_contract_result(
        contract_id="longrunner_user_visible_transport",
        title="Longrunner events preserve blocker context and terminal semantics",
        area="longrunner",
        checks={
            "progress_event_schema": progress.schema_version == LONGRUNNER_SCHEMA_VERSION,
            "progress_not_terminal": is_terminal_event_type(progress.type) is False,
            "blocker_type": blocker.type == "blocker",
            "blocker_reason_preserved": blocker.blocker_reason == blocker_reason,
            "blocker_workflow_status": blocker.workflow_status == "challenge_required",
            "blocker_resume_hint": bool(blocker.workflow_resume_hint),
            "blocker_challenge_type": blocker.workflow_challenge_type == "2fa",
            "terminal_completion_event": is_terminal_event_type(completed.type) is True,
            "shared_run_id": progress.run_id == blocker.run_id == completed.run_id,
        },
        evidence={
            "run_id": blocker.run_id,
            "workflow_id": blocker.workflow_id,
            "workflow_status": blocker.workflow_status,
            "terminal_event_type": completed.type,
        },
        refs=[
            "orchestration/longrunner_transport.py",
            "tests/test_longrunner_transport_contract.py",
            "docs/PHASE_F_PLAN.md",
        ],
    )


def evaluate_typed_handoff_contract() -> dict[str, Any]:
    packet = build_typed_task_packet(
        packet_type="deep_research",
        objective="Analysiere den Frontdoor-Routing-Fehler und liefere einen reproduzierbaren Fixplan.",
        scope={
            "surface": "dispatcher",
            "incident_class": "frontdoor_misclassification",
            "target": "build_setup_intent_vs_research_intent",
            "constraints": "keep_runtime_stable",
            "source": "phase_f_contract_eval",
            "environment": "production_like",
        },
        acceptance_criteria=[
            "task packet is complete",
            "request preflight is machine readable",
            "handoff can be compacted before dispatch",
            "runtime keeps explicit escalation policy",
        ],
        allowed_tools=[
            "start_deep_research",
            "generate_research_report",
            "search_web",
            "read_webpage",
        ],
        reporting_contract={
            "must_include": [
                "sources_for_live_claims",
                "artifact_or_report_summary",
                "explicit_operator_risks",
            ],
            "style": "concise_structured",
            "max_sections": "4",
        },
        escalation_policy={
            "on_provider_pressure": "compact_context",
            "on_live_claims": "attach_sources",
            "on_blocker": "escalate_to_operator",
        },
        state_context={
            "session_mode": "phase_f_contract_eval",
            "recent_failure": "research_intent_false_positive",
            "lane": "dispatcher",
            "requested_depth": "high",
        },
    )

    huge_request = "R" * 6000
    huge_handoff = "H" * 5000
    with patch.dict(
        "os.environ",
        {
            "MAX_CONTEXT_TOKENS": "512",
            "WM_MAX_CHARS": "10000",
        },
        clear=False,
    ):
        preflight = build_request_preflight(
            packet=packet,
            original_request=huge_request,
            rendered_handoff=huge_handoff,
            task_type="deep_research",
            recipe_id="web_research_only",
        )

    issues = list(preflight.get("issues") or [])
    actions = list(preflight.get("actions") or [])
    metrics = dict(preflight.get("metrics") or {})

    return build_phase_f_contract_result(
        contract_id="typed_handoff_and_preflight",
        title="Typed task packets and request preflight stay explicit under pressure",
        area="handoff",
        checks={
            "packet_schema_version": packet.get("schema_version") == TASK_PACKET_SCHEMA_VERSION,
            "packet_has_objective": bool(packet.get("objective")),
            "packet_has_allowed_tools": len(list(packet.get("allowed_tools") or [])) >= 1,
            "packet_has_reporting_contract": bool(packet.get("reporting_contract")),
            "preflight_schema_version": preflight.get("schema_version") == REQUEST_PREFLIGHT_SCHEMA_VERSION,
            "preflight_state_blocked": preflight.get("state") == "blocked",
            "preflight_marks_blocked": preflight.get("blocked") is True,
            "preflight_request_hard_limit": "request_chars_hard_limit" in issues,
            "preflight_split_action": "split_request_before_dispatch" in actions,
            "preflight_provider_pressure": "provider_window_pressure" in issues or "provider_window_hard_limit" in issues,
        },
        evidence={
            "packet_type": _text(packet.get("packet_type"), limit=64),
            "packet_chars": int(metrics.get("packet_chars") or 0),
            "handoff_chars": int(metrics.get("handoff_chars") or 0),
            "request_chars": int(metrics.get("original_request_chars") or 0),
            "preflight_issues": issues[:6],
        },
        refs=[
            "orchestration/typed_task_packet.py",
            "main_dispatcher.py",
            "tests/test_typed_task_packet.py",
            "tests/test_meta_handoff.py",
        ],
    )


def _sample_operator_snapshot() -> dict[str, Any]:
    return build_phase_e_operator_snapshot(
        system_snapshot={
            "services": {
                "mcp": {"ok": True, "active": "active", "uptime_seconds": 120.0},
                "dispatcher": {"ok": True, "active": "active", "uptime_seconds": 90.0},
                "qdrant": {"ok": True, "active": "active", "uptime_seconds": 300.0},
            },
            "ops": {"state": "critical", "critical_alerts": 1, "warnings": 0},
            "mcp_runtime": {"state": "healthy", "reason": "steady_state", "ready": True},
            "request_runtime": {"state": "ok", "reason": "steady_state", "chat_requests_total": 4, "task_failed_total": 0},
            "stability_gate": {"state": "hold"},
        },
        observation_summary={
            "improvement_runtime": {
                "autonomy_decisions_total": 3,
                "enqueue_creation_rate": 0.33,
                "verified_rate": 0.5,
                "not_verified_rate": 0.5,
            },
            "memory_curation_runtime": {
                "autonomy_completion_rate": 1.0,
                "verification_pass_rate": 1.0,
                "retrieval_pass_rate": 1.0,
                "rollback_rate": 0.0,
            },
        },
        recent_events=[
            {
                "event_type": "improvement_task_autonomy_event",
                "observed_at": "2026-04-17T10:00:00+02:00",
                "payload": {
                    "candidate_id": "m12:1",
                    "autoenqueue_state": "strict_force_off",
                    "rollout_guard_state": "strict_force_off",
                },
            },
            {
                "event_type": "memory_curation_autonomy_blocked",
                "observed_at": "2026-04-17T10:01:00+02:00",
                "payload": {
                    "state": "cooldown_active",
                    "reasons": ["recent_memory_curation_run"],
                    "snapshot_id": "snap-1",
                    "request_id": "req-mem-1",
                },
            },
        ],
        improvement_governance={
            "rollout_guard_state": "strict_force_off",
            "rollout_guard_blocked": True,
            "rollout_guard_reasons": ["policy_runtime:strict_force_off"],
            "shadowed_guard_states": ["verification_backpressure"],
            "shadowed_guard_reasons": {
                "verification_backpressure": ["verification_sample_total:3"],
            },
            "strict_force_off": True,
            "verification_backpressure": {
                "blocked": True,
                "active": False,
                "shadowed": True,
                "reasons": ["verification_sample_total:3"],
            },
        },
        improvement_candidate_views=[
            {"candidate_id": "m12:1", "summary": "tool:find_text_coordinates | prio=1.320"},
        ],
        memory_curation_status={
            "current_metrics": {
                "active_items": 100,
                "archived_items": 10,
                "summary_items": 3,
                "stale_active_items": 4,
            },
            "last_snapshots": [{"snapshot_id": "snap-2", "status": "completed"}],
            "pending_candidates": [
                {
                    "candidate_id": "mc:1",
                    "action": "summarize",
                    "category": "working_memory",
                    "tier": "ephemeral",
                    "reason": "group:working_memory",
                    "item_count": 5,
                }
            ],
            "autonomy_governance": {
                "state": "cooldown_active",
                "blocked": True,
                "reasons": ["recent_memory_curation_run"],
            },
            "quality_governance": {
                "state": "retrieval_backpressure",
                "blocked": True,
                "reasons": ["pass_rate=0.25", "failed_runs=2"],
            },
        },
        approval_surface={
            "state": "approval_required",
            "blocked": True,
            "pending_count": 1,
            "highest_risk_class": "critical",
            "requested_actions": ["rollback"],
            "lanes": ["improvement"],
            "oldest_pending_minutes": 42.0,
            "items": [
                {
                    "request_id": "req-1",
                    "lane": "improvement",
                    "risk_class": "critical",
                    "requested_action": "rollback",
                    "approval_reason": "rollback_requires_approval",
                }
            ],
        },
    )


def evaluate_runtime_lane_contract() -> dict[str, Any]:
    snapshot = _sample_operator_snapshot()
    operator_surface = dict(snapshot.get("operator_surface") or {})
    summary = dict(snapshot.get("summary") or {})
    governance = dict(snapshot.get("governance") or {})
    lanes = dict(snapshot.get("lanes") or {})

    return build_phase_f_contract_result(
        contract_id="runtime_lane_operator_surface",
        title="Runtime and self-improvement lanes stay unified in one operator surface",
        area="runtime_lanes",
        checks={
            "operator_surface_contract": operator_surface.get("contract_version") == "phase_e_operator_v1",
            "operator_surface_has_lanes": operator_surface.get("available_lanes") == ["improvement", "memory_curation"],
            "summary_blocked_lane_count": int(summary.get("blocked_lane_count") or 0) == 2,
            "summary_governance_state": summary.get("governance_state") == "strict_force_off",
            "summary_approval_pending": int(summary.get("approval_pending_count") or 0) == 1,
            "improvement_lane_state": dict(lanes.get("improvement") or {}).get("state") == "strict_force_off",
            "memory_lane_state": dict(lanes.get("memory_curation") or {}).get("state") == "cooldown_active",
            "governance_action_freeze": governance.get("action") == "freeze",
        },
        evidence={
            "governance_state": _text(summary.get("governance_state"), limit=64),
            "governance_action": _text(governance.get("action"), limit=32),
            "blocked_lanes": list(summary.get("blocked_lanes") or []),
            "approval_pending_count": int(summary.get("approval_pending_count") or 0),
        },
        refs=[
            "docs/PHASE_E_SELF_IMPROVEMENT_PLAN.md",
            "orchestration/phase_e_operator_snapshot.py",
            "tests/test_phase_e_operator_snapshot.py",
            "orchestration/autonomy_observation.py",
        ],
    )


def run_phase_f_contract_eval() -> dict[str, Any]:
    results = [
        evaluate_phase_d_workflow_contract(),
        evaluate_longrunner_visibility_contract(),
        evaluate_typed_handoff_contract(),
        evaluate_runtime_lane_contract(),
    ]
    return {
        "contract_version": PHASE_F_CONTRACT_REPORT_VERSION,
        "generated_at": _iso_now(),
        "results": results,
        "summary": summarize_phase_f_contract_results(results),
    }
