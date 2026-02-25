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
import urllib.error
import urllib.request
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, Optional

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
from utils.policy_gate import audit_policy_decision, evaluate_policy_gate

log = logging.getLogger("SelfHealingEngine")


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
        if upsert.get("reopened"):
            summary["incidents_reopened"] += 1

        should_attempt = bool(upsert.get("created") or upsert.get("reopened") or retry_due)
        attempts_exhausted = should_attempt and playbook_attempts >= max_attempts
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
                    "route_lane": lane,
                    "route_class": route_class,
                    "route_reason": route_reason,
                },
                recovery_action="playbook_attempt_budget_exhausted",
                recovery_status="blocked",
                observed_at=now.isoformat(),
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
                "headline": "MCP-Service pruefen, ggf. restarten und Health verifizieren.",
                "steps": [
                    "Health endpoint pruefen (/health).",
                    "Bei Ausfall Service restarten (timus-mcp.service).",
                    "JSON-RPC Probe gegen root endpoint testen.",
                ],
                "suggested_commands": [
                    "curl -sS http://127.0.0.1:5000/health",
                    "systemctl restart timus-mcp.service",
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

    def _check_mcp_health(self) -> Dict[str, Any]:
        try:
            probe = self._mcp_probe() or {}
            ok = bool(probe.get("ok"))
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
            with urllib.request.urlopen(url, timeout=timeout) as resp:
                status_code = int(getattr(resp, "status", 200) or 200)
                body = resp.read().decode("utf-8", errors="ignore")
            payload: Dict[str, Any] = {}
            if body.strip():
                try:
                    loaded = json.loads(body)
                    if isinstance(loaded, dict):
                        payload = loaded
                except Exception:
                    payload = {"raw_body": body[:200]}
            healthy = status_code == 200 and str(payload.get("status") or "").lower() in {"healthy", "ok"}
            return {
                "ok": healthy,
                "http_status": status_code,
                "endpoint": url,
                "status": payload.get("status"),
            }
        except urllib.error.URLError as e:
            return {"ok": False, "endpoint": url, "error": str(e)}
        except Exception as e:
            return {"ok": False, "endpoint": url, "error": str(e)}

    def _default_system_stats_provider(self) -> Dict[str, Any]:
        from gateway.system_monitor import get_system_stats

        return get_system_stats()
