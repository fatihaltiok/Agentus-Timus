from __future__ import annotations

import json
import os
import threading
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_LOG_PATH = PROJECT_ROOT / "logs" / "autonomy_observation.jsonl"
DEFAULT_STATE_PATH = PROJECT_ROOT / "logs" / "autonomy_observation_state.json"

_AUTONOMY_OBSERVATION_STORE: Optional["AutonomyObservationStore"] = None


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
            "recent_failures": [],
        },
        "top_goal_signatures": [],
    }

    recipe_duration_total = 0
    goal_counts: Dict[str, Dict[str, int]] = {}
    meta_diag = summary["meta_diagnostics"]
    request_correlation = summary["request_correlation"]
    recent_failures: List[Dict[str, Any]] = []

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

        elif event_type == "chat_request_completed":
            request_correlation["chat_completed_total"] += 1
            _bump(request_correlation["by_source"], payload.get("source"))
            _bump(request_correlation["by_agent"], payload.get("agent"))

        elif event_type == "chat_request_failed":
            request_correlation["chat_failed_total"] += 1
            request_correlation["user_visible_failures_total"] += 1
            _bump(request_correlation["by_source"], payload.get("source"))
            _bump(request_correlation["by_agent"], payload.get("agent"), fallback="none")
            _bump(
                request_correlation["by_error_class"],
                payload.get("error_class") or "chat_request_failed",
            )
            _record_recent_failure(event_type, observed_at, payload)

        elif event_type == "dispatcher_route_selected":
            request_correlation["dispatcher_routes_total"] += 1
            _bump(request_correlation["by_source"], payload.get("source") or "dispatcher")
            _bump(request_correlation["by_agent"], payload.get("agent"))

        elif event_type == "request_route_selected":
            request_correlation["request_routes_total"] += 1
            _bump(request_correlation["by_source"], payload.get("source"))
            _bump(request_correlation["by_agent"], payload.get("agent"))

        elif event_type == "task_route_selected":
            request_correlation["task_routes_total"] += 1
            _bump(request_correlation["by_source"], payload.get("source"))
            _bump(request_correlation["by_agent"], payload.get("agent"))

        elif event_type == "task_execution_started":
            request_correlation["task_started_total"] += 1
            _bump(request_correlation["by_source"], payload.get("source"))

        elif event_type == "task_execution_completed":
            request_correlation["task_completed_total"] += 1
            _bump(request_correlation["by_source"], payload.get("source"))
            _bump(request_correlation["by_agent"], payload.get("agent"))

        elif event_type == "task_execution_failed":
            request_correlation["task_failed_total"] += 1
            _bump(request_correlation["by_source"], payload.get("source"))
            _bump(request_correlation["by_agent"], payload.get("agent"), fallback="none")
            _bump(
                request_correlation["by_error_class"],
                payload.get("error_class") or "task_execution_failed",
            )
            _record_recent_failure(event_type, observed_at, payload)

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
    summary["request_correlation"]["recent_failures"] = sorted(
        recent_failures,
        key=lambda item: str(item.get("observed_at") or ""),
        reverse=True,
    )[:8]
    return summary


def render_autonomy_observation_markdown(summary: Dict[str, Any]) -> str:
    session = dict(summary.get("session") or {})
    window = dict(summary.get("window") or {})
    recipe = dict(summary.get("recipe_outcomes") or {})
    runtime = dict(summary.get("runtime_gaps") or {})
    hardening = dict(summary.get("self_hardening") or {})
    meta_diag = dict(summary.get("meta_diagnostics") or {})
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
