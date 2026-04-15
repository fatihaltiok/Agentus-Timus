from __future__ import annotations

import json
import os
import threading
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_LOG_PATH = PROJECT_ROOT / "logs" / "autonomy_observation.jsonl"
DEFAULT_STATE_PATH = PROJECT_ROOT / "logs" / "autonomy_observation_state.json"

_AUTONOMY_OBSERVATION_STORE: Optional["AutonomyObservationStore"] = None
_RECENT_CORRELATION_LIMIT = 8

# C2: abgeschlossene Menge der Nutzerwirkungs-Klassen.
# Emitter werden erst gesetzt wenn der Trigger-Pfad semantisch gesichert ist.
_USER_IMPACT_EVENT_TYPES: frozenset = frozenset({
    "response_never_delivered",
    "silent_failure",
    "user_visible_timeout",
    "misroute_recovered",
})


def _iso_now() -> str:
    return datetime.now().astimezone().isoformat()


def _parse_iso_datetime(value: str) -> Optional[datetime]:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def _normalize_duration_days(value: Any, *, default: int = 7) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = int(default)
    return max(0, parsed)


def _normalize_counter_key(value: Any, *, fallback: str = "unknown") -> str:
    normalized = str(value or "").strip().lower()
    if not normalized:
        return fallback
    cleaned = "".join(ch if ch.isalnum() or ch in {"_", "-"} else "_" for ch in normalized)
    return cleaned[:80] or fallback


def _should_skip_default_test_writes() -> bool:
    """Verhindert, dass Pytest-Läufe in das produktive Beobachtungslog schreiben.

    Standardfall:
    - unter Pytest keine Writes in `logs/autonomy_observation.jsonl`
    Ausnahmen:
    - explizit erlaubt über `AUTONOMY_OBSERVATION_ALLOW_TEST_WRITES`
    - oder wenn Tests einen eigenen Log-/State-Pfad gesetzt haben
    """
    if not str(os.getenv("PYTEST_CURRENT_TEST") or "").strip():
        return False
    allow = str(os.getenv("AUTONOMY_OBSERVATION_ALLOW_TEST_WRITES", "")).strip().lower()
    if allow in {"1", "true", "yes", "on"}:
        return False
    if os.getenv("AUTONOMY_OBSERVATION_LOG_PATH") or os.getenv("AUTONOMY_OBSERVATION_STATE_PATH"):
        return False
    return True


def _json_safe(value: Any, *, depth: int = 0) -> Any:
    if depth >= 4:
        return str(value)[:240]
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return value[:240]
    if isinstance(value, dict):
        safe: Dict[str, Any] = {}
        for key, item in list(value.items())[:24]:
            safe[str(key)[:80]] = _json_safe(item, depth=depth + 1)
        return safe
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(item, depth=depth + 1) for item in list(value)[:24]]
    return str(value)[:240]


def _classify_user_impact_event(event_type: str) -> str:
    """Gibt den kanonischen User-Impact-Klassennamen zurück, oder 'none'.

    Pure Funktion — kein IO. Abgeschlossene Wertemenge, CrossHair-kontraktfähig.
    """
    normalized = _normalize_counter_key(event_type)
    return normalized if normalized in _USER_IMPACT_EVENT_TYPES else "none"


def build_incident_trace(
    events: List[Dict[str, Any]],
    request_id: str,
) -> List[Dict[str, Any]]:
    """Filtert alle Events mit matching request_id und gibt sie chronologisch sortiert zurück.

    Pure Funktion — kein IO. Testbar mit CrossHair und Hypothesis.
    Leere request_id → leere Liste (keine Exception).

    Kerninvariante (strukturell bewiesen in lean/CiSpecs.lean):
    len(result) ≤ len(events)
    """
    target = str(request_id or "").strip()
    if not target:
        return []
    matched = [
        e
        for e in events
        if isinstance(e, dict)
        and str((dict(e.get("payload") or {}).get("request_id") or "")).strip() == target
    ]
    # Zeitordnung via _parse_iso_datetime — toleriert Z, Offsets und naive Formate.
    # Bei unparsbaren Zeitstempeln: stabiler Fallback auf leeres datetime (sortiert nach vorne),
    # Originalreihenfolge innerhalb gleicher Zeitstempel bleibt erhalten (stabile Sortierung).
    _FALLBACK_DT = datetime.min.replace(tzinfo=None)

    def _sort_key(e: dict) -> datetime:
        dt = _parse_iso_datetime(str(e.get("observed_at") or ""))
        if dt is None:
            return _FALLBACK_DT
        # Aware → UTC konvertieren, dann naive für Vergleich; naive bleibt wie ist.
        if dt.tzinfo is not None:
            return dt.astimezone(timezone.utc).replace(tzinfo=None)
        return dt

    return sorted(matched, key=_sort_key)


def summarize_autonomy_events(events: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    summary: Dict[str, Any] = {
        "total_events": 0,
        "event_counts": {},
        "meta_diagnostics": {
            "dispatcher_meta_fallback_total": 0,
            "dispatcher_meta_fallback_by_reason": {},
            "specialist_delegations_total": 0,
            "specialist_delegation_errors_total": 0,
            "specialist_delegation_by_agent": {},
            "direct_tool_calls_total": 0,
            "direct_tool_errors_total": 0,
            "direct_tool_by_method": {},
            "lead_diagnosis_selected_total": 0,
            "diagnosis_conflicts_total": 0,
            "developer_tasks_compiled_total": 0,
            "unverified_claims_suppressed_total": 0,
            "primary_fix_tasks_total": 0,
            "followup_tasks_deferred_total": 0,
            "root_cause_gate_blocked_total": 0,
            "task_mix_suppressed_total": 0,
        },
        "recipe_outcomes": {
            "total": 0,
            "success_total": 0,
            "failure_total": 0,
            "planner_adopted_total": 0,
            "planner_fallback_total": 0,
            "runtime_gap_outcomes_total": 0,
            "average_duration_ms": 0,
            "by_recipe": {},
        },
        "runtime_gaps": {
            "total_insertions": 0,
            "by_reason": {},
        },
        "self_hardening": {
            "total": 0,
            "by_stage": {},
            "by_status": {},
            "self_modify_started_total": 0,
            "self_modify_finished_total": 0,
            "self_modify_success_total": 0,
            "self_modify_blocked_total": 0,
            "self_modify_rolled_back_total": 0,
            "self_modify_error_total": 0,
        },
        "request_correlation": {
            "chat_requests_total": 0,
            "chat_completed_total": 0,
            "chat_failed_total": 0,
            "dispatcher_routes_total": 0,
            "request_routes_total": 0,
            "task_routes_total": 0,
            "task_started_total": 0,
            "task_completed_total": 0,
            "task_failed_total": 0,
            "user_visible_failures_total": 0,
            "by_agent": {},
            "by_source": {},
            "by_error_class": {},
            "recent_requests": [],
            "recent_routes": [],
            "recent_outcomes": [],
            "recent_failures": [],
        },
        "meta_context_state": {
            "turn_type_selected_total": 0,
            "response_mode_selected_total": 0,
            "policy_mode_selected_total": 0,
            "policy_override_total": 0,
            "self_model_bound_total": 0,
            "context_bundle_built_total": 0,
            "context_slot_selected_total": 0,
            "context_slot_suppressed_total": 0,
            "conversation_state_updated_total": 0,
            "conversation_state_decayed_total": 0,
            "topic_shift_total": 0,
            "historical_topic_attached_total": 0,
            "preference_captured_total": 0,
            "preference_applied_total": 0,
            "preference_scope_selected_total": 0,
            "preference_conflict_resolved_total": 0,
            "context_misread_suspected_total": 0,
            "healthy_bundle_rate": 0.0,
            "misread_rate": 0.0,
            "state_update_coverage": 0.0,
            "preference_roundtrip_rate": 0.0,
            "policy_override_rate": 0.0,
            "by_turn_type": {},
            "by_response_mode": {},
            "by_policy_reason": {},
            "by_slot": {},
            "by_suppression_reason": {},
            "by_decay_reason": {},
            "by_historical_time_label": {},
            "by_preference_scope": {},
            "by_preference_family": {},
            "by_misread_reason": {},
            "recent_misreads": [],
        },
        "specialist_context": {
            "strategy_selected_total": 0,
            "specialist_signal_total": 0,
            "needs_meta_reframe_total": 0,
            "context_mismatch_total": 0,
            "agent_signal_rate": 0.0,
            "signal_reframe_rate": 0.0,
            "by_agent": {},
            "by_strategy_mode": {},
            "by_response_mode": {},
            "by_signal": {},
            "by_signal_source": {},
        },
        "communication_runtime": {
            "tasks_started_total": 0,
            "tasks_completed_total": 0,
            "tasks_failed_total": 0,
            "tasks_partial_total": 0,
            "email_send_success_total": 0,
            "email_send_failed_total": 0,
            "by_source": {},
            "by_backend": {},
            "by_agent": {},
            "by_channel": {},
        },
        "challenge_runtime": {
            "challenge_required_total": 0,
            "challenge_resume_total": 0,
            "challenge_resolved_total": 0,
            "challenge_reblocked_total": 0,
            "resolution_rate": 0.0,
            "reblock_rate": 0.0,
            "by_service": {},
            "by_challenge_type": {},
            "by_reply_kind": {},
        },
        "improvement_runtime": {
            "autonomy_decisions_total": 0,
            "autoenqueue_ready_total": 0,
            "enqueue_created_total": 0,
            "enqueue_deduped_total": 0,
            "enqueue_cooldown_active_total": 0,
            "enqueue_blocked_total": 0,
            "execution_started_total": 0,
            "execution_terminal_total": 0,
            "execution_verified_total": 0,
            "execution_ended_unverified_total": 0,
            "execution_blocked_total": 0,
            "execution_verification_failed_total": 0,
            "execution_rolled_back_total": 0,
            "execution_failed_other_total": 0,
            "enqueue_creation_rate": 0.0,
            "verified_rate": 0.0,
            "not_verified_rate": 0.0,
            "by_autoenqueue_state": {},
            "by_target_agent": {},
            "by_rollout_guard_state": {},
            "by_shadowed_rollout_guard_state": {},
            "by_task_outcome_state": {},
            "by_verification_state": {},
        },
        "top_goal_signatures": [],
        # C2: Nutzerwirkungs-Klassen — eigener Block, unabhängig von request_correlation.
        # user_visible_failures_total in request_correlation wird NICHT doppelt erhöht.
        "user_impact": {
            "response_never_delivered_total": 0,
            "silent_failure_total": 0,
            "user_visible_timeout_total": 0,
            "misroute_recovered_total": 0,
            "recent_impacts": [],
        },
    }

    recipe_duration_total = 0
    goal_counts: Dict[str, Dict[str, int]] = {}
    meta_diag = summary["meta_diagnostics"]
    request_correlation = summary["request_correlation"]
    meta_context_state = summary["meta_context_state"]
    specialist_context = summary["specialist_context"]
    communication_runtime = summary["communication_runtime"]
    challenge_runtime = summary["challenge_runtime"]
    improvement_runtime = summary["improvement_runtime"]
    user_impact = summary["user_impact"]
    recent_requests: List[Dict[str, Any]] = []
    recent_routes: List[Dict[str, Any]] = []
    recent_outcomes: List[Dict[str, Any]] = []
    recent_failures: List[Dict[str, Any]] = []
    recent_impacts: List[Dict[str, Any]] = []
    recent_misreads: List[Dict[str, Any]] = []

    def _bump(bucket: Dict[str, Any], key: Any, *, amount: int = 1, fallback: str = "unknown") -> None:
        normalized = _normalize_counter_key(key, fallback=fallback)
        bucket[normalized] = int(bucket.get(normalized) or 0) + int(amount)

    def _record_recent_failure(event_type: str, observed_at: str, payload: Dict[str, Any]) -> None:
        recent_failures.append(
            {
                "event_type": _normalize_counter_key(event_type),
                "observed_at": str(observed_at or ""),
                "request_id": str(payload.get("request_id") or ""),
                "session_id": str(payload.get("session_id") or ""),
                "task_id": str(payload.get("task_id") or ""),
                "agent": str(payload.get("agent") or ""),
                "source": str(payload.get("source") or ""),
                "incident_key": str(payload.get("incident_key") or ""),
                "error_class": str(payload.get("error_class") or ""),
                "error": str(payload.get("error") or "")[:240],
                "query_preview": str(payload.get("query_preview") or payload.get("description_preview") or "")[:180],
            }
        )

    def _record_recent_request(event_type: str, observed_at: str, payload: Dict[str, Any]) -> None:
        recent_requests.append(
            {
                "event_type": _normalize_counter_key(event_type),
                "observed_at": str(observed_at or ""),
                "request_id": str(payload.get("request_id") or ""),
                "session_id": str(payload.get("session_id") or ""),
                "source": str(payload.get("source") or ""),
                "query_preview": str(payload.get("query_preview") or "")[:180],
            }
        )

    def _record_recent_route(event_type: str, observed_at: str, payload: Dict[str, Any]) -> None:
        recent_routes.append(
            {
                "event_type": _normalize_counter_key(event_type),
                "observed_at": str(observed_at or ""),
                "request_id": str(payload.get("request_id") or ""),
                "session_id": str(payload.get("session_id") or ""),
                "task_id": str(payload.get("task_id") or ""),
                "source": str(payload.get("source") or ""),
                "agent": str(payload.get("agent") or ""),
                "route_source": str(payload.get("route_source") or ""),
                "decision_source": str(payload.get("decision_source") or ""),
                "incident_key": str(payload.get("incident_key") or ""),
                "query_preview": str(payload.get("query_preview") or payload.get("description_preview") or "")[:180],
            }
        )

    def _record_recent_outcome(event_type: str, observed_at: str, payload: Dict[str, Any]) -> None:
        recent_outcomes.append(
            {
                "event_type": _normalize_counter_key(event_type),
                "observed_at": str(observed_at or ""),
                "request_id": str(payload.get("request_id") or ""),
                "session_id": str(payload.get("session_id") or ""),
                "task_id": str(payload.get("task_id") or ""),
                "source": str(payload.get("source") or ""),
                "agent": str(payload.get("agent") or ""),
                "error_class": str(payload.get("error_class") or ""),
                "incident_key": str(payload.get("incident_key") or ""),
                "query_preview": str(payload.get("query_preview") or payload.get("description_preview") or "")[:180],
            }
        )

    def _is_improvement_runtime_payload(event_type: str, payload: Dict[str, Any]) -> bool:
        if event_type == "improvement_task_autonomy_event":
            return True
        source = _normalize_counter_key(payload.get("source"), fallback="")
        if source == "improvement_task_bridge":
            return True
        task_outcome_state = _normalize_counter_key(payload.get("task_outcome_state"), fallback="")
        if task_outcome_state in {
            "verified",
            "ended_unverified",
            "blocked",
            "verification_failed",
            "rolled_back",
        }:
            return True
        verification_state = _normalize_counter_key(payload.get("verification_state"), fallback="")
        return verification_state in {"verified", "not_verified", "blocked", "error", "rolled_back"}

    for raw_event in events:
        event = dict(raw_event or {})
        event_type = _normalize_counter_key(event.get("event_type"))
        observed_at = str(event.get("observed_at") or "")
        payload = dict(event.get("payload") or {})
        summary["total_events"] += 1
        summary["event_counts"][event_type] = int(summary["event_counts"].get(event_type) or 0) + 1

        if event_type == "meta_recipe_outcome":
            recipe_summary = summary["recipe_outcomes"]
            recipe_summary["total"] += 1
            success = bool(payload.get("success"))
            recipe_summary["success_total" if success else "failure_total"] += 1

            planner_state = _normalize_counter_key(payload.get("planner_resolution_state"))
            if planner_state == "adopted":
                recipe_summary["planner_adopted_total"] += 1
            else:
                recipe_summary["planner_fallback_total"] += 1

            runtime_gaps = [
                _normalize_counter_key(item)
                for item in list(payload.get("runtime_gap_insertions") or [])
                if str(item or "").strip()
            ]
            if runtime_gaps:
                recipe_summary["runtime_gap_outcomes_total"] += 1

            duration_ms = max(0, int(payload.get("duration_ms") or 0))
            recipe_duration_total += duration_ms

            recipe_id = _normalize_counter_key(payload.get("recipe_id"))
            recipe_bucket = recipe_summary["by_recipe"].setdefault(
                recipe_id,
                {"total": 0, "success_total": 0, "failure_total": 0},
            )
            recipe_bucket["total"] += 1
            recipe_bucket["success_total" if success else "failure_total"] += 1

            goal_signature = str(payload.get("goal_signature") or "").strip()
            if goal_signature:
                goal_bucket = goal_counts.setdefault(
                    goal_signature,
                    {"total": 0, "success_total": 0, "failure_total": 0},
                )
                goal_bucket["total"] += 1
                goal_bucket["success_total" if success else "failure_total"] += 1

        elif event_type == "dispatcher_meta_fallback":
            meta_diag["dispatcher_meta_fallback_total"] += 1
            reason = _normalize_counter_key(payload.get("reason"))
            meta_diag["dispatcher_meta_fallback_by_reason"][reason] = (
                int(meta_diag["dispatcher_meta_fallback_by_reason"].get(reason) or 0) + 1
            )

        elif event_type == "meta_specialist_delegation":
            meta_diag["specialist_delegations_total"] += 1
            agent = _normalize_counter_key(payload.get("agent"))
            meta_diag["specialist_delegation_by_agent"][agent] = (
                int(meta_diag["specialist_delegation_by_agent"].get(agent) or 0) + 1
            )
            if str(payload.get("status") or "").strip().lower() == "error":
                meta_diag["specialist_delegation_errors_total"] += 1

        elif event_type == "meta_direct_tool_call":
            meta_diag["direct_tool_calls_total"] += 1
            method = _normalize_counter_key(payload.get("method"))
            meta_diag["direct_tool_by_method"][method] = int(meta_diag["direct_tool_by_method"].get(method) or 0) + 1
            if str(payload.get("status") or "").strip().lower() == "error" or bool(payload.get("has_error")):
                meta_diag["direct_tool_errors_total"] += 1

        elif event_type == "lead_diagnosis_selected":
            meta_diag["lead_diagnosis_selected_total"] += 1

        elif event_type == "diagnosis_conflict_detected":
            meta_diag["diagnosis_conflicts_total"] += 1

        elif event_type == "developer_task_compiled":
            meta_diag["developer_tasks_compiled_total"] += 1

        elif event_type == "unverified_claim_suppressed":
            meta_diag["unverified_claims_suppressed_total"] += max(
                1,
                int(payload.get("suppressed_claims_count") or 0),
            )

        elif event_type == "primary_fix_task_emitted":
            meta_diag["primary_fix_tasks_total"] += 1

        elif event_type == "followup_task_deferred":
            meta_diag["followup_tasks_deferred_total"] += max(1, int(payload.get("followup_tasks_count") or 0))

        elif event_type == "root_cause_gate_blocked":
            meta_diag["root_cause_gate_blocked_total"] += 1

        elif event_type == "task_mix_suppressed":
            meta_diag["task_mix_suppressed_total"] += max(1, int(payload.get("task_mix_suppressed_count") or 0))

        elif event_type == "runtime_goal_gap_inserted":
            runtime_summary = summary["runtime_gaps"]
            runtime_summary["total_insertions"] += 1
            reason = _normalize_counter_key(payload.get("adaptive_reason"))
            runtime_summary["by_reason"][reason] = int(runtime_summary["by_reason"].get(reason) or 0) + 1

        elif event_type == "self_hardening_runtime_event":
            hardening = summary["self_hardening"]
            hardening["total"] += 1
            stage = _normalize_counter_key(payload.get("stage"))
            status = _normalize_counter_key(payload.get("status"))
            hardening["by_stage"][stage] = int(hardening["by_stage"].get(stage) or 0) + 1
            hardening["by_status"][status] = int(hardening["by_status"].get(status) or 0) + 1
            if stage == "self_modify_started":
                hardening["self_modify_started_total"] += 1
            if stage == "self_modify_finished":
                hardening["self_modify_finished_total"] += 1
                if status == "success":
                    hardening["self_modify_success_total"] += 1
                elif status == "blocked":
                    hardening["self_modify_blocked_total"] += 1
                elif status == "rolled_back":
                    hardening["self_modify_rolled_back_total"] += 1
                elif status == "error":
                    hardening["self_modify_error_total"] += 1

        elif event_type == "chat_request_received":
            request_correlation["chat_requests_total"] += 1
            _bump(request_correlation["by_source"], payload.get("source"))
            _record_recent_request(event_type, observed_at, payload)

        elif event_type == "chat_request_completed":
            request_correlation["chat_completed_total"] += 1
            _bump(request_correlation["by_source"], payload.get("source"))
            _bump(request_correlation["by_agent"], payload.get("agent"))
            _record_recent_outcome(event_type, observed_at, payload)

        elif event_type == "chat_request_failed":
            request_correlation["chat_failed_total"] += 1
            request_correlation["user_visible_failures_total"] += 1
            _bump(request_correlation["by_source"], payload.get("source"))
            _bump(request_correlation["by_agent"], payload.get("agent"), fallback="none")
            _bump(
                request_correlation["by_error_class"],
                payload.get("error_class") or "chat_request_failed",
            )
            _record_recent_outcome(event_type, observed_at, payload)
            _record_recent_failure(event_type, observed_at, payload)

        elif event_type == "dispatcher_route_selected":
            request_correlation["dispatcher_routes_total"] += 1
            _bump(request_correlation["by_source"], payload.get("source") or "dispatcher")
            _bump(request_correlation["by_agent"], payload.get("agent"))
            _record_recent_route(event_type, observed_at, payload)

        elif event_type == "request_route_selected":
            request_correlation["request_routes_total"] += 1
            _bump(request_correlation["by_source"], payload.get("source"))
            _bump(request_correlation["by_agent"], payload.get("agent"))
            _record_recent_route(event_type, observed_at, payload)

        elif event_type == "task_route_selected":
            request_correlation["task_routes_total"] += 1
            _bump(request_correlation["by_source"], payload.get("source"))
            _bump(request_correlation["by_agent"], payload.get("agent"))
            _record_recent_route(event_type, observed_at, payload)

        elif event_type == "task_execution_started":
            request_correlation["task_started_total"] += 1
            _bump(request_correlation["by_source"], payload.get("source"))
            if _is_improvement_runtime_payload(event_type, payload):
                improvement_runtime["execution_started_total"] += 1

        elif event_type == "task_execution_completed":
            request_correlation["task_completed_total"] += 1
            _bump(request_correlation["by_source"], payload.get("source"))
            _bump(request_correlation["by_agent"], payload.get("agent"))
            _record_recent_outcome(event_type, observed_at, payload)
            if _is_improvement_runtime_payload(event_type, payload):
                improvement_runtime["execution_terminal_total"] += 1
                task_outcome_state = _normalize_counter_key(payload.get("task_outcome_state"))
                verification_state = _normalize_counter_key(payload.get("verification_state"))
                _bump(improvement_runtime["by_task_outcome_state"], task_outcome_state)
                _bump(improvement_runtime["by_verification_state"], verification_state)
                if task_outcome_state == "verified":
                    improvement_runtime["execution_verified_total"] += 1
                elif task_outcome_state == "ended_unverified":
                    improvement_runtime["execution_ended_unverified_total"] += 1

        elif event_type == "task_execution_failed":
            request_correlation["task_failed_total"] += 1
            _bump(request_correlation["by_source"], payload.get("source"))
            _bump(request_correlation["by_agent"], payload.get("agent"), fallback="none")
            _bump(
                request_correlation["by_error_class"],
                payload.get("error_class") or "task_execution_failed",
            )
            _record_recent_outcome(event_type, observed_at, payload)
            _record_recent_failure(event_type, observed_at, payload)
            if _is_improvement_runtime_payload(event_type, payload):
                improvement_runtime["execution_terminal_total"] += 1
                task_outcome_state = _normalize_counter_key(payload.get("task_outcome_state"))
                verification_state = _normalize_counter_key(payload.get("verification_state"))
                _bump(improvement_runtime["by_task_outcome_state"], task_outcome_state)
                _bump(improvement_runtime["by_verification_state"], verification_state)
                if task_outcome_state == "blocked":
                    improvement_runtime["execution_blocked_total"] += 1
                elif task_outcome_state == "verification_failed":
                    improvement_runtime["execution_verification_failed_total"] += 1
                elif task_outcome_state == "rolled_back":
                    improvement_runtime["execution_rolled_back_total"] += 1
                else:
                    improvement_runtime["execution_failed_other_total"] += 1

        elif event_type == "meta_turn_type_selected":
            meta_context_state["turn_type_selected_total"] += 1
            _bump(meta_context_state["by_turn_type"], payload.get("dominant_turn_type"))

        elif event_type == "meta_response_mode_selected":
            meta_context_state["response_mode_selected_total"] += 1
            _bump(meta_context_state["by_response_mode"], payload.get("response_mode"))

        elif event_type == "meta_policy_mode_selected":
            meta_context_state["policy_mode_selected_total"] += 1
            _bump(meta_context_state["by_response_mode"], payload.get("response_mode"))
            _bump(meta_context_state["by_policy_reason"], payload.get("policy_reason"))

        elif event_type == "meta_policy_override_applied":
            meta_context_state["policy_override_total"] += 1
            _bump(meta_context_state["by_policy_reason"], payload.get("policy_reason"))

        elif event_type == "meta_policy_self_model_bound_applied":
            meta_context_state["self_model_bound_total"] += 1
            _bump(meta_context_state["by_policy_reason"], payload.get("policy_reason"))

        elif event_type == "context_rehydration_bundle_built":
            meta_context_state["context_bundle_built_total"] += 1

        elif event_type == "context_slot_selected":
            meta_context_state["context_slot_selected_total"] += 1
            _bump(meta_context_state["by_slot"], payload.get("slot"))

        elif event_type == "context_slot_suppressed":
            meta_context_state["context_slot_suppressed_total"] += 1
            _bump(meta_context_state["by_suppression_reason"], payload.get("reason"))

        elif event_type == "context_misread_suspected":
            meta_context_state["context_misread_suspected_total"] += 1
            for reason in list(payload.get("risk_reasons") or []):
                _bump(meta_context_state["by_misread_reason"], reason)
            recent_misreads.append(
                {
                    "observed_at": str(observed_at or ""),
                    "request_id": str(payload.get("request_id") or ""),
                    "session_id": str(payload.get("session_id") or ""),
                    "dominant_turn_type": str(payload.get("dominant_turn_type") or ""),
                    "response_mode": str(payload.get("response_mode") or ""),
                    "risk_reasons": [
                        _normalize_counter_key(item)
                        for item in list(payload.get("risk_reasons") or [])
                        if str(item or "").strip()
                    ][:6],
                }
            )

        elif event_type == "topic_shift_detected":
            meta_context_state["topic_shift_total"] += 1

        elif event_type == "conversation_state_updated":
            meta_context_state["conversation_state_updated_total"] += 1

        elif event_type == "conversation_state_decayed":
            meta_context_state["conversation_state_decayed_total"] += 1
            for reason in list(payload.get("reasons") or []):
                _bump(meta_context_state["by_decay_reason"], reason)

        elif event_type == "historical_topic_attached":
            meta_context_state["historical_topic_attached_total"] += 1
            _bump(meta_context_state["by_historical_time_label"], payload.get("time_label"))

        elif event_type == "preference_captured":
            meta_context_state["preference_captured_total"] += 1
            _bump(meta_context_state["by_preference_scope"], payload.get("scope"))

        elif event_type == "preference_applied":
            meta_context_state["preference_applied_total"] += 1

        elif event_type == "preference_scope_selected":
            meta_context_state["preference_scope_selected_total"] += 1
            _bump(meta_context_state["by_preference_scope"], payload.get("scope"))
            _bump(meta_context_state["by_preference_family"], payload.get("family"))

        elif event_type == "preference_conflict_resolved":
            meta_context_state["preference_conflict_resolved_total"] += 1
            _bump(meta_context_state["by_preference_family"], payload.get("family"))

        elif event_type == "specialist_strategy_selected":
            specialist_context["strategy_selected_total"] += 1
            _bump(specialist_context["by_agent"], payload.get("agent"))
            _bump(specialist_context["by_strategy_mode"], payload.get("strategy_mode"))
            _bump(specialist_context["by_response_mode"], payload.get("response_mode"))

        elif event_type == "specialist_signal_emitted":
            specialist_context["specialist_signal_total"] += 1
            _bump(specialist_context["by_agent"], payload.get("agent"))
            _bump(specialist_context["by_signal"], payload.get("signal"))
            _bump(specialist_context["by_signal_source"], payload.get("signal_source"))
            signal_name = _normalize_counter_key(payload.get("signal"))
            if signal_name == "needs_meta_reframe":
                specialist_context["needs_meta_reframe_total"] += 1
            elif signal_name == "context_mismatch":
                specialist_context["context_mismatch_total"] += 1

        elif event_type == "communication_task_started":
            communication_runtime["tasks_started_total"] += 1
            _bump(communication_runtime["by_source"], payload.get("source"))
            _bump(communication_runtime["by_backend"], payload.get("backend"), fallback="unknown")
            _bump(communication_runtime["by_agent"], payload.get("agent"))
            _bump(communication_runtime["by_channel"], payload.get("channel"))

        elif event_type == "communication_task_completed":
            communication_runtime["tasks_completed_total"] += 1
            _bump(communication_runtime["by_source"], payload.get("source"))
            _bump(communication_runtime["by_backend"], payload.get("backend"), fallback="unknown")
            _bump(communication_runtime["by_agent"], payload.get("agent"))
            _bump(communication_runtime["by_channel"], payload.get("channel"))

        elif event_type == "communication_task_partial":
            communication_runtime["tasks_partial_total"] += 1
            _bump(communication_runtime["by_source"], payload.get("source"))
            _bump(communication_runtime["by_backend"], payload.get("backend"), fallback="unknown")
            _bump(communication_runtime["by_agent"], payload.get("agent"))
            _bump(communication_runtime["by_channel"], payload.get("channel"))

        elif event_type == "communication_task_failed":
            communication_runtime["tasks_failed_total"] += 1
            _bump(communication_runtime["by_source"], payload.get("source"))
            _bump(communication_runtime["by_backend"], payload.get("backend"), fallback="unknown")
            _bump(communication_runtime["by_agent"], payload.get("agent"))
            _bump(communication_runtime["by_channel"], payload.get("channel"))

        elif event_type == "send_email_succeeded":
            communication_runtime["email_send_success_total"] += 1
            _bump(communication_runtime["by_source"], payload.get("source"))
            _bump(communication_runtime["by_backend"], payload.get("backend"), fallback="unknown")
            _bump(communication_runtime["by_agent"], payload.get("agent"))
            _bump(communication_runtime["by_channel"], payload.get("channel"))

        elif event_type == "send_email_failed":
            communication_runtime["email_send_failed_total"] += 1
            _bump(communication_runtime["by_source"], payload.get("source"))
            _bump(communication_runtime["by_backend"], payload.get("backend"), fallback="unknown")
            _bump(communication_runtime["by_agent"], payload.get("agent"))
            _bump(communication_runtime["by_channel"], payload.get("channel"))

        elif event_type == "challenge_required":
            challenge_runtime["challenge_required_total"] += 1
            _bump(challenge_runtime["by_service"], payload.get("service"))
            _bump(challenge_runtime["by_challenge_type"], payload.get("challenge_type"))

        elif event_type == "challenge_resume":
            challenge_runtime["challenge_resume_total"] += 1
            _bump(challenge_runtime["by_service"], payload.get("service"))
            _bump(challenge_runtime["by_challenge_type"], payload.get("challenge_type"))
            _bump(challenge_runtime["by_reply_kind"], payload.get("reply_kind"))

        elif event_type == "challenge_resolved":
            challenge_runtime["challenge_resolved_total"] += 1
            _bump(challenge_runtime["by_service"], payload.get("service"))
            _bump(challenge_runtime["by_challenge_type"], payload.get("challenge_type"))
            _bump(challenge_runtime["by_reply_kind"], payload.get("reply_kind"))

        elif event_type == "challenge_reblocked":
            challenge_runtime["challenge_reblocked_total"] += 1
            _bump(challenge_runtime["by_service"], payload.get("service"))
            _bump(challenge_runtime["by_challenge_type"], payload.get("challenge_type"))
            _bump(challenge_runtime["by_reply_kind"], payload.get("reply_kind"))

        elif event_type == "improvement_task_autonomy_event":
            improvement_runtime["autonomy_decisions_total"] += 1
            autoenqueue_state = _normalize_counter_key(payload.get("autoenqueue_state"))
            _bump(improvement_runtime["by_autoenqueue_state"], autoenqueue_state)
            _bump(improvement_runtime["by_target_agent"], payload.get("target_agent"))
            _bump(improvement_runtime["by_rollout_guard_state"], payload.get("rollout_guard_state"))
            for state in list(payload.get("shadowed_guard_states") or [])[:4]:
                _bump(improvement_runtime["by_shadowed_rollout_guard_state"], state)
            if autoenqueue_state == "autoenqueue_ready":
                improvement_runtime["autoenqueue_ready_total"] += 1
            elif autoenqueue_state == "enqueue_created":
                improvement_runtime["enqueue_created_total"] += 1
            elif autoenqueue_state == "enqueue_deduped":
                improvement_runtime["enqueue_deduped_total"] += 1
            else:
                improvement_runtime["enqueue_blocked_total"] += 1
                if autoenqueue_state == "enqueue_cooldown_active":
                    improvement_runtime["enqueue_cooldown_active_total"] += 1

        elif event_type in _USER_IMPACT_EVENT_TYPES:
            # C2: Nutzerwirkungs-Klassen. Eigener Block — user_visible_failures_total
            # in request_correlation wird nicht doppelt erhöht.
            counter_key = f"{event_type}_total"
            user_impact[counter_key] = int(user_impact.get(counter_key) or 0) + 1
            recent_impacts.append({
                "event_type": event_type,
                "observed_at": str(observed_at or ""),
                "request_id": str(payload.get("request_id") or ""),
                "session_id": str(payload.get("session_id") or ""),
                "agent": str(payload.get("agent") or ""),
                "source": str(payload.get("source") or ""),
                "query_preview": str(payload.get("query_preview") or "")[:180],
            })

    recipe_total = int(summary["recipe_outcomes"]["total"] or 0)
    if recipe_total > 0:
        summary["recipe_outcomes"]["average_duration_ms"] = int(recipe_duration_total / recipe_total)

    top_goal_signatures = sorted(
        (
            {
                "goal_signature": goal_signature,
                "total": counts["total"],
                "success_total": counts["success_total"],
                "failure_total": counts["failure_total"],
            }
            for goal_signature, counts in goal_counts.items()
        ),
        key=lambda item: (-int(item["total"]), item["goal_signature"]),
    )
    summary["top_goal_signatures"] = top_goal_signatures[:8]
    summary["request_correlation"]["recent_requests"] = sorted(
        recent_requests,
        key=lambda item: str(item.get("observed_at") or ""),
        reverse=True,
    )[:_RECENT_CORRELATION_LIMIT]
    summary["request_correlation"]["recent_routes"] = sorted(
        recent_routes,
        key=lambda item: str(item.get("observed_at") or ""),
        reverse=True,
    )[:_RECENT_CORRELATION_LIMIT]
    summary["request_correlation"]["recent_outcomes"] = sorted(
        recent_outcomes,
        key=lambda item: str(item.get("observed_at") or ""),
        reverse=True,
    )[:_RECENT_CORRELATION_LIMIT]
    summary["request_correlation"]["recent_failures"] = sorted(
        recent_failures,
        key=lambda item: str(item.get("observed_at") or ""),
        reverse=True,
    )[:_RECENT_CORRELATION_LIMIT]
    summary["user_impact"]["recent_impacts"] = sorted(
        recent_impacts,
        key=lambda item: str(item.get("observed_at") or ""),
        reverse=True,
    )[:_RECENT_CORRELATION_LIMIT]
    bundle_total = int(meta_context_state.get("context_bundle_built_total") or 0)
    if bundle_total > 0:
        suspicious_total = int(meta_context_state.get("context_misread_suspected_total") or 0)
        meta_context_state["healthy_bundle_rate"] = round(max(0.0, 1.0 - (suspicious_total / bundle_total)), 3)
        meta_context_state["misread_rate"] = round(min(1.0, suspicious_total / bundle_total), 3)
    turn_total = int(meta_context_state.get("turn_type_selected_total") or 0)
    if turn_total > 0:
        meta_context_state["state_update_coverage"] = round(
            min(1.0, int(meta_context_state.get("conversation_state_updated_total") or 0) / turn_total),
            3,
        )
    captured_total = int(meta_context_state.get("preference_captured_total") or 0)
    if captured_total > 0:
        meta_context_state["preference_roundtrip_rate"] = round(
            min(1.0, int(meta_context_state.get("preference_applied_total") or 0) / captured_total),
            3,
        )
    policy_total = int(meta_context_state.get("policy_mode_selected_total") or 0)
    if policy_total > 0:
        meta_context_state["policy_override_rate"] = round(
            min(1.0, int(meta_context_state.get("policy_override_total") or 0) / policy_total),
            3,
        )
    strategy_total = int(specialist_context.get("strategy_selected_total") or 0)
    signal_total = int(specialist_context.get("specialist_signal_total") or 0)
    if signal_total > 0:
        specialist_context["agent_signal_rate"] = round(
            min(1.0, int(dict(specialist_context.get("by_signal_source") or {}).get("agent") or 0) / signal_total),
            3,
        )
        specialist_context["signal_reframe_rate"] = round(
            min(1.0, int(specialist_context.get("needs_meta_reframe_total") or 0) / signal_total),
            3,
        )
    challenge_required_total = int(challenge_runtime.get("challenge_required_total") or 0)
    challenge_resume_total = int(challenge_runtime.get("challenge_resume_total") or 0)
    if challenge_required_total > 0:
        challenge_runtime["resolution_rate"] = round(
            min(1.0, int(challenge_runtime.get("challenge_resolved_total") or 0) / challenge_required_total),
            3,
        )
    if challenge_resume_total > 0:
        challenge_runtime["reblock_rate"] = round(
            min(1.0, int(challenge_runtime.get("challenge_reblocked_total") or 0) / challenge_resume_total),
            3,
        )
    autonomy_decisions_total = int(improvement_runtime.get("autonomy_decisions_total") or 0)
    if autonomy_decisions_total > 0:
        improvement_runtime["enqueue_creation_rate"] = round(
            min(1.0, int(improvement_runtime.get("enqueue_created_total") or 0) / autonomy_decisions_total),
            3,
        )
    execution_terminal_total = int(improvement_runtime.get("execution_terminal_total") or 0)
    if execution_terminal_total > 0:
        verified_total = int(improvement_runtime.get("execution_verified_total") or 0)
        improvement_runtime["verified_rate"] = round(min(1.0, verified_total / execution_terminal_total), 3)
        improvement_runtime["not_verified_rate"] = round(
            min(1.0, max(0, execution_terminal_total - verified_total) / execution_terminal_total),
            3,
        )
    summary["meta_context_state"]["recent_misreads"] = sorted(
        recent_misreads,
        key=lambda item: str(item.get("observed_at") or ""),
        reverse=True,
    )[:_RECENT_CORRELATION_LIMIT]
    return summary


def render_autonomy_observation_markdown(summary: Dict[str, Any]) -> str:
    session = dict(summary.get("session") or {})
    window = dict(summary.get("window") or {})
    recipe = dict(summary.get("recipe_outcomes") or {})
    runtime = dict(summary.get("runtime_gaps") or {})
    hardening = dict(summary.get("self_hardening") or {})
    meta_diag = dict(summary.get("meta_diagnostics") or {})
    meta_context_state = dict(summary.get("meta_context_state") or {})
    specialist_context = dict(summary.get("specialist_context") or {})
    communication_runtime = dict(summary.get("communication_runtime") or {})
    challenge_runtime = dict(summary.get("challenge_runtime") or {})
    improvement_runtime = dict(summary.get("improvement_runtime") or {})
    request_correlation = dict(summary.get("request_correlation") or {})
    event_counts = dict(summary.get("event_counts") or {})

    lines = [
        "# Timus Autonomy Observation",
        "",
        f"- Label: `{session.get('label') or ''}`",
        f"- Start: `{window.get('since') or session.get('started_at') or ''}`",
        f"- Ende: `{window.get('until') or session.get('ends_at') or ''}`",
        f"- Aktiv: `{bool(session.get('active'))}`",
        f"- Events gesamt: `{int(summary.get('total_events') or 0)}`",
        "",
        "## Event-Typen",
    ]
    for key, value in sorted(event_counts.items()):
        lines.append(f"- `{key}`: `{int(value or 0)}`")

    lines.extend(
        [
            "",
            "## Meta-Diagnostik",
            f"- Dispatcher -> Meta Fallbacks: `{int(meta_diag.get('dispatcher_meta_fallback_total') or 0)}`",
            f"- Specialist-Delegationen: `{int(meta_diag.get('specialist_delegations_total') or 0)}`",
            f"- Specialist-Delegationsfehler: `{int(meta_diag.get('specialist_delegation_errors_total') or 0)}`",
            f"- Direkte Meta-Tool-Calls: `{int(meta_diag.get('direct_tool_calls_total') or 0)}`",
            f"- Direkte Meta-Tool-Fehler: `{int(meta_diag.get('direct_tool_errors_total') or 0)}`",
            f"- Lead-Diagnosen gewaehlt: `{int(meta_diag.get('lead_diagnosis_selected_total') or 0)}`",
            f"- Diagnose-Konflikte erkannt: `{int(meta_diag.get('diagnosis_conflicts_total') or 0)}`",
            f"- Developer-Tasks kompiliert: `{int(meta_diag.get('developer_tasks_compiled_total') or 0)}`",
            f"- Unverifizierte Claims unterdrueckt: `{int(meta_diag.get('unverified_claims_suppressed_total') or 0)}`",
            f"- Primary-Fix-Tasks emittiert: `{int(meta_diag.get('primary_fix_tasks_total') or 0)}`",
            f"- Follow-up-Tasks deferiert: `{int(meta_diag.get('followup_tasks_deferred_total') or 0)}`",
            f"- Root-Cause-Gate blockiert: `{int(meta_diag.get('root_cause_gate_blocked_total') or 0)}`",
            f"- Task-Mix unterdrueckt: `{int(meta_diag.get('task_mix_suppressed_total') or 0)}`",
            "",
            "## D0 Meta Context State",
            f"- Turn-Typ-Entscheidungen: `{int(meta_context_state.get('turn_type_selected_total') or 0)}`",
            f"- Response-Mode-Entscheidungen: `{int(meta_context_state.get('response_mode_selected_total') or 0)}`",
            f"- Context-Bundles gebaut: `{int(meta_context_state.get('context_bundle_built_total') or 0)}`",
            f"- Verdacht auf Kontext-Fehlgriff: `{int(meta_context_state.get('context_misread_suspected_total') or 0)}`",
            f"- Healthy-Bundle-Rate: `{float(meta_context_state.get('healthy_bundle_rate') or 0.0):.3f}`",
            f"- Misread-Rate: `{float(meta_context_state.get('misread_rate') or 0.0):.3f}`",
            f"- State-Update-Coverage: `{float(meta_context_state.get('state_update_coverage') or 0.0):.3f}`",
            f"- Preference-Roundtrip-Rate: `{float(meta_context_state.get('preference_roundtrip_rate') or 0.0):.3f}`",
            f"- Policy-Override-Rate: `{float(meta_context_state.get('policy_override_rate') or 0.0):.3f}`",
            f"- Conversation-State-Decay: `{int(meta_context_state.get('conversation_state_decayed_total') or 0)}`",
            f"- Historical-Topic-Attachments: `{int(meta_context_state.get('historical_topic_attached_total') or 0)}`",
            f"- Preference-Captures: `{int(meta_context_state.get('preference_captured_total') or 0)}`",
            f"- Preference-Applies: `{int(meta_context_state.get('preference_applied_total') or 0)}`",
            "",
            "## D0.9 Specialist Context",
            f"- Strategien gewaehlt: `{int(specialist_context.get('strategy_selected_total') or 0)}`",
            f"- Specialist-Signale: `{int(specialist_context.get('specialist_signal_total') or 0)}`",
            f"- `needs_meta_reframe`: `{int(specialist_context.get('needs_meta_reframe_total') or 0)}`",
            f"- `context_mismatch`: `{int(specialist_context.get('context_mismatch_total') or 0)}`",
            f"- Agent-Signal-Rate: `{float(specialist_context.get('agent_signal_rate') or 0.0):.3f}`",
            f"- Reframe-Rate: `{float(specialist_context.get('signal_reframe_rate') or 0.0):.3f}`",
            "",
            "## Communication Runtime",
            f"- Communication-Tasks gestartet: `{int(communication_runtime.get('tasks_started_total') or 0)}`",
            f"- Communication-Tasks abgeschlossen: `{int(communication_runtime.get('tasks_completed_total') or 0)}`",
            f"- Communication-Tasks partiell: `{int(communication_runtime.get('tasks_partial_total') or 0)}`",
            f"- Communication-Tasks fehlgeschlagen: `{int(communication_runtime.get('tasks_failed_total') or 0)}`",
            f"- E-Mail-Versand Erfolg: `{int(communication_runtime.get('email_send_success_total') or 0)}`",
            f"- E-Mail-Versand Fehler: `{int(communication_runtime.get('email_send_failed_total') or 0)}`",
            "",
            "## Challenge Runtime",
            f"- Challenge erforderlich: `{int(challenge_runtime.get('challenge_required_total') or 0)}`",
            f"- Challenge-Resume erkannt: `{int(challenge_runtime.get('challenge_resume_total') or 0)}`",
            f"- Challenge aufgeloest: `{int(challenge_runtime.get('challenge_resolved_total') or 0)}`",
            f"- Challenge erneut blockiert: `{int(challenge_runtime.get('challenge_reblocked_total') or 0)}`",
            f"- Challenge-Resolution-Rate: `{float(challenge_runtime.get('resolution_rate') or 0.0):.3f}`",
            f"- Challenge-Reblock-Rate: `{float(challenge_runtime.get('reblock_rate') or 0.0):.3f}`",
            "",
            "## Improvement Runtime",
            f"- Autonomy-Entscheidungen: `{int(improvement_runtime.get('autonomy_decisions_total') or 0)}`",
            f"- Auto-Enqueue bereit: `{int(improvement_runtime.get('autoenqueue_ready_total') or 0)}`",
            f"- Enqueue erstellt: `{int(improvement_runtime.get('enqueue_created_total') or 0)}`",
            f"- Enqueue dedupliziert: `{int(improvement_runtime.get('enqueue_deduped_total') or 0)}`",
            f"- Enqueue Cooldown aktiv: `{int(improvement_runtime.get('enqueue_cooldown_active_total') or 0)}`",
            f"- Enqueue blockiert: `{int(improvement_runtime.get('enqueue_blocked_total') or 0)}`",
            f"- Execution gestartet: `{int(improvement_runtime.get('execution_started_total') or 0)}`",
            f"- Terminale Execution-Outcomes: `{int(improvement_runtime.get('execution_terminal_total') or 0)}`",
            f"- Verifiziert: `{int(improvement_runtime.get('execution_verified_total') or 0)}`",
            f"- Beendet unverifiziert: `{int(improvement_runtime.get('execution_ended_unverified_total') or 0)}`",
            f"- Blockiert: `{int(improvement_runtime.get('execution_blocked_total') or 0)}`",
            f"- Verifikation fehlgeschlagen: `{int(improvement_runtime.get('execution_verification_failed_total') or 0)}`",
            f"- Zurueckgerollt: `{int(improvement_runtime.get('execution_rolled_back_total') or 0)}`",
            f"- Sonstige Execution-Fehler: `{int(improvement_runtime.get('execution_failed_other_total') or 0)}`",
            f"- Enqueue-Creation-Rate: `{float(improvement_runtime.get('enqueue_creation_rate') or 0.0):.3f}`",
            f"- Verified-Rate: `{float(improvement_runtime.get('verified_rate') or 0.0):.3f}`",
            f"- Nicht-verifiziert-Rate: `{float(improvement_runtime.get('not_verified_rate') or 0.0):.3f}`",
            "",
            "## Recipe Outcomes",
            f"- Gesamt: `{int(recipe.get('total') or 0)}`",
            f"- Erfolg: `{int(recipe.get('success_total') or 0)}`",
            f"- Fehler: `{int(recipe.get('failure_total') or 0)}`",
            f"- Planner adoptiert: `{int(recipe.get('planner_adopted_total') or 0)}`",
            f"- Planner Fallback: `{int(recipe.get('planner_fallback_total') or 0)}`",
            f"- Outcomes mit Runtime-Gap: `{int(recipe.get('runtime_gap_outcomes_total') or 0)}`",
            f"- Durchschnittliche Laufzeit (ms): `{int(recipe.get('average_duration_ms') or 0)}`",
            "",
            "## Runtime Gaps",
            f"- Insertions gesamt: `{int(runtime.get('total_insertions') or 0)}`",
        ]
    )
    for key, value in sorted(dict(runtime.get("by_reason") or {}).items()):
        lines.append(f"- `{key}`: `{int(value or 0)}`")
    for key, value in sorted(dict(meta_diag.get("dispatcher_meta_fallback_by_reason") or {}).items()):
        lines.append(f"- Dispatcher-Fallback `{key}`: `{int(value or 0)}`")
    for key, value in sorted(dict(meta_diag.get("specialist_delegation_by_agent") or {}).items()):
        lines.append(f"- Specialist `{key}`: `{int(value or 0)}`")
    for key, value in sorted(dict(meta_diag.get("direct_tool_by_method") or {}).items()):
        lines.append(f"- Meta-Tool `{key}`: `{int(value or 0)}`")
    for key, value in sorted(dict(meta_context_state.get("by_decay_reason") or {}).items()):
        lines.append(f"- Decay `{key}`: `{int(value or 0)}`")
    for key, value in sorted(dict(meta_context_state.get("by_historical_time_label") or {}).items()):
        lines.append(f"- Historical `{key}`: `{int(value or 0)}`")
    for key, value in sorted(dict(specialist_context.get("by_strategy_mode") or {}).items()):
        lines.append(f"- Specialist-Strategie `{key}`: `{int(value or 0)}`")
    for key, value in sorted(dict(specialist_context.get("by_signal") or {}).items()):
        lines.append(f"- Specialist-Signal `{key}`: `{int(value or 0)}`")
    for key, value in sorted(dict(specialist_context.get("by_signal_source") or {}).items()):
        lines.append(f"- Specialist-Signalquelle `{key}`: `{int(value or 0)}`")
    for key, value in sorted(dict(communication_runtime.get("by_backend") or {}).items()):
        lines.append(f"- Mail-Backend `{key}`: `{int(value or 0)}`")
    for key, value in sorted(dict(communication_runtime.get("by_channel") or {}).items()):
        lines.append(f"- Communication-Kanal `{key}`: `{int(value or 0)}`")
    for key, value in sorted(dict(challenge_runtime.get("by_challenge_type") or {}).items()):
        lines.append(f"- Challenge-Typ `{key}`: `{int(value or 0)}`")
    for key, value in sorted(dict(challenge_runtime.get("by_reply_kind") or {}).items()):
        lines.append(f"- Challenge-Reply `{key}`: `{int(value or 0)}`")
    for key, value in sorted(dict(improvement_runtime.get("by_autoenqueue_state") or {}).items()):
        lines.append(f"- Improvement-Autoenqueue `{key}`: `{int(value or 0)}`")
    for key, value in sorted(dict(improvement_runtime.get("by_rollout_guard_state") or {}).items()):
        lines.append(f"- Improvement-Rollout-Guard `{key}`: `{int(value or 0)}`")
    for key, value in sorted(dict(improvement_runtime.get("by_shadowed_rollout_guard_state") or {}).items()):
        lines.append(f"- Shadowed Guard `{key}`: `{int(value or 0)}`")
    for key, value in sorted(dict(improvement_runtime.get("by_task_outcome_state") or {}).items()):
        lines.append(f"- Improvement-Outcome `{key}`: `{int(value or 0)}`")
    for key, value in sorted(dict(improvement_runtime.get("by_verification_state") or {}).items()):
        lines.append(f"- Improvement-Verification `{key}`: `{int(value or 0)}`")

    lines.extend(
        [
            "",
            "## Request-Korrelation",
            f"- Chat-Requests: `{int(request_correlation.get('chat_requests_total') or 0)}`",
            f"- Chat abgeschlossen: `{int(request_correlation.get('chat_completed_total') or 0)}`",
            f"- Chat fehlgeschlagen: `{int(request_correlation.get('chat_failed_total') or 0)}`",
            f"- Dispatcher-Routen: `{int(request_correlation.get('dispatcher_routes_total') or 0)}`",
            f"- Request-Routen: `{int(request_correlation.get('request_routes_total') or 0)}`",
            f"- Task-Routen: `{int(request_correlation.get('task_routes_total') or 0)}`",
            f"- Tasks gestartet: `{int(request_correlation.get('task_started_total') or 0)}`",
            f"- Tasks abgeschlossen: `{int(request_correlation.get('task_completed_total') or 0)}`",
            f"- Tasks fehlgeschlagen: `{int(request_correlation.get('task_failed_total') or 0)}`",
            f"- Nutzer-sichtbare Fehler: `{int(request_correlation.get('user_visible_failures_total') or 0)}`",
            "",
            "## Self-Hardening",
            f"- Events gesamt: `{int(hardening.get('total') or 0)}`",
            f"- Self-Modify gestartet: `{int(hardening.get('self_modify_started_total') or 0)}`",
            f"- Self-Modify beendet: `{int(hardening.get('self_modify_finished_total') or 0)}`",
            f"- Self-Modify Erfolg: `{int(hardening.get('self_modify_success_total') or 0)}`",
            f"- Self-Modify Blocked: `{int(hardening.get('self_modify_blocked_total') or 0)}`",
            f"- Self-Modify Rollback: `{int(hardening.get('self_modify_rolled_back_total') or 0)}`",
            f"- Self-Modify Error: `{int(hardening.get('self_modify_error_total') or 0)}`",
            "",
            "## Hauefige Zielsignaturen",
        ]
    )
    for item in list(summary.get("top_goal_signatures") or [])[:8]:
        lines.append(
            f"- `{item.get('goal_signature')}`: total `{int(item.get('total') or 0)}`, "
            f"success `{int(item.get('success_total') or 0)}`, failure `{int(item.get('failure_total') or 0)}`"
        )
    for key, value in sorted(dict(request_correlation.get("by_source") or {}).items()):
        lines.append(f"- Source `{key}`: `{int(value or 0)}`")
    for key, value in sorted(dict(request_correlation.get("by_agent") or {}).items()):
        lines.append(f"- Agent `{key}`: `{int(value or 0)}`")
    for key, value in sorted(dict(request_correlation.get("by_error_class") or {}).items()):
        lines.append(f"- Fehlerklasse `{key}`: `{int(value or 0)}`")
    if list(request_correlation.get("recent_failures") or []):
        lines.append("")
        lines.append("## Letzte korrelierte Fehler")
        for item in list(request_correlation.get("recent_failures") or [])[:6]:
            lines.append(
                "- `{event}` | `{source}` | agent `{agent}` | req `{request_id}` | task `{task_id}` | `{error_class}` | `{preview}`".format(
                    event=item.get("event_type", ""),
                    source=item.get("source", "") or "unknown",
                    agent=item.get("agent", "") or "none",
                    request_id=str(item.get("request_id", "") or "")[:12],
                    task_id=str(item.get("task_id", "") or "")[:12],
                    error_class=item.get("error_class", "") or "unknown",
                    preview=(item.get("query_preview", "") or item.get("error", "") or "")[:120],
                )
            )

    # C2: User-Impact-Block
    ui = dict(summary.get("user_impact") or {})
    lines.extend([
        "",
        "## Nutzerwirkung (C2)",
        f"- response_never_delivered: `{int(ui.get('response_never_delivered_total') or 0)}`",
        f"- silent_failure: `{int(ui.get('silent_failure_total') or 0)}`",
        f"- user_visible_timeout: `{int(ui.get('user_visible_timeout_total') or 0)}`",
        f"- misroute_recovered: `{int(ui.get('misroute_recovered_total') or 0)}`",
    ])
    if list(ui.get("recent_impacts") or []):
        lines.append("")
        lines.append("### Letzte User-Impact-Events")
        for item in list(ui.get("recent_impacts") or [])[:6]:
            lines.append(
                "- `{event}` | req `{request_id}` | agent `{agent}` | `{preview}`".format(
                    event=item.get("event_type", ""),
                    request_id=str(item.get("request_id", "") or "")[:12],
                    agent=item.get("agent", "") or "none",
                    preview=str(item.get("query_preview", "") or "")[:120],
                )
            )
    return "\n".join(lines).rstrip() + "\n"


class AutonomyObservationStore:
    def __init__(self, log_path: Path = DEFAULT_LOG_PATH, state_path: Path = DEFAULT_STATE_PATH) -> None:
        self.log_path = Path(log_path)
        self.state_path = Path(state_path)
        self._lock = threading.Lock()

    def _ensure_parent_dirs(self) -> None:
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self.state_path.parent.mkdir(parents=True, exist_ok=True)

    def load_state(self) -> Dict[str, Any]:
        if not self.state_path.exists():
            return {}
        try:
            raw = json.loads(self.state_path.read_text(encoding="utf-8"))
        except Exception:
            return {}
        if not isinstance(raw, dict):
            return {}
        started_at = str(raw.get("started_at") or "").strip()
        ends_at = str(raw.get("ends_at") or "").strip()
        now = _parse_iso_datetime(_iso_now())
        end_dt = _parse_iso_datetime(ends_at)
        open_ended = bool(started_at and not ends_at)
        active = bool(
            started_at
            and (
                open_ended
                or (ends_at and now and end_dt and now <= end_dt)
            )
        )
        return {
            "label": str(raw.get("label") or "").strip(),
            "started_at": started_at,
            "ends_at": ends_at,
            "duration_days": _normalize_duration_days(raw.get("duration_days"), default=(0 if open_ended else 7)),
            "active": active,
            "log_path": str(raw.get("log_path") or self.log_path),
        }

    def _append_event(self, event_type: str, payload: Dict[str, Any], *, observed_at: str = "") -> Dict[str, Any]:
        self._ensure_parent_dirs()
        event = {
            "id": uuid.uuid4().hex,
            "observed_at": observed_at or _iso_now(),
            "event_type": _normalize_counter_key(event_type, fallback="event"),
            "payload": _json_safe(payload),
        }
        with self._lock:
            with self.log_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(event, ensure_ascii=True, sort_keys=True) + "\n")
        return event

    def start_session(
        self,
        *,
        label: str = "phase3_phase4_weekly",
        duration_days: int = 7,
        started_at: str = "",
    ) -> Dict[str, Any]:
        safe_days = min(365, _normalize_duration_days(duration_days, default=7))
        start_dt = _parse_iso_datetime(started_at) or datetime.now().astimezone()
        end_dt = start_dt + timedelta(days=safe_days) if safe_days > 0 else None
        self._ensure_parent_dirs()
        state = {
            "label": str(label or "phase3_phase4_weekly").strip()[:120],
            "started_at": start_dt.isoformat(),
            "ends_at": end_dt.isoformat() if end_dt else "",
            "duration_days": safe_days,
            "active": True,
            "log_path": str(self.log_path),
        }
        self.state_path.write_text(json.dumps(state, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")
        self._append_event(
            "observation_started",
            {
                "label": state["label"],
                "duration_days": safe_days,
                "ends_at": state["ends_at"],
                "open_ended": safe_days == 0,
            },
            observed_at=state["started_at"],
        )
        return state

    def record_event(self, event_type: str, payload: Dict[str, Any], *, observed_at: str = "") -> bool:
        state = self.load_state()
        if not state.get("active"):
            return False
        self._append_event(event_type, payload, observed_at=observed_at)
        return True

    def iter_events(self, *, since: str = "", until: str = "") -> List[Dict[str, Any]]:
        if not self.log_path.exists():
            return []
        since_dt = _parse_iso_datetime(since)
        until_dt = _parse_iso_datetime(until)
        events: List[Dict[str, Any]] = []
        with self.log_path.open("r", encoding="utf-8") as handle:
            for line in handle:
                text = line.strip()
                if not text:
                    continue
                try:
                    payload = json.loads(text)
                except Exception:
                    continue
                if not isinstance(payload, dict):
                    continue
                observed_at = _parse_iso_datetime(str(payload.get("observed_at") or ""))
                if observed_at is None:
                    continue
                if since_dt is not None and observed_at < since_dt:
                    continue
                if until_dt is not None and observed_at > until_dt:
                    continue
                events.append(payload)
        return events

    def build_summary(self, *, since: str = "", until: str = "") -> Dict[str, Any]:
        state = self.load_state()
        effective_since = str(since or state.get("started_at") or "").strip()
        effective_until = str(until or state.get("ends_at") or _iso_now()).strip()
        events = self.iter_events(since=effective_since, until=effective_until)
        summary = summarize_autonomy_events(events)
        summary["session"] = state
        summary["window"] = {
            "since": effective_since,
            "until": effective_until,
        }
        summary["log_path"] = str(self.log_path)
        return summary


def get_autonomy_observation_store() -> AutonomyObservationStore:
    global _AUTONOMY_OBSERVATION_STORE
    if _AUTONOMY_OBSERVATION_STORE is None:
        log_path = Path(os.getenv("AUTONOMY_OBSERVATION_LOG_PATH", str(DEFAULT_LOG_PATH)))
        state_path = Path(os.getenv("AUTONOMY_OBSERVATION_STATE_PATH", str(DEFAULT_STATE_PATH)))
        _AUTONOMY_OBSERVATION_STORE = AutonomyObservationStore(log_path=log_path, state_path=state_path)
    return _AUTONOMY_OBSERVATION_STORE


def start_autonomy_observation(*, label: str = "phase3_phase4_weekly", duration_days: int = 7) -> Dict[str, Any]:
    return get_autonomy_observation_store().start_session(label=label, duration_days=duration_days)


def record_autonomy_observation(event_type: str, payload: Dict[str, Any], *, observed_at: str = "") -> bool:
    enabled = str(os.getenv("AUTONOMY_OBSERVATION_ENABLED", "true")).strip().lower()
    if enabled in {"0", "false", "no", "off"}:
        return False
    if _should_skip_default_test_writes():
        return False
    return get_autonomy_observation_store().record_event(event_type, payload, observed_at=observed_at)


def build_autonomy_observation_summary(*, since: str = "", until: str = "") -> Dict[str, Any]:
    return get_autonomy_observation_store().build_summary(since=since, until=until)


def record_user_impact_observation(
    event_type: str,
    *,
    request_id: str = "",
    session_id: str = "",
    agent: str = "",
    source: str = "",
    error_class: str = "",
    query_preview: str = "",
) -> bool:
    """Emittiert ein Nutzerwirkungs-Event. Nur bekannte Klassen werden akzeptiert.

    Erhöht user_impact-Zähler, NICHT user_visible_failures_total in request_correlation.
    Emitter sollten nur dort gesetzt werden, wo die Trigger-Semantik gesichert ist.
    """
    if _classify_user_impact_event(event_type) == "none":
        return False
    return record_autonomy_observation(
        event_type,
        {
            "request_id": str(request_id or "").strip(),
            "session_id": str(session_id or "").strip(),
            "agent": str(agent or "").strip(),
            "source": str(source or "").strip(),
            "error_class": str(error_class or "").strip(),
            "query_preview": str(query_preview or "")[:180],
        },
    )


def get_incident_trace(
    request_id: str,
    *,
    since: str = "",
    until: str = "",
) -> List[Dict[str, Any]]:
    """IO-Wrapper: liest Events aus dem Store und delegiert an build_incident_trace.

    Pure Logik liegt in build_incident_trace — dort sind Contracts und Tests angesiedelt.
    """
    if not str(request_id or "").strip():
        return []
    events = get_autonomy_observation_store().iter_events(since=since, until=until)
    return build_incident_trace(events, request_id)


# ---------------------------------------------------------------------------
# C5: Memory-Sync-Observability
# ---------------------------------------------------------------------------

def _record_memory_sync_observation(
    *,
    items_written: int,
    deduped_count: int,
    written: bool,
) -> None:
    """Emittiert ein Memory-Sync-Event für C5-Observability.

    Kein Crash wenn Observation-System nicht verfügbar — best-effort.
    """
    try:
        if written:
            record_autonomy_observation(
                "memory_sync_completed",
                {
                    "items_written": int(items_written),
                    "deduped_count": int(deduped_count),
                    "source": "sync_to_markdown",
                },
            )
        else:
            record_autonomy_observation(
                "memory_sync_skipped_unchanged",
                {
                    "items_written": 0,
                    "deduped_count": int(deduped_count),
                    "source": "sync_to_markdown",
                },
            )
    except Exception:
        pass
