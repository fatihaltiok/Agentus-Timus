"""Maschinenlesbarer Self-State fuer Meta-Orchestrierung."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Dict, Iterable, List, Tuple

from orchestration.llm_budget_guard import get_public_budget_status
from orchestration.self_stabilization_gate import evaluate_self_stabilization_gate
from orchestration.task_queue import (
    SelfHealingCircuitBreakerState,
    SelfHealingIncidentStatus,
    get_queue,
)


def _as_list(values: Iterable[str]) -> List[str]:
    return [str(value).strip() for value in values if str(value).strip()]


@dataclass(frozen=True)
class MetaRiskSignal:
    signal: str
    severity: str
    reason: str

    def to_dict(self) -> Dict[str, str]:
        return asdict(self)


@dataclass(frozen=True)
class MetaToolState:
    tool: str
    state: str
    reason: str

    def to_dict(self) -> Dict[str, str]:
        return asdict(self)


@dataclass(frozen=True)
class MetaRuntimeConstraints:
    budget_state: str
    stability_gate_state: str
    degrade_mode: str
    open_incidents: int
    circuit_breakers_open: int
    resource_guard_state: str
    resource_guard_reason: str
    quarantined_incidents: int
    cooldown_incidents: int
    known_bad_patterns: int
    release_blocked: bool
    autonomy_hold: bool

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class MetaConfidenceBound:
    area: str
    level: str
    reason: str

    def to_dict(self) -> Dict[str, str]:
        return asdict(self)


@dataclass(frozen=True)
class MetaAutonomyLimit:
    limit: str
    state: str
    reason: str

    def to_dict(self) -> Dict[str, str]:
        return asdict(self)


def _coerce_runtime_constraints(value: Dict[str, Any] | MetaRuntimeConstraints | None) -> MetaRuntimeConstraints:
    if isinstance(value, MetaRuntimeConstraints):
        return value
    if isinstance(value, dict):
        return MetaRuntimeConstraints(
            budget_state=str(value.get("budget_state", "unknown") or "unknown"),
            stability_gate_state=str(value.get("stability_gate_state", "unknown") or "unknown"),
            degrade_mode=str(value.get("degrade_mode", "unknown") or "unknown"),
            open_incidents=int(value.get("open_incidents", 0) or 0),
            circuit_breakers_open=int(value.get("circuit_breakers_open", 0) or 0),
            resource_guard_state=str(value.get("resource_guard_state", "unknown") or "unknown"),
            resource_guard_reason=str(value.get("resource_guard_reason", "") or ""),
            quarantined_incidents=int(value.get("quarantined_incidents", 0) or 0),
            cooldown_incidents=int(value.get("cooldown_incidents", 0) or 0),
            known_bad_patterns=int(value.get("known_bad_patterns", 0) or 0),
            release_blocked=bool(value.get("release_blocked")),
            autonomy_hold=bool(value.get("autonomy_hold")),
        )
    return _derive_runtime_constraints()


@dataclass(frozen=True)
class MetaSelfState:
    identity: str
    orchestration_role: str
    strategy_posture: str
    preferred_entry_agent: str
    task_type: str
    site_kind: str
    available_specialists: Tuple[str, ...]
    required_capabilities: Tuple[str, ...]
    current_capabilities: Tuple[str, ...]
    partial_capabilities: Tuple[str, ...]
    planned_capabilities: Tuple[str, ...]
    blocked_capabilities: Tuple[str, ...]
    confidence_bounds: Tuple[MetaConfidenceBound, ...]
    autonomy_limits: Tuple[MetaAutonomyLimit, ...]
    active_tools: Tuple[MetaToolState, ...]
    known_limits: Tuple[str, ...]
    active_risks: Tuple[MetaRiskSignal, ...]
    runtime_constraints: MetaRuntimeConstraints
    structured_handoff_required: bool

    def to_dict(self) -> Dict[str, Any]:
        payload = asdict(self)
        payload["available_specialists"] = list(self.available_specialists)
        payload["required_capabilities"] = list(self.required_capabilities)
        payload["current_capabilities"] = list(self.current_capabilities)
        payload["partial_capabilities"] = list(self.partial_capabilities)
        payload["planned_capabilities"] = list(self.planned_capabilities)
        payload["blocked_capabilities"] = list(self.blocked_capabilities)
        payload["confidence_bounds"] = [item.to_dict() for item in self.confidence_bounds]
        payload["autonomy_limits"] = [item.to_dict() for item in self.autonomy_limits]
        payload["active_tools"] = [tool.to_dict() for tool in self.active_tools]
        payload["known_limits"] = list(self.known_limits)
        payload["active_risks"] = [risk.to_dict() for risk in self.active_risks]
        payload["runtime_constraints"] = self.runtime_constraints.to_dict()
        return payload


def _derive_runtime_constraints() -> MetaRuntimeConstraints:
    try:
        budget = get_public_budget_status() or {}
    except Exception:
        budget = {}

    self_healing: Dict[str, Any]
    try:
        queue = get_queue()
        metrics = queue.get_self_healing_metrics() or {}
        resource_guard = queue.get_self_healing_runtime_state("resource_guard") or {}
        resource_guard_meta = resource_guard.get("metadata", {}) or {}
        incidents = queue.list_self_healing_incidents(
            statuses=[SelfHealingIncidentStatus.OPEN],
            limit=100,
        )
        open_breakers = queue.list_self_healing_circuit_breakers(
            states=[SelfHealingCircuitBreakerState.OPEN],
            limit=20,
        )
        rows: List[Dict[str, Any]] = []
        for incident in incidents:
            incident_key = str(incident.get("incident_key", "") or "").lower()
            notify_state = queue.get_self_healing_runtime_state(f"incident_notify:{incident_key}") or {}
            notify_meta = notify_state.get("metadata", {}) or {}
            phase_state = queue.get_self_healing_runtime_state(f"incident_phase:{incident_key}") or {}
            quarantine_state = queue.get_self_healing_runtime_state(f"incident_quarantine:{incident_key}") or {}
            memory_state = queue.get_self_healing_runtime_state(
                "incident_memory:{component}:{signal}".format(
                    component=str(incident.get("component", "") or "").lower(),
                    signal=str(incident.get("signal", "") or "").lower(),
                )
            ) or {}
            rows.append(
                {
                    "recovery_phase": str(phase_state.get("state_value", "unknown") or "unknown"),
                    "quarantine_state": str(quarantine_state.get("state_value", "none") or "none"),
                    "notification_state": str(notify_state.get("state_value", "none") or "none"),
                    "memory_state": str(memory_state.get("state_value", "new") or "new"),
                    "cooldown_until": str(notify_meta.get("cooldown_until", "") or ""),
                }
            )
        self_healing = {
            "open_incidents": int(metrics.get("open_incidents", 0) or 0),
            "degrade_mode": str(metrics.get("degrade_mode", "normal") or "normal"),
            "circuit_breakers_open": int(metrics.get("circuit_breakers_open", 0) or 0),
            "open_breakers": [
                {
                    "breaker_key": str(row.get("breaker_key", "") or ""),
                    "component": str(row.get("component", "") or ""),
                    "signal": str(row.get("signal", "") or ""),
                    "opened_until": str(row.get("opened_until", "") or ""),
                }
                for row in open_breakers
            ],
            "resource_guard_state": str(resource_guard.get("state_value", "inactive") or "inactive"),
            "resource_guard_reason": str(resource_guard_meta.get("reason", "") or ""),
            "incidents": rows,
        }
    except Exception:
        self_healing = {
            "open_incidents": 0,
            "degrade_mode": "unknown",
            "circuit_breakers_open": 0,
            "open_breakers": [],
            "resource_guard_state": "unknown",
            "resource_guard_reason": "",
            "incidents": [],
        }

    try:
        stability_gate = evaluate_self_stabilization_gate(self_healing)
    except Exception:
        stability_gate = {
            "state": "unknown",
            "release_blocked": False,
            "autonomy_hold": False,
            "quarantined_incidents": 0,
            "cooldown_incidents": 0,
            "known_bad_patterns": 0,
        }

    return MetaRuntimeConstraints(
        budget_state=str(budget.get("state", "unknown") or "unknown"),
        stability_gate_state=str(stability_gate.get("state", "unknown") or "unknown"),
        degrade_mode=str(self_healing.get("degrade_mode", "unknown") or "unknown"),
        open_incidents=int(self_healing.get("open_incidents", 0) or 0),
        circuit_breakers_open=int(self_healing.get("circuit_breakers_open", 0) or 0),
        resource_guard_state=str(self_healing.get("resource_guard_state", "unknown") or "unknown"),
        resource_guard_reason=str(self_healing.get("resource_guard_reason", "") or ""),
        quarantined_incidents=int(stability_gate.get("quarantined_incidents", 0) or 0),
        cooldown_incidents=int(stability_gate.get("cooldown_incidents", 0) or 0),
        known_bad_patterns=int(stability_gate.get("known_bad_patterns", 0) or 0),
        release_blocked=bool(stability_gate.get("release_blocked")),
        autonomy_hold=bool(stability_gate.get("autonomy_hold")),
    )


def _derive_active_tools(
    classification: Dict[str, Any],
    runtime_constraints: MetaRuntimeConstraints,
) -> Tuple[MetaToolState, ...]:
    required_capabilities = {
        str(item).strip().lower()
        for item in (classification.get("required_capabilities") or [])
        if str(item).strip()
    }
    budget_state = runtime_constraints.budget_state.strip().lower()
    stability_state = runtime_constraints.stability_gate_state.strip().lower()
    resource_guard_state = runtime_constraints.resource_guard_state.strip().lower()

    def _degraded_by_budget() -> bool:
        return budget_state in {"warn", "warning", "soft_limit", "hard_limit", "blocked"}

    def _blocked_by_stability() -> bool:
        return stability_state == "blocked"

    def _degraded_by_stability() -> bool:
        return stability_state == "warn"

    tools: List[MetaToolState] = [
        MetaToolState(
            tool="delegate_to_agent",
            state="degraded" if _blocked_by_stability() or _degraded_by_budget() else "ready",
            reason=(
                "Stabilitaets- oder Budgetguard verlangt konservativere Delegation"
                if _blocked_by_stability() or _degraded_by_budget()
                else "meta orchestriert Spezialagenten ueber strukturierte Delegation"
            ),
        ),
    ]
    if "browser_navigation" in required_capabilities or "ui_interaction" in required_capabilities:
        tools.append(
            MetaToolState(
                tool="browser_workflow_plan",
                state=(
                    "blocked"
                    if _blocked_by_stability()
                    else "degraded"
                    if _degraded_by_stability() or resource_guard_state not in {"", "inactive", "none", "unknown"}
                    else "ready"
                ),
                reason=(
                    "Self-Stabilization blockiert Browser-Workflows"
                    if _blocked_by_stability()
                    else "Browser-Workflows laufen unter Guard/Cooldown konservativer"
                    if _degraded_by_stability() or resource_guard_state not in {"", "inactive", "none", "unknown"}
                    else "strukturierte Browserplaene und Zustandsmodelle verfuegbar"
                ),
            )
        )
    if "content_extraction" in required_capabilities or "web_research" in required_capabilities:
        tools.append(
            MetaToolState(
                tool="research_pipeline",
                state="degraded" if _degraded_by_budget() else "ready",
                reason=(
                    "Budgetguard bevorzugt sparsame oder konservative Research-Laeufe"
                    if _degraded_by_budget()
                    else "Research-Agent kann Quellen, Metadaten und Zusammenfassungen liefern"
                ),
            )
        )
    if "pdf_creation" in required_capabilities or "docx_creation" in required_capabilities:
        tools.append(
            MetaToolState(
                tool="document_exports",
                state="degraded" if _degraded_by_budget() else "ready",
                reason=(
                    "Budgetguard priorisiert knappe Artefaktausgabe"
                    if _degraded_by_budget()
                    else "Dokument-Agent kann Artefakte aus strukturierten Inputs erzeugen"
                ),
            )
        )
    if "diagnostics" in required_capabilities or "service_inspection" in required_capabilities:
        tools.append(
            MetaToolState(
                tool="system_diagnostics",
                state="ready",
                reason="System-/Shell-Pfade stehen fuer Diagnosen und Remediation bereit",
            )
        )
    return tuple(tools)


def _derive_known_limits(
    classification: Dict[str, Any],
    learning_snapshot: Dict[str, Any] | None,
    runtime_constraints: MetaRuntimeConstraints,
) -> Tuple[str, ...]:
    limits = [
        "bounded_replanning_only",
        "recipe_switching_not_enabled",
        "specialist_handoffs_partial",
    ]
    task_type = str(classification.get("task_type") or "").strip().lower()
    site_kind = str(classification.get("site_kind") or "").strip().lower()
    if task_type in {"youtube_content_extraction", "web_content_extraction", "multi_stage_web_task"}:
        limits.append("ui_state_depends_on_external_site")
    if site_kind in {"youtube", "x", "linkedin", "outlook", "booking"}:
        limits.append("site_profile_coverage_partial")
    posture = str((learning_snapshot or {}).get("posture") or "").strip().lower()
    if posture == "conservative":
        limits.append("conservative_learning_guard_enabled")
    if runtime_constraints.budget_state not in {"", "pass", "ok", "unknown"}:
        limits.append(f"budget_guard_{runtime_constraints.budget_state}")
    if runtime_constraints.stability_gate_state not in {"", "pass", "ok", "unknown"}:
        limits.append(f"stability_gate_{runtime_constraints.stability_gate_state}")
    if runtime_constraints.resource_guard_state not in {"", "inactive", "none", "unknown"}:
        limits.append("resource_guard_active")
    if runtime_constraints.open_incidents > 0:
        limits.append("self_healing_incidents_open")
    return tuple(_as_list(limits))


def _derive_risks(
    classification: Dict[str, Any],
    learning_snapshot: Dict[str, Any] | None,
    runtime_constraints: MetaRuntimeConstraints,
) -> Tuple[MetaRiskSignal, ...]:
    risks: List[MetaRiskSignal] = []
    task_type = str(classification.get("task_type") or "").strip().lower()
    posture = str((learning_snapshot or {}).get("posture") or "").strip().lower()
    if classification.get("needs_structured_handoff"):
        risks.append(
            MetaRiskSignal(
                signal="multi_stage_coordination",
                severity="warning",
                reason="mehrstufige Aufgabe braucht disziplinierte Agentenuebergaben",
            )
        )
    if posture == "conservative":
        risks.append(
            MetaRiskSignal(
                signal="negative_outcome_history",
                severity="warning",
                reason="historische Outcomes legen konservativere Orchestrierung nahe",
            )
        )
    if task_type in {"youtube_content_extraction", "multi_stage_web_task"}:
        risks.append(
            MetaRiskSignal(
                signal="external_ui_variability",
                severity="warning",
                reason="externe Webseiten koennen Layout und Zustandsuebergaenge aendern",
            )
        )
    if runtime_constraints.budget_state in {"warn", "warning", "soft_limit"}:
        risks.append(
            MetaRiskSignal(
                signal="budget_pressure",
                severity="warning",
                reason="aktuelle Budgetlage verlangt sparsamere oder kuerzere Orchestrierung",
            )
        )
    if runtime_constraints.budget_state in {"hard_limit", "blocked"}:
        risks.append(
            MetaRiskSignal(
                signal="budget_blocked",
                severity="error",
                reason="harte Budgetgrenze schraenkt spezialisierte Delegation ein",
            )
        )
    if runtime_constraints.stability_gate_state == "warn":
        risks.append(
            MetaRiskSignal(
                signal="stability_guard_active",
                severity="warning",
                reason="Self-Stabilization meldet degrade/warn und verlangt konservativere Schritte",
            )
        )
    if runtime_constraints.stability_gate_state == "blocked":
        risks.append(
            MetaRiskSignal(
                signal="stability_gate_blocked",
                severity="error",
                reason="aktuelle Stabilitaetslage blockiert riskantere oder offene Workflow-Schritte",
            )
        )
    if runtime_constraints.resource_guard_state not in {"", "inactive", "none", "unknown"}:
        risks.append(
            MetaRiskSignal(
                signal="resource_guard_active",
                severity="warning",
                reason="Ressourcenschutz drosselt schwere autonome oder browserlastige Schritte",
            )
        )
    return tuple(risks)


def _derive_capability_sets(
    classification: Dict[str, Any],
    runtime_constraints: MetaRuntimeConstraints,
    active_tools: Tuple[MetaToolState, ...],
) -> Tuple[Tuple[str, ...], Tuple[str, ...], Tuple[str, ...], Tuple[str, ...]]:
    current = {
        "structured_delegation",
        "specialist_routing",
        "conversation_state_tracking",
        "turn_understanding",
        "context_rehydration",
        "topic_state_tracking",
        "preference_instruction_memory",
        "response_mode_policy",
        "runtime_visibility",
    }
    partial = {
        "specialist_handoffs",
        "site_profile_coverage",
    }
    planned = {
        "specialist_context_propagation",
        "approval_gate_workflows",
        "user_mediated_login",
        "state_decay_cleanup",
        "self_model_policy_binding",
    }
    blocked: set[str] = set()

    task_type = str(classification.get("task_type") or "").strip().lower()
    site_kind = str(classification.get("site_kind") or "").strip().lower()
    required_capabilities = {
        str(item).strip().lower()
        for item in (classification.get("required_capabilities") or [])
        if str(item).strip()
    }

    if classification.get("recommended_recipe_id") or classification.get("recipe_stages"):
        current.add("recipe_orchestration")
    if "diagnostics" in required_capabilities or "service_inspection" in required_capabilities or task_type == "system_diagnosis":
        current.add("system_diagnostics")
    if task_type in {"simple_live_lookup", "location_local_search", "location_route"}:
        current.add("lightweight_live_lookup")
    if task_type in {"knowledge_research", "youtube_content_extraction", "web_content_extraction"}:
        partial.add("deep_research_orchestration")

    browser_relevant = bool(
        required_capabilities.intersection({"browser_navigation", "ui_interaction"})
        or task_type in {"youtube_content_extraction", "multi_stage_web_task", "ui_navigation"}
        or site_kind in {"youtube", "x", "linkedin", "outlook", "booking"}
    )
    if browser_relevant:
        partial.add("browser_workflow_orchestration")

    tool_states = {
        str(item.tool): str(item.state).strip().lower()
        for item in active_tools
    }
    if tool_states.get("browser_workflow_plan") == "blocked":
        partial.discard("browser_workflow_orchestration")
        blocked.add("browser_workflow_orchestration")
    if runtime_constraints.budget_state in {"hard_limit", "blocked"}:
        blocked.add("heavy_research_delegation")
    if runtime_constraints.autonomy_hold:
        blocked.add("unattended_background_autonomy")
    if runtime_constraints.release_blocked:
        blocked.add("release_path_execution")

    return (
        tuple(sorted(current)),
        tuple(sorted(partial)),
        tuple(sorted(planned)),
        tuple(sorted(blocked)),
    )


def _derive_confidence_bounds(
    runtime_constraints: MetaRuntimeConstraints,
    *,
    blocked_capabilities: Tuple[str, ...],
) -> Tuple[MetaConfidenceBound, ...]:
    bounds = [
        MetaConfidenceBound(
            area="current_capabilities",
            level="current_only",
            reason="Nur runtime- und testgestuetzte Faehigkeiten als aktuell verfuegbar darstellen.",
        ),
        MetaConfidenceBound(
            area="partial_capabilities",
            level="partial_with_caveats",
            reason="Teilfaehige Pfade brauchen Hinweise auf Site-, Kontext- oder Runtime-Abhaengigkeiten.",
        ),
        MetaConfidenceBound(
            area="planned_capabilities",
            level="planned_not_current",
            reason="Vorbereitete oder roadmap-geplante Faehigkeiten duerfen nicht als aktiv behauptet werden.",
        ),
        MetaConfidenceBound(
            area="autonomy",
            level="bounded",
            reason="Meta arbeitet unter Runtime-Guards, Handoffs und konservativer Orchestrierung.",
        ),
    ]
    if blocked_capabilities:
        bounds.append(
            MetaConfidenceBound(
                area="blocked_capabilities",
                level="blocked_now",
                reason="Aktuelle Guards oder Runtime-Sperren blockieren einzelne Faehigkeiten im Moment.",
            )
        )
    if runtime_constraints.autonomy_hold:
        bounds.append(
            MetaConfidenceBound(
                area="autonomy_hold",
                level="blocked_now",
                reason="Autonomy-Hold erlaubt derzeit keine ungebremsten autonomen Fortschreibungen.",
            )
        )
    return tuple(bounds)


def _derive_autonomy_limits(
    runtime_constraints: MetaRuntimeConstraints,
    *,
    structured_handoff_required: bool,
    blocked_capabilities: Tuple[str, ...],
) -> Tuple[MetaAutonomyLimit, ...]:
    limits = [
        MetaAutonomyLimit(
            limit="bounded_replanning_only",
            state="active",
            reason="Meta plant konservativ nach und ersetzt keine ungebremste Endlosschleife.",
        ),
        MetaAutonomyLimit(
            limit="approval_gate_not_fully_active",
            state="active",
            reason="Sensitive Approval-/Consent-Workflows werden erst in spaeteren Phase-D-Bloecken voll ausgebaut.",
        ),
        MetaAutonomyLimit(
            limit="user_mediated_auth_required",
            state="active",
            reason="Login-, 2FA- und Challenge-Pfade brauchen weiterhin Nutzerfreigabe oder Nutzeruebernahme.",
        ),
    ]
    if structured_handoff_required:
        limits.append(
            MetaAutonomyLimit(
                limit="specialist_handoff_required",
                state="active",
                reason="Mehrstufige Aufgaben muessen ueber spezialisierte Agentenketten statt reine Meta-Ausfuehrung laufen.",
            )
        )
    if runtime_constraints.resource_guard_state not in {"", "inactive", "none", "unknown"}:
        limits.append(
            MetaAutonomyLimit(
                limit="runtime_resource_guard",
                state="active",
                reason="Ressourcenschutz kann schwere oder browserlastige Schritte konservativer machen.",
            )
        )
    if runtime_constraints.autonomy_hold:
        limits.append(
            MetaAutonomyLimit(
                limit="autonomy_hold",
                state="blocked",
                reason="Runtime-Guard hat autonome Weiterlaeufe aktuell eingefroren.",
            )
        )
    for capability in blocked_capabilities:
        limits.append(
            MetaAutonomyLimit(
                limit=f"{capability}_blocked",
                state="blocked",
                reason="Diese Faehigkeit ist aktuell durch Runtime-Limits oder Guards nicht frei verfuegbar.",
            )
        )
    return tuple(limits)


def build_meta_self_state(
    classification: Dict[str, Any],
    learning_snapshot: Dict[str, Any] | None = None,
    runtime_constraints: Dict[str, Any] | MetaRuntimeConstraints | None = None,
) -> Dict[str, Any]:
    """Erzeugt einen kompakten, maschinenlesbaren Self-State fuer Meta."""
    chain = _as_list(classification.get("recommended_agent_chain") or [])
    specialists = tuple(agent for agent in chain if agent != "meta")
    runtime_constraints = _coerce_runtime_constraints(runtime_constraints)
    active_tools = _derive_active_tools(classification, runtime_constraints)
    current_capabilities, partial_capabilities, planned_capabilities, blocked_capabilities = _derive_capability_sets(
        classification,
        runtime_constraints,
        active_tools,
    )
    state = MetaSelfState(
        identity="Timus",
        orchestration_role="workflow_orchestrator",
        strategy_posture=str((learning_snapshot or {}).get("posture") or "neutral"),
        preferred_entry_agent=str(classification.get("recommended_entry_agent") or "meta"),
        task_type=str(classification.get("task_type") or "single_lane"),
        site_kind=str(classification.get("site_kind") or ""),
        available_specialists=specialists,
        required_capabilities=tuple(_as_list(classification.get("required_capabilities") or [])),
        current_capabilities=current_capabilities,
        partial_capabilities=partial_capabilities,
        planned_capabilities=planned_capabilities,
        blocked_capabilities=blocked_capabilities,
        confidence_bounds=_derive_confidence_bounds(
            runtime_constraints,
            blocked_capabilities=blocked_capabilities,
        ),
        autonomy_limits=_derive_autonomy_limits(
            runtime_constraints,
            structured_handoff_required=bool(classification.get("needs_structured_handoff")),
            blocked_capabilities=blocked_capabilities,
        ),
        active_tools=active_tools,
        known_limits=_derive_known_limits(classification, learning_snapshot, runtime_constraints),
        active_risks=_derive_risks(classification, learning_snapshot, runtime_constraints),
        runtime_constraints=runtime_constraints,
        structured_handoff_required=bool(classification.get("needs_structured_handoff")),
    )
    return state.to_dict()
