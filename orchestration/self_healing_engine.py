"""
orchestration/self_healing_engine.py

M3.1 Self-Healing Baseline:
- Health-Checks fuer MCP, Systemdruck, Queue-Backlog und Failure-Spikes
- Persistentes Incident-Tracking
- Recovery-Playbooks (Task-Enqueue) bei neuen/reopened Vorfaellen
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, Optional

import httpx

from orchestration.health_orchestrator import HealthOrchestrator
from orchestration.task_queue import (
    Priority,
    SelfHealingCircuitBreakerState,
    SelfHealingDegradeMode,
    SelfHealingIncidentStatus,
    TaskQueue,
    TaskType,
    get_queue,
)
from utils.http_health import fetch_http_text
from utils.dashscope_native import (
    build_dashscope_native_payload,
    dashscope_native_generation_url,
    extract_dashscope_native_reasoning,
    extract_dashscope_native_text,
)
from utils.policy_gate import audit_policy_decision, evaluate_policy_gate

log = logging.getLogger("SelfHealingEngine")

PLAYBOOK_CODE_FIX = "code_fix"


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name, "true" if default else "false").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)).strip())
    except Exception:
        return default


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)).strip())
    except Exception:
        return default


def _self_healing_feature_enabled() -> bool:
    if _env_bool("AUTONOMY_COMPAT_MODE", True):
        return False
    return _env_bool("AUTONOMY_SELF_HEALING_ENABLED", False)


def _parse_iso(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
        if parsed.tzinfo is not None:
            return parsed.astimezone().replace(tzinfo=None)
        return parsed
    except Exception:
        return None


class SelfHealingEngine:
    """Erkennt Standardstoerungen und startet Recovery-Playbooks."""

    def __init__(
        self,
        queue: TaskQueue | None = None,
        *,
        now_provider: Callable[[], datetime] | None = None,
        mcp_probe: Optional[Callable[[], Dict[str, Any]]] = None,
        system_stats_provider: Optional[Callable[[], Dict[str, Any]]] = None,
        health_orchestrator: Optional[HealthOrchestrator] = None,
    ):
        self.queue = queue or get_queue()
        self._now = now_provider or datetime.now
        self._mcp_probe = mcp_probe or self._default_mcp_probe
        self._system_stats_provider = system_stats_provider or self._default_system_stats_provider
        self._health_orchestrator = health_orchestrator or HealthOrchestrator(now_provider=self._now)

    def _incident_phase_state_key(self, incident_key: str) -> str:
        return f"incident_phase:{str(incident_key or '').strip().lower()}"

    def _incident_memory_state_key(self, component: str, signal: str) -> str:
        return f"incident_memory:{str(component or '').strip().lower()}:{str(signal or '').strip().lower()}"

    def _get_incident_memory(self, *, component: str, signal: str) -> Dict[str, Any]:
        state = self.queue.get_self_healing_runtime_state(self._incident_memory_state_key(component, signal)) or {}
        metadata = state.get("metadata", {}) or {}
        return {
            "state": str(state.get("state_value", "new") or "new"),
            "metadata": metadata,
            "seen_count": int(metadata.get("seen_count", 0) or 0),
            "resolved_count": int(metadata.get("resolved_count", 0) or 0),
            "escalated_count": int(metadata.get("escalated_count", 0) or 0),
            "failed_count": int(metadata.get("failed_count", 0) or 0),
            "conservative_mode": bool(metadata.get("conservative_mode", False)),
            "last_outcome": str(metadata.get("last_outcome", "") or ""),
        }

    def _record_incident_memory(
        self,
        *,
        component: str,
        signal: str,
        incident_key: str,
        outcome: str,
        observed_at: Optional[str] = None,
        extra: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        key = self._incident_memory_state_key(component, signal)
        current = self.queue.get_self_healing_runtime_state(key) or {}
        current_meta = current.get("metadata", {}) or {}
        seen_count = int(current_meta.get("seen_count", 0) or 0)
        resolved_count = int(current_meta.get("resolved_count", 0) or 0)
        escalated_count = int(current_meta.get("escalated_count", 0) or 0)
        failed_count = int(current_meta.get("failed_count", 0) or 0)

        if outcome == "opened":
            seen_count += 1
        elif outcome == "resolved":
            resolved_count += 1
        elif outcome == "escalated":
            escalated_count += 1
        elif outcome in {"failed", "blocked"}:
            failed_count += 1

        conservative_mode = (
            failed_count >= 1
            or escalated_count >= 1
            or (seen_count >= 3 and resolved_count * 2 < seen_count)
        )
        state_value = "known_bad_pattern" if conservative_mode else ("known_pattern" if seen_count >= 2 else "new")
        return self.queue.set_self_healing_runtime_state(
            key,
            state_value,
            metadata_update={
                "component": component,
                "signal": signal,
                "last_incident_key": incident_key,
                "last_outcome": outcome,
                "seen_count": seen_count,
                "resolved_count": resolved_count,
                "escalated_count": escalated_count,
                "failed_count": failed_count,
                "conservative_mode": conservative_mode,
                **(extra or {}),
            },
            observed_at=observed_at,
        )

    def _is_verified_outage(self, *, component: str, signal: str, details: Dict[str, Any]) -> bool:
        payload = details if isinstance(details, dict) else {}
        if bool(payload.get("transient")):
            if str(payload.get("status") or "").lower() in {"starting", "shutting_down"}:
                return False
            if str(payload.get("lifecycle_phase") or "").lower() in {"startup", "shutdown", "warmup"}:
                return False
        if payload.get("ok") is False:
            return True
        if component == "mcp" and signal == "mcp_health":
            if payload.get("status") in {"down", "unhealthy"}:
                return True
            if payload.get("error"):
                return True
        return False

    def _set_incident_phase(
        self,
        *,
        incident_key: str,
        phase: str,
        metadata_update: Optional[Dict[str, Any]] = None,
        observed_at: Optional[str] = None,
    ) -> Dict[str, Any]:
        return self.queue.set_self_healing_runtime_state(
            self._incident_phase_state_key(incident_key),
            phase,
            metadata_update=metadata_update or {},
            observed_at=observed_at,
        )

    def _build_recovery_ladder_state(
        self,
        *,
        incident_key: str,
        component: str,
        signal: str,
        severity: str,
        playbook_attempts: int,
        max_attempts: int,
        allow_playbook: bool,
        retry_due: bool,
        should_attempt: bool,
        attempts_exhausted: bool,
        verified_outage: bool,
        conservative_mode: bool,
        escalated: bool = False,
    ) -> Dict[str, Any]:
        if escalated:
            return {
                "phase": "blocked",
                "stage": "human_escalation",
                "reason": "open_incident_sla_breach",
                "escalation_allowed": True,
            }
        if attempts_exhausted:
            return {
                "phase": "blocked",
                "stage": "manual_review" if conservative_mode else ("restart_candidate" if verified_outage else "manual_review"),
                "reason": "known_bad_pattern_budget_exhausted" if conservative_mode else "playbook_attempt_budget_exhausted",
                "escalation_allowed": bool(verified_outage and not conservative_mode),
            }
        if not allow_playbook:
            return {
                "phase": "degraded",
                "stage": "breaker_cooldown",
                "reason": "circuit_breaker_open",
                "escalation_allowed": False,
            }
        if conservative_mode and should_attempt:
            return {
                "phase": "degraded",
                "stage": "known_bad_pattern",
                "reason": "pattern_memory_conservative_mode",
                "escalation_allowed": False,
            }
        if retry_due or (should_attempt and playbook_attempts >= 1):
            return {
                "phase": "recovering",
                "stage": "fallback",
                "reason": "recovery_retry_due" if retry_due else "playbook_retry",
                "escalation_allowed": False,
            }
        if should_attempt:
            return {
                "phase": "recovering",
                "stage": "diagnose",
                "reason": "initial_playbook_dispatch",
                "escalation_allowed": False,
            }
        return {
            "phase": "degraded",
            "stage": "observe",
            "reason": "incident_open",
            "escalation_allowed": False,
        }

    def run_cycle(self) -> Dict[str, Any]:
        if not _self_healing_feature_enabled():
            return {
                "status": "disabled",
                "checks_run": 0,
                "incidents_opened": 0,
                "incidents_reopened": 0,
                "incidents_resolved": 0,
                "incidents_escalated": 0,
                "escalation_tasks_created": 0,
                "playbooks_triggered": 0,
                "playbooks_failed": 0,
                "playbooks_suppressed": 0,
                "playbook_attempts_blocked": 0,
                "policy_blocks": 0,
                "circuit_breaker_trips": 0,
                "circuit_breaker_recoveries": 0,
                "degrade_mode": SelfHealingDegradeMode.NORMAL,
                "degrade_reason": "disabled",
                "degrade_mode_changed": False,
            }

        summary = {
            "status": "ok",
            "checks_run": 0,
            "incidents_opened": 0,
            "incidents_reopened": 0,
            "incidents_resolved": 0,
            "incidents_escalated": 0,
            "escalation_tasks_created": 0,
            "playbooks_triggered": 0,
            "playbooks_failed": 0,
            "playbooks_suppressed": 0,
            "playbook_attempts_blocked": 0,
            "policy_blocks": 0,
            "circuit_breaker_trips": 0,
            "circuit_breaker_recoveries": 0,
            "routed_playbooks": 0,
            "routed_by_agent": {},
            "routed_by_lane": {},
            "routed_by_template": {},
            "routing_decisions": [],
            "degrade_mode": SelfHealingDegradeMode.NORMAL,
            "degrade_reason": "not_evaluated",
            "degrade_mode_previous": SelfHealingDegradeMode.NORMAL,
            "degrade_mode_changed": False,
            "degrade_score": 0.0,
            "signals": {},
        }

        summary["checks_run"] += 1
        mcp = self._check_mcp_health()
        summary["signals"]["mcp_health"] = mcp
        if not mcp.get("ok"):
            self._register_incident(
                summary=summary,
                incident_key="m3_mcp_health_unavailable",
                component="mcp",
                signal="mcp_health",
                severity="high",
                title="MCP Health endpoint nicht erreichbar",
                details=mcp,
                route=self._health_orchestrator.route_recovery(
                    component="mcp",
                    signal="mcp_health",
                    severity="high",
                    default_target_agent="system",
                    default_priority=int(Priority.CRITICAL),
                    default_template="mcp_recovery",
                ),
                breaker_key="mcp:mcp_health",
            )
        else:
            self._resolve_incident_if_open(
                summary=summary,
                incident_key="m3_mcp_health_unavailable",
                details={"resolved_by": "healthy_mcp_probe"},
                breaker_key="mcp:mcp_health",
                component="mcp",
                signal="mcp_health",
            )

        summary["checks_run"] += 1
        system_pressure = self._check_system_pressure()
        summary["signals"]["system_pressure"] = system_pressure
        if not system_pressure.get("ok"):
            self._register_incident(
                summary=summary,
                incident_key="m3_system_pressure",
                component="system",
                signal="system_pressure",
                severity="medium",
                title="Systemdruck ueber Schwellwert",
                details=system_pressure,
                route=self._health_orchestrator.route_recovery(
                    component="system",
                    signal="system_pressure",
                    severity="medium",
                    default_target_agent="system",
                    default_priority=int(Priority.HIGH),
                    default_template="system_pressure_relief",
                ),
                breaker_key="system:system_pressure",
            )
        else:
            self._resolve_incident_if_open(
                summary=summary,
                incident_key="m3_system_pressure",
                details={"resolved_by": "system_back_to_normal"},
                breaker_key="system:system_pressure",
                component="system",
                signal="system_pressure",
            )

        summary["checks_run"] += 1
        backlog = self._check_queue_backlog()
        summary["signals"]["queue_backlog"] = backlog
        if not backlog.get("ok"):
            self._register_incident(
                summary=summary,
                incident_key="m3_queue_backlog",
                component="queue",
                signal="pending_backlog",
                severity="medium",
                title="Queue-Backlog ueber Schwellwert",
                details=backlog,
                route=self._health_orchestrator.route_recovery(
                    component="queue",
                    signal="pending_backlog",
                    severity="medium",
                    default_target_agent="meta",
                    default_priority=int(Priority.HIGH),
                    default_template="queue_backlog_relief",
                ),
                breaker_key="queue:pending_backlog",
            )
        else:
            self._resolve_incident_if_open(
                summary=summary,
                incident_key="m3_queue_backlog",
                details={"resolved_by": "pending_backlog_normalized"},
                breaker_key="queue:pending_backlog",
                component="queue",
                signal="pending_backlog",
            )

        summary["checks_run"] += 1
        failures = self._check_failure_spike()
        summary["signals"]["failure_spike"] = failures
        if not failures.get("ok"):
            self._register_incident(
                summary=summary,
                incident_key="m3_failure_spike",
                component="providers",
                signal="task_failure_spike",
                severity="high",
                title="Failure-Spike in autonomen Tasks",
                details=failures,
                route=self._health_orchestrator.route_recovery(
                    component="providers",
                    signal="task_failure_spike",
                    severity="high",
                    default_target_agent="meta",
                    default_priority=int(Priority.HIGH),
                    default_template="provider_failover_diagnostics",
                ),
                breaker_key="providers:task_failure_spike",
            )
        else:
            self._resolve_incident_if_open(
                summary=summary,
                incident_key="m3_failure_spike",
                details={"resolved_by": "failure_rate_normalized"},
                breaker_key="providers:task_failure_spike",
                component="providers",
                signal="task_failure_spike",
            )

        self._run_escalation_control_loop(summary=summary)
        self._cleanup_overdue_commitments(summary=summary)

        metrics_snapshot = self.queue.get_self_healing_metrics()
        previous_mode = str(metrics_snapshot.get("degrade_mode") or SelfHealingDegradeMode.NORMAL)
        degrade_eval = self._health_orchestrator.evaluate_degrade_mode(
            metrics=metrics_snapshot,
            signals=summary.get("signals", {}),
            previous_mode=previous_mode,
        )
        runtime_state = self.queue.set_self_healing_runtime_state(
            "degrade_mode",
            str(degrade_eval.get("mode") or SelfHealingDegradeMode.NORMAL),
            metadata_update={
                "reason": str(degrade_eval.get("reason") or ""),
                "reason_codes": degrade_eval.get("reason_codes", []),
                "score": float(degrade_eval.get("score") or 0.0),
                "inputs": degrade_eval.get("inputs", {}),
                "routed_playbooks": int(summary.get("routed_playbooks", 0)),
            },
            observed_at=str(degrade_eval.get("observed_at") or self._now().isoformat()),
        )
        summary["degrade_mode_previous"] = previous_mode
        summary["degrade_mode"] = str(runtime_state.get("state_value") or previous_mode)
        summary["degrade_reason"] = str((runtime_state.get("metadata") or {}).get("reason") or "")
        summary["degrade_mode_changed"] = summary["degrade_mode"] != previous_mode
        summary["degrade_score"] = float(degrade_eval.get("score") or 0.0)

        return summary

    async def attempt_code_fix(
        self,
        *,
        file_path: str,
        error_text: str,
        session_id: str = "",
    ) -> Dict[str, Any]:
        """M18: versucht einen gezielten Code-Fix über die Self-Modification Engine."""
        try:
            from orchestration.self_modifier_engine import get_self_modifier_engine

            result = await get_self_modifier_engine().modify_file(
                file_path=file_path,
                change_description=f"Behebe ImportError/SyntaxError im Zielcode: {error_text}",
                update_snippet=error_text,
                require_tests=True,
                session_id=session_id,
            )
            return {"ok": result.status in {"success", "pending_approval"}, "status": result.status}
        except Exception as exc:
            return {"ok": False, "status": "error", "error": str(exc)}

    def _register_incident(
        self,
        *,
        summary: Dict[str, Any],
        incident_key: str,
        component: str,
        signal: str,
        severity: str,
        title: str,
        details: Dict[str, Any],
        route: Optional[Dict[str, Any]],
        breaker_key: str,
    ) -> None:
        now = self._now()
        route_cfg = route or {}
        target_agent = str(route_cfg.get("target_agent") or "meta")
        priority = int(route_cfg.get("priority") or int(Priority.HIGH))
        playbook_template = str(route_cfg.get("playbook_template") or "generic_recovery")
        lane = str(route_cfg.get("lane") or "self_healing_standard_lane")
        route_class = str(route_cfg.get("route_class") or "standard")
        route_reason = str(route_cfg.get("route_reason") or f"{component}:{signal}:{severity}")
        existing_incident = self.queue.get_self_healing_incident(incident_key)
        existing_details_raw = existing_incident.get("details") if existing_incident else {}
        existing_details = existing_details_raw if isinstance(existing_details_raw, dict) else {}
        try:
            playbook_attempts = max(0, int(existing_details.get("playbook_attempts", 0) or 0))
        except Exception:
            playbook_attempts = 0
        max_attempts = max(1, _env_int("AUTONOMY_SELF_HEALING_MAX_PLAYBOOK_ATTEMPTS", 3))
        verified_outage = self._is_verified_outage(component=component, signal=signal, details=details)
        incident_memory = self._get_incident_memory(component=component, signal=signal)

        breaker = self.queue.get_self_healing_circuit_breaker(breaker_key)
        allow_playbook = True
        retry_due = False
        if breaker and str(breaker.get("state") or "") == SelfHealingCircuitBreakerState.OPEN:
            opened_until = _parse_iso(str(breaker.get("opened_until") or ""))
            if opened_until and now < opened_until:
                allow_playbook = False
            else:
                retry_due = True

        upsert = self.queue.upsert_self_healing_incident(
            incident_key=incident_key,
            component=component,
            signal=signal,
            severity=severity,
            status=SelfHealingIncidentStatus.OPEN,
            title=title,
            details=details,
            observed_at=now.isoformat(),
        )
        if upsert.get("created"):
            summary["incidents_opened"] += 1
            if _env_bool("AUTONOMY_LLM_DIAGNOSIS_ENABLED", True):
                llm_diag = self._diagnose_incident_with_llm(
                    component=component,
                    signal=signal,
                    severity=severity,
                    title=title,
                    details=details,
                )
                if llm_diag:
                    self.queue.upsert_self_healing_incident(
                        incident_key=incident_key,
                        component=component,
                        signal=signal,
                        severity=severity,
                        status=SelfHealingIncidentStatus.OPEN,
                        title=title,
                        details={"llm_diagnosis": llm_diag},
                        observed_at=now.isoformat(),
                    )
                    summary.setdefault("llm_diagnoses", 0)
                    summary["llm_diagnoses"] += 1
                    log.info(
                        "🧠 LLM-Diagnose: %s → %s (confidence=%s)",
                        incident_key,
                        llm_diag.get("root_cause", "?")[:60],
                        llm_diag.get("confidence", "?"),
                    )
        if upsert.get("reopened"):
            summary["incidents_reopened"] += 1

        should_attempt = bool(upsert.get("created") or upsert.get("reopened") or retry_due)
        attempts_exhausted = should_attempt and playbook_attempts >= max_attempts
        ladder = self._build_recovery_ladder_state(
            incident_key=incident_key,
            component=component,
            signal=signal,
            severity=severity,
            playbook_attempts=playbook_attempts,
            max_attempts=max_attempts,
            allow_playbook=allow_playbook,
            retry_due=retry_due,
            should_attempt=should_attempt,
            attempts_exhausted=attempts_exhausted,
            verified_outage=verified_outage,
            conservative_mode=bool(incident_memory.get("conservative_mode")),
        )
        if upsert.get("created") or upsert.get("reopened"):
            self._record_incident_memory(
                component=component,
                signal=signal,
                incident_key=incident_key,
                outcome="opened",
                observed_at=now.isoformat(),
                extra={
                    "last_title": title,
                    "verified_outage": verified_outage,
                },
            )
        self._set_incident_phase(
            incident_key=incident_key,
            phase=ladder["phase"],
            metadata_update={
                "component": component,
                "signal": signal,
                "severity": severity,
                "stage": ladder["stage"],
                "reason": ladder["reason"],
                "verified_outage": verified_outage,
                "playbook_attempts": playbook_attempts,
                "playbook_attempts_max": max_attempts,
                "allow_playbook": allow_playbook,
                "retry_due": retry_due,
                "attempts_exhausted": attempts_exhausted,
                "escalation_allowed": ladder["escalation_allowed"],
                "incident_memory_state": incident_memory.get("state", "new"),
                "incident_memory_seen_count": incident_memory.get("seen_count", 0),
                "conservative_mode": bool(incident_memory.get("conservative_mode")),
                "open_incident": True,
            },
            observed_at=now.isoformat(),
        )
        if should_attempt:
            self._record_routing_decision(
                summary=summary,
                incident_key=incident_key,
                target_agent=target_agent,
                lane=lane,
                template=playbook_template,
                route_class=route_class,
                route_reason=route_reason,
                suppressed=(not allow_playbook) or attempts_exhausted,
            )

        if should_attempt and allow_playbook and not attempts_exhausted:
            action = self._trigger_playbook(
                incident_key=incident_key,
                component=component,
                signal=signal,
                target_agent=target_agent,
                priority=priority,
                details=details,
                playbook_template=playbook_template,
                lane=lane,
                route_class=route_class,
                route_reason=route_reason,
            )
            if action.get("ok"):
                summary["playbooks_triggered"] += 1
                self.queue.upsert_self_healing_incident(
                    incident_key=incident_key,
                    component=component,
                    signal=signal,
                    severity=severity,
                    status=SelfHealingIncidentStatus.OPEN,
                    details={
                        "playbook_task_id": action.get("task_id"),
                        "playbook_attempts": playbook_attempts + 1,
                        "playbook_attempts_max": max_attempts,
                        "breaker_key": breaker_key,
                        "retry_due": retry_due,
                        "verified_outage": verified_outage,
                        "recovery_phase": "recovering",
                        "recovery_stage": "diagnose" if ladder["stage"] == "known_bad_pattern" else ladder["stage"],
                        "incident_memory_state": incident_memory.get("state", "new"),
                        "route_lane": lane,
                        "route_class": route_class,
                        "route_reason": route_reason,
                    },
                    recovery_action=str(action.get("action") or ""),
                    recovery_status="queued",
                    observed_at=now.isoformat(),
                )
            else:
                if action.get("blocked_by_policy"):
                    summary["policy_blocks"] += 1
                summary["playbooks_failed"] += 1
                self._record_incident_memory(
                    component=component,
                    signal=signal,
                    incident_key=incident_key,
                    outcome="failed" if not action.get("blocked_by_policy") else "blocked",
                    observed_at=now.isoformat(),
                    extra={"last_error": str(action.get("error") or "unknown")},
                )
                self.queue.upsert_self_healing_incident(
                    incident_key=incident_key,
                    component=component,
                    signal=signal,
                    severity=severity,
                    status=SelfHealingIncidentStatus.OPEN,
                    details={
                        "playbook_error": str(action.get("error") or "unknown"),
                        "blocked_by_policy": bool(action.get("blocked_by_policy")),
                        "playbook_attempts": playbook_attempts + 1,
                        "playbook_attempts_max": max_attempts,
                        "breaker_key": breaker_key,
                        "verified_outage": verified_outage,
                        "recovery_phase": "degraded",
                        "recovery_stage": "policy_blocked" if action.get("blocked_by_policy") else "dispatch_failed",
                        "route_lane": lane,
                        "route_class": route_class,
                        "route_reason": route_reason,
                    },
                    recovery_action=str(action.get("action") or ""),
                    recovery_status="failed",
                    observed_at=now.isoformat(),
                )
        elif should_attempt and attempts_exhausted:
            summary["playbook_attempts_blocked"] += 1
            self.queue.upsert_self_healing_incident(
                incident_key=incident_key,
                component=component,
                signal=signal,
                severity=severity,
                status=SelfHealingIncidentStatus.OPEN,
                details={
                    "playbook_attempts": playbook_attempts,
                    "playbook_attempts_max": max_attempts,
                    "attempts_exhausted": True,
                    "breaker_key": breaker_key,
                    "verified_outage": verified_outage,
                    "recovery_phase": "blocked",
                    "recovery_stage": ladder["stage"],
                    "incident_memory_state": incident_memory.get("state", "new"),
                    "route_lane": lane,
                    "route_class": route_class,
                    "route_reason": route_reason,
                },
                recovery_action="playbook_attempt_budget_exhausted",
                recovery_status="blocked",
                observed_at=now.isoformat(),
            )
            self._record_incident_memory(
                component=component,
                signal=signal,
                incident_key=incident_key,
                outcome="blocked",
                observed_at=now.isoformat(),
                extra={"last_reason": "attempt_budget_exhausted"},
            )
        elif should_attempt and not allow_playbook:
            summary["playbooks_suppressed"] += 1
            self.queue.upsert_self_healing_incident(
                incident_key=incident_key,
                component=component,
                signal=signal,
                severity=severity,
                status=SelfHealingIncidentStatus.OPEN,
                details={
                    "playbook_attempts": playbook_attempts,
                    "playbook_attempts_max": max_attempts,
                    "breaker_key": breaker_key,
                    "suppressed": True,
                    "verified_outage": verified_outage,
                    "recovery_phase": "degraded",
                    "recovery_stage": ladder["stage"],
                    "incident_memory_state": incident_memory.get("state", "new"),
                    "route_lane": lane,
                    "route_class": route_class,
                    "route_reason": route_reason,
                },
                recovery_action="playbook_suppressed_breaker_open",
                recovery_status="suppressed",
                observed_at=now.isoformat(),
            )

        breaker_result = self.queue.record_self_healing_circuit_breaker_result(
            breaker_key=breaker_key,
            component=component,
            signal=signal,
            success=False,
            failure_threshold=max(1, _env_int("AUTONOMY_SELF_HEALING_BREAKER_FAILURE_THRESHOLD", 3)),
            cooldown_seconds=max(1, _env_int("AUTONOMY_SELF_HEALING_BREAKER_COOLDOWN_SEC", 600)),
            metadata_update={
                "incident_key": incident_key,
                "last_signal_ok": False,
                "route_lane": lane,
                "route_class": route_class,
                "playbook_attempts": playbook_attempts + (1 if should_attempt and allow_playbook and not attempts_exhausted else 0),
            },
            observed_at=now.isoformat(),
        )
        if breaker_result.get("tripped"):
            summary["circuit_breaker_trips"] += 1

    def _record_routing_decision(
        self,
        *,
        summary: Dict[str, Any],
        incident_key: str,
        target_agent: str,
        lane: str,
        template: str,
        route_class: str,
        route_reason: str,
        suppressed: bool,
    ) -> None:
        summary["routed_playbooks"] = int(summary.get("routed_playbooks", 0) or 0) + 1

        by_agent = summary.setdefault("routed_by_agent", {})
        by_agent[target_agent] = int(by_agent.get(target_agent, 0) or 0) + 1

        by_lane = summary.setdefault("routed_by_lane", {})
        by_lane[lane] = int(by_lane.get(lane, 0) or 0) + 1

        by_template = summary.setdefault("routed_by_template", {})
        by_template[template] = int(by_template.get(template, 0) or 0) + 1

        decisions = summary.setdefault("routing_decisions", [])
        if isinstance(decisions, list) and len(decisions) < 20:
            decisions.append(
                {
                    "incident_key": incident_key,
                    "target_agent": target_agent,
                    "lane": lane,
                    "template": template,
                    "route_class": route_class,
                    "route_reason": route_reason,
                    "suppressed": bool(suppressed),
                }
            )

    def _resolve_incident_if_open(
        self,
        *,
        summary: Dict[str, Any],
        incident_key: str,
        details: Optional[Dict[str, Any]] = None,
        breaker_key: str,
        component: str,
        signal: str,
    ) -> None:
        incident = self.queue.get_self_healing_incident(incident_key)
        if incident and str(incident.get("status") or "") != SelfHealingIncidentStatus.RECOVERED:
            resolved_details = {
                "resolved": True,
                "playbook_attempts": 0,
                "attempts_exhausted": False,
                "escalated": False,
                "recovery_phase": "ok",
                "recovery_stage": "resolved",
            }
            if details:
                resolved_details.update(details)
            ok = self.queue.resolve_self_healing_incident(
                incident_key,
                status=SelfHealingIncidentStatus.RECOVERED,
                recovery_action="auto_recovered",
                recovery_status="ok",
                details_update=resolved_details,
                observed_at=self._now().isoformat(),
            )
            if ok:
                summary["incidents_resolved"] += 1
                self._record_incident_memory(
                    component=component,
                    signal=signal,
                    incident_key=incident_key,
                    outcome="resolved",
                    observed_at=self._now().isoformat(),
                    extra={"last_reason": str((details or {}).get("resolved_by") or "auto_recovered")},
                )
                self._set_incident_phase(
                    incident_key=incident_key,
                    phase="ok",
                    metadata_update={
                        "stage": "resolved",
                        "reason": str((details or {}).get("resolved_by") or "auto_recovered"),
                        "open_incident": False,
                    },
                    observed_at=self._now().isoformat(),
                )

        breaker_result = self.queue.record_self_healing_circuit_breaker_result(
            breaker_key=breaker_key,
            component=component,
            signal=signal,
            success=True,
            failure_threshold=max(1, _env_int("AUTONOMY_SELF_HEALING_BREAKER_FAILURE_THRESHOLD", 3)),
            cooldown_seconds=max(1, _env_int("AUTONOMY_SELF_HEALING_BREAKER_COOLDOWN_SEC", 600)),
            metadata_update={"last_signal_ok": True},
            observed_at=self._now().isoformat(),
        )
        if breaker_result.get("recovered"):
            summary["circuit_breaker_recoveries"] += 1

    def _cleanup_overdue_commitments(self, *, summary: Dict[str, Any]) -> None:
        """Bricht Commitments ab, deren Deadline um mehr als 2h überschritten ist.

        Verhindert dauerhaften Planning-Score-Abfall durch nie abgeräumte
        autonome Commitments (z.B. CuriosityEngine-Ziele mit Midnight-Deadline).
        """
        threshold_hours = max(
            0.5,
            float(os.environ.get("AUTONOMY_COMMITMENT_OVERDUE_CANCEL_HOURS", "2.0")),
        )
        try:
            result = self.queue.cancel_overdue_commitments(
                overdue_threshold_hours=threshold_hours,
            )
            cancelled = int(result.get("cancelled", 0))
            if cancelled > 0:
                summary.setdefault("commitments_cancelled", 0)
                summary["commitments_cancelled"] += cancelled
                log.info(
                    "🧹 Self-Healing: %d abgelaufene Commitments abgebrochen "
                    "(Threshold: %.1fh)",
                    cancelled,
                    threshold_hours,
                )
        except Exception as e:
            log.warning("⚠️ Self-Healing: Commitment-Cleanup fehlgeschlagen: %s", e)

        # Stale eskalierte Reviews schließen (sonst -10 Abzug im Planning-Score)
        stale_review_hours = max(
            1.0,
            float(os.environ.get("AUTONOMY_REVIEW_STALE_CLOSE_HOURS", "48.0")),
        )
        try:
            r = self.queue.close_stale_escalated_reviews(stale_after_hours=stale_review_hours)
            closed = int(r.get("closed", 0))
            if closed > 0:
                summary.setdefault("reviews_closed", 0)
                summary["reviews_closed"] += closed
                log.info(
                    "🧹 Self-Healing: %d stale eskalierte Reviews geschlossen (Threshold: %.1fh)",
                    closed,
                    stale_review_hours,
                )
        except Exception as e:
            log.warning("⚠️ Self-Healing: Review-Cleanup fehlgeschlagen: %s", e)

    def _run_escalation_control_loop(self, *, summary: Dict[str, Any]) -> None:
        now = self._now()
        stale_after_minutes = max(5, _env_int("AUTONOMY_SELF_HEALING_ESCALATE_AFTER_MIN", 30))
        max_escalations = max(1, _env_int("AUTONOMY_SELF_HEALING_ESCALATION_LIMIT_PER_CYCLE", 3))
        escalated = 0
        open_incidents = self.queue.list_self_healing_incidents(
            statuses=[SelfHealingIncidentStatus.OPEN],
            limit=200,
        )
        for incident in open_incidents:
            if escalated >= max_escalations:
                break
            first_seen = _parse_iso(str(incident.get("first_seen_at") or ""))
            if first_seen is None:
                continue
            age_minutes = max(0.0, (now - first_seen).total_seconds() / 60.0)
            if age_minutes < float(stale_after_minutes):
                continue
            details_raw = incident.get("details")
            details = details_raw if isinstance(details_raw, dict) else {}
            if bool(details.get("escalated")):
                continue
            playbook_attempts = int(details.get("playbook_attempts", 0) or 0)
            max_attempts = max(1, int(details.get("playbook_attempts_max", _env_int("AUTONOMY_SELF_HEALING_MAX_PLAYBOOK_ATTEMPTS", 3)) or 0))
            verified_outage = bool(details.get("verified_outage"))
            if not verified_outage and playbook_attempts < max_attempts:
                self._set_incident_phase(
                    incident_key=str(incident.get("incident_key") or ""),
                    phase="degraded",
                    metadata_update={
                        "stage": "observe",
                        "reason": "awaiting_verified_outage_or_attempt_exhaustion",
                        "playbook_attempts": playbook_attempts,
                        "playbook_attempts_max": max_attempts,
                        "verified_outage": verified_outage,
                        "open_incident": True,
                    },
                    observed_at=now.isoformat(),
                )
                continue
            if self._escalate_open_incident(summary=summary, incident=incident, age_minutes=age_minutes):
                escalated += 1

    def _escalate_open_incident(
        self,
        *,
        summary: Dict[str, Any],
        incident: Dict[str, Any],
        age_minutes: float,
    ) -> bool:
        incident_key = str(incident.get("incident_key") or "")
        if not incident_key:
            return False

        component = str(incident.get("component") or "unknown")
        signal = str(incident.get("signal") or "unknown_signal")
        route = self._health_orchestrator.route_recovery(
            component=component,
            signal=signal,
            severity="critical",
            default_target_agent="meta",
            default_priority=int(Priority.CRITICAL),
            default_template="incident_escalation",
        )
        target_agent = str(route.get("target_agent") or "meta")
        priority = int(route.get("priority") or int(Priority.CRITICAL))
        playbook_template = "incident_escalation"
        lane = str(route.get("lane") or "self_healing_fast_lane")
        route_class = str(route.get("route_class") or "expedite")
        route_reason = str(route.get("route_reason") or f"{component}:{signal}:critical")

        self._record_routing_decision(
            summary=summary,
            incident_key=incident_key,
            target_agent=target_agent,
            lane=lane,
            template=playbook_template,
            route_class=route_class,
            route_reason=route_reason,
            suppressed=False,
        )

        action = self._trigger_playbook(
            incident_key=incident_key,
            component=component,
            signal=signal,
            target_agent=target_agent,
            priority=priority,
            details={
                "escalation": True,
                "incident_age_minutes": round(age_minutes, 2),
                "reason": "open_incident_sla_breach",
            },
            playbook_template=playbook_template,
            lane=lane,
            route_class=route_class,
            route_reason=route_reason,
        )

        if not action.get("ok"):
            summary["playbooks_failed"] += 1
            self._record_incident_memory(
                component=component,
                signal=signal,
                incident_key=incident_key,
                outcome="failed",
                observed_at=self._now().isoformat(),
                extra={"last_reason": "escalation_queue_task_failed"},
            )
            self.queue.upsert_self_healing_incident(
                incident_key=incident_key,
                component=component,
                signal=signal,
                severity="high",
                status=SelfHealingIncidentStatus.OPEN,
                details={
                    "escalation_error": str(action.get("error") or "unknown"),
                    "escalation_attempted_at": self._now().isoformat(),
                    "escalation_age_minutes": round(age_minutes, 2),
                },
                recovery_action=str(action.get("action") or "escalation_queue_task_failed"),
                recovery_status="escalation_failed",
                observed_at=self._now().isoformat(),
            )
            return False

        summary["incidents_escalated"] += 1
        summary["escalation_tasks_created"] += 1
        summary["playbooks_triggered"] += 1
        self._record_incident_memory(
            component=component,
            signal=signal,
            incident_key=incident_key,
            outcome="escalated",
            observed_at=self._now().isoformat(),
            extra={"last_reason": "open_incident_sla_breach"},
        )
        self._set_incident_phase(
            incident_key=incident_key,
            phase="blocked",
            metadata_update={
                "component": component,
                "signal": signal,
                "stage": "human_escalation",
                "reason": "open_incident_sla_breach",
                "open_incident": True,
            },
            observed_at=self._now().isoformat(),
        )
        self.queue.upsert_self_healing_incident(
            incident_key=incident_key,
            component=component,
            signal=signal,
            severity="high",
            status=SelfHealingIncidentStatus.OPEN,
            details={
                "escalated": True,
                "escalated_at": self._now().isoformat(),
                "escalation_task_id": action.get("task_id"),
                "escalation_age_minutes": round(age_minutes, 2),
                "recovery_phase": "blocked",
                "recovery_stage": "human_escalation",
                "route_lane": lane,
                "route_class": route_class,
                "route_reason": route_reason,
            },
            recovery_action=str(action.get("action") or ""),
            recovery_status="escalated",
            observed_at=self._now().isoformat(),
        )
        return True

    def _trigger_playbook(
        self,
        *,
        incident_key: str,
        component: str,
        signal: str,
        target_agent: str,
        priority: int,
        details: Dict[str, Any],
        playbook_template: str,
        lane: str,
        route_class: str,
        route_reason: str,
    ) -> Dict[str, Any]:
        playbook = self._playbook_template(playbook_template, component=component, signal=signal)
        metadata = {
            "self_healing": True,
            "incident_key": incident_key,
            "component": component,
            "signal": signal,
            "details": details,
            "playbook_version": "v2",
            "playbook_template": playbook_template,
            "playbook_steps": playbook.get("steps", []),
            "suggested_commands": playbook.get("suggested_commands", []),
            "routing": {
                "lane": lane,
                "route_class": route_class,
                "route_reason": route_reason,
                "target_agent": target_agent,
                "priority": int(priority),
            },
            "created_at": self._now().isoformat(),
        }
        description = (
            f"Self-Healing Playbook V2 ({component}/{signal}): "
            f"{playbook.get('headline', 'Bitte Diagnose und Recovery ausfuehren.')} "
            "Nutze die Schritte aus metadata.playbook_steps."
        )
        policy_decision = evaluate_policy_gate(
            gate="autonomous_task",
            subject=description,
            payload={
                "task": description,
                "component": component,
                "signal": signal,
                "target_agent": target_agent,
                "playbook_template": playbook_template,
            },
            source="self_healing_engine._trigger_playbook",
        )
        audit_policy_decision(policy_decision)
        if policy_decision.get("blocked"):
            return {
                "ok": False,
                "action": "policy_blocked_autonomous_task",
                "error": str(policy_decision.get("reason") or "Policy blocked autonomous playbook"),
                "blocked_by_policy": True,
            }

        try:
            task_id = self.queue.add(
                description=description,
                priority=priority,
                task_type=TaskType.TRIGGERED,
                target_agent=target_agent,
                metadata=json.dumps(metadata, ensure_ascii=True),
            )
            return {
                "ok": True,
                "task_id": task_id,
                "action": f"queue_task:{task_id[:8]}:{playbook_template}",
            }
        except Exception as e:
            return {"ok": False, "action": "queue_task_failed", "error": str(e)}

    def _playbook_template(self, template: str, *, component: str, signal: str) -> Dict[str, Any]:
        catalog: Dict[str, Dict[str, Any]] = {
            "mcp_recovery": {
                "headline": "MCP Health pruefen und bei echtem Ausfall sicher neu starten.",
                "steps": [
                    "ZUERST Health endpoint pruefen (GET /health) — bei 200er Antwort ist MCP gesund, ABBRUCH.",
                    "KEIN kill, KEIN kill -9, KEIN systemctl ohne vorherige Health-Pruefung.",
                    "Nur wenn /health tatsaechlich nicht antwortet: MCP per nohup neu starten.",
                    "Nach 5 Sekunden erneut /health pruefen und Ergebnis melden.",
                ],
                "suggested_commands": [
                    "curl -sS http://127.0.0.1:5000/health",
                    "cd /home/fatih-ubuntu/dev/timus && nohup python3 server/mcp_server.py > logs/mcp_restart.log 2>&1 &",
                    "sleep 5 && curl -sS http://127.0.0.1:5000/health",
                ],
            },
            "system_pressure_relief": {
                "headline": "Ressourcenengpass analysieren und Last kurzfristig reduzieren.",
                "steps": [
                    "Top CPU/RAM Prozesse identifizieren.",
                    "Nicht-kritische Workloads drosseln oder pausieren.",
                    "Nach 5 Minuten erneute Messung dokumentieren.",
                ],
                "suggested_commands": [
                    "ps aux --sort=-%cpu | head -20",
                    "ps aux --sort=-%mem | head -20",
                ],
            },
            "queue_backlog_relief": {
                "headline": "Queue-Backlog triagieren und Prioritaeten neu ordnen.",
                "steps": [
                    "Top 20 pending Tasks nach Prioritaet analysieren.",
                    "Niedrige Prioritaeten bei Bedarf verschieben.",
                    "Blocker/Dependencies fuer High-Priority Tasks markieren.",
                ],
                "suggested_commands": [],
            },
            "provider_failover_diagnostics": {
                "headline": "Provider-Failures klassifizieren und Failover-Kette stabilisieren.",
                "steps": [
                    "Fehlertypen aus den letzten failed Tasks extrahieren.",
                    "Betroffene Agent/Provider identifizieren.",
                    "Fallback-Kette anpassen und erneuten Lauf pruefen.",
                ],
                "suggested_commands": [],
            },
            PLAYBOOK_CODE_FIX: {
                "headline": "ImportError oder SyntaxError analysieren und gezielten Code-Fix vorbereiten.",
                "steps": [
                    "Betroffene Datei und konkrete Fehlermeldung aus Logs extrahieren.",
                    "Developer-Agent analysiert Root-Cause und erzeugt präzisen Fix-Vorschlag.",
                    "SelfModifierEngine.modify_file() mit Fix anwenden oder Approval anfordern.",
                    "Danach Import-/Syntax-Check und gezielte Tests ausführen.",
                    "Wenn Fix erfolgreich war: Dispatcher/Service sauber neu starten oder Health prüfen.",
                ],
                "suggested_commands": [],
            },
            "incident_escalation": {
                "headline": "Incident eskalieren, On-Call informieren und Recovery-War-Room starten.",
                "steps": [
                    "Incident mit Zeitstempel und Impact klassifizieren.",
                    "On-Call oder Betreiberkanal mit Kontext und Task-ID alarmieren.",
                    "Rollback/Fallback-Strategie priorisieren und verifizieren.",
                ],
                "suggested_commands": [],
            },
        }
        return catalog.get(
            template,
            {
                "headline": f"Diagnose fuer {component}/{signal} durchfuehren.",
                "steps": ["Signal validieren.", "Root-Cause eingrenzen.", "Recovery pruefen."],
                "suggested_commands": [],
            },
        )

    def _diagnose_incident_with_llm(
        self,
        *,
        component: str,
        signal: str,
        severity: str,
        title: str,
        details: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Schicht 2: Analysiert einen neuen Incident mit dem konfigurierten System-Modell."""
        import re

        try:
            from agent.providers import ModelProvider, get_provider_client, resolve_model_provider_env

            model, provider = resolve_model_provider_env(
                model_env="SYSTEM_MODEL",
                provider_env="SYSTEM_MODEL_PROVIDER",
                fallback_model="qwen/qwen3.5-plus-02-15",
                fallback_provider=ModelProvider.OPENROUTER,
            )
            if provider not in {
                ModelProvider.OPENAI,
                ModelProvider.ZAI,
                ModelProvider.DASHSCOPE,
                ModelProvider.DASHSCOPE_NATIVE,
                ModelProvider.DEEPSEEK,
                ModelProvider.MOONSHOT,
                ModelProvider.INCEPTION,
                ModelProvider.NVIDIA,
                ModelProvider.OPENROUTER,
            }:
                log.debug("LLM-Diagnose uebersprungen: system provider '%s' ist hier nicht openai-kompatibel", provider.value)
                return {}
            prompt = (
                "Du bist ein KI-System-Diagnostiker für den autonomen Agenten Timus.\n"
                "Analysiere folgenden Incident und antworte NUR mit validem JSON.\n\n"
                f"Component: {component}\n"
                f"Signal: {signal}\n"
                f"Severity: {severity}\n"
                f"Title: {title}\n"
                f"Details: {json.dumps(details, ensure_ascii=False)[:600]}\n\n"
                "Antworte mit genau diesem JSON-Schema (keine weiteren Erklärungen):\n"
                '{"root_cause": "...", "confidence": "low|medium|high", '
                '"recommended_action": "...", "urgency": "low|medium|high|immediate", '
                '"pattern_hint": "..."}'
            )
            if provider == ModelProvider.DASHSCOPE_NATIVE:
                provider_client = get_provider_client()
                api_key = provider_client.get_api_key(ModelProvider.DASHSCOPE_NATIVE)
                base_url = provider_client.get_base_url(ModelProvider.DASHSCOPE_NATIVE)
                payload = build_dashscope_native_payload(
                    model=model,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.1,
                    max_tokens=300,
                )
                with httpx.Client(timeout=float(os.getenv("DASHSCOPE_NATIVE_TIMEOUT", "60"))) as http:
                    response = http.post(
                        dashscope_native_generation_url(base_url, model),
                        headers={
                            "Authorization": f"Bearer {api_key}",
                            "Content-Type": "application/json",
                        },
                        json=payload,
                    )
                    response.raise_for_status()
                    response_payload = response.json()
                raw = extract_dashscope_native_text(response_payload) or extract_dashscope_native_reasoning(response_payload)
            else:
                client = get_provider_client().get_client(provider)
                response = client.chat.completions.create(
                    model=model,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.1,
                    max_tokens=300,
                )
                raw = (response.choices[0].message.content or "").strip()
            match = re.search(r"\{.*\}", raw, re.DOTALL)
            if match:
                return json.loads(match.group(0))
        except Exception as e:
            log.debug("LLM-Diagnose fehlgeschlagen (nicht kritisch): %s", e)
        return {}

    def _check_mcp_health(self) -> Dict[str, Any]:
        try:
            probe = self._mcp_probe() or {}
            ok = bool(probe.get("ok"))
            if not ok:
                # Post-Standby-Schutz: kurz warten und nochmal prüfen, bevor ein
                # Incident geöffnet wird — vermeidet False-Positives nach Resume.
                import time as _time
                delay = _env_float("AUTONOMY_SELF_HEALING_MCP_RETRY_DELAY_SEC", 5.0)
                _time.sleep(delay)
                probe = self._mcp_probe() or {}
                ok = bool(probe.get("ok"))
                probe["retry_after_sec"] = delay
            return {"ok": ok, **probe}
        except Exception as e:
            return {"ok": False, "error": f"mcp_probe_error:{e}"}

    def _check_system_pressure(self) -> Dict[str, Any]:
        try:
            stats = self._system_stats_provider() or {}
            cpu = float(stats.get("cpu_percent") or 0.0)
            ram = float(stats.get("ram_percent") or 0.0)
            disk = float(stats.get("disk_percent") or 0.0)
            cpu_threshold = _env_float("MONITOR_CPU_THRESHOLD", 85.0)
            ram_threshold = _env_float("MONITOR_RAM_THRESHOLD", 85.0)
            disk_threshold = _env_float("MONITOR_DISK_THRESHOLD", 90.0)
            breaches = []
            if cpu >= cpu_threshold:
                breaches.append(f"cpu={cpu}")
            if ram >= ram_threshold:
                breaches.append(f"ram={ram}")
            if disk >= disk_threshold:
                breaches.append(f"disk={disk}")
            return {
                "ok": len(breaches) == 0,
                "breaches": breaches,
                "cpu_percent": cpu,
                "ram_percent": ram,
                "disk_percent": disk,
            }
        except Exception as e:
            return {"ok": False, "error": f"system_stats_error:{e}"}

    def _check_queue_backlog(self) -> Dict[str, Any]:
        stats = self.queue.stats()
        pending = int(stats.get("pending", 0) or 0)
        in_progress = int(stats.get("in_progress", 0) or 0)
        threshold = max(1, _env_int("AUTONOMY_SELF_HEALING_PENDING_THRESHOLD", 30))
        return {
            "ok": pending < threshold,
            "pending": pending,
            "in_progress": in_progress,
            "threshold": threshold,
        }

    def _check_failure_spike(self) -> Dict[str, Any]:
        window_minutes = max(5, _env_int("AUTONOMY_SELF_HEALING_FAILURE_WINDOW_MIN", 60))
        threshold = max(1, _env_int("AUTONOMY_SELF_HEALING_FAILURE_THRESHOLD", 6))
        since = self._now() - timedelta(minutes=window_minutes)
        failed_recent = 0
        total_recent = 0
        tasks = self.queue.get_all(limit=200)
        for task in tasks:
            ts = _parse_iso(str(task.get("completed_at") or task.get("created_at") or ""))
            if ts is None or ts < since:
                continue
            total_recent += 1
            if str(task.get("status") or "") == "failed":
                failed_recent += 1
        return {
            "ok": failed_recent < threshold,
            "window_minutes": window_minutes,
            "failed_recent": failed_recent,
            "total_recent": total_recent,
            "threshold": threshold,
        }

    def _default_mcp_probe(self) -> Dict[str, Any]:
        url = os.getenv("AUTONOMY_SELF_HEALING_MCP_HEALTH_URL", "http://127.0.0.1:5000/health").strip()
        timeout = _env_float("AUTONOMY_SELF_HEALING_HTTP_TIMEOUT_SEC", 2.0)
        try:
            probe = fetch_http_text(url, timeout=timeout)
            status_code = int(probe["status_code"])
            body = str(probe.get("body") or "")
            payload: Dict[str, Any] = {}
            if body.strip():
                try:
                    loaded = json.loads(body)
                    if isinstance(loaded, dict):
                        payload = loaded
                except Exception:
                    payload = {"raw_body": body[:200]}
            healthy = status_code == 200 and str(payload.get("status") or "").lower() in {"healthy", "ok"}
            lifecycle = payload.get("lifecycle") if isinstance(payload.get("lifecycle"), dict) else {}
            status = str(payload.get("status") or "")
            transient = bool(payload.get("transient"))
            return {
                "ok": healthy,
                "http_status": status_code,
                "endpoint": url,
                "status": payload.get("status"),
                "transient": transient,
                "lifecycle_phase": lifecycle.get("phase"),
            }
        except Exception as e:
            return {"ok": False, "endpoint": url, "error": str(e)}
        except Exception as e:
            return {"ok": False, "endpoint": url, "error": str(e)}

    def _default_system_stats_provider(self) -> Dict[str, Any]:
        from gateway.system_monitor import get_system_stats

        return get_system_stats()
