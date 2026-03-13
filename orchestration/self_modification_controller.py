from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Sequence


@dataclass(frozen=True)
class AutonomousSelfModificationCandidate:
    source_kind: str
    source_id: str
    file_path: str
    change_type: str
    change_description: str
    priority: int
    confidence: float
    severity: str
    target: str = ""


@dataclass(frozen=True)
class SelfModificationControllerDecision:
    state: str
    allow_autonomous_apply: bool
    max_apply_count: int
    reasons: tuple[str, ...]


def _normalize_text(value: str) -> str:
    return " ".join(str(value or "").strip().lower().split())


def _severity_priority(value: str) -> int:
    normalized = _normalize_text(value)
    if normalized == "high":
        return 100
    if normalized == "medium":
        return 70
    return 40


def _routing_candidate(suggestion: dict) -> AutonomousSelfModificationCandidate | None:
    target = str(suggestion.get("target") or "").strip().lower()
    if target not in {"meta", "visual", "research", "document", "communication", "system", "shell"}:
        return None
    suggestion_text = str(suggestion.get("suggestion") or "")
    finding = str(suggestion.get("finding") or "")
    combined = _normalize_text(f"{suggestion_text} {finding}")
    use_prompt = "prompt" in combined
    file_path = "agent/prompts.py" if use_prompt else "orchestration/orchestration_policy.py"
    change_type = "prompt_policy" if use_prompt else "orchestration_policy"
    focus = "Prompt-Hinweise" if use_prompt else "Routing-Heuristik"
    change_description = (
        f"Autonomer Low-Risk-Fix aus Self-Improvement Suggestion #{suggestion.get('id')}: "
        f"Verbessere {focus} fuer Agent '{target}' auf Basis von '{finding}'. "
        f"Halte die Aenderung minimal, aendere keine gesperrten Dateien und "
        f"ergaenze oder aktualisiere passende Tests nur im erlaubten Umfang."
    )
    return AutonomousSelfModificationCandidate(
        source_kind="improvement_suggestion",
        source_id=str(suggestion.get("id") or ""),
        file_path=file_path,
        change_type=change_type,
        change_description=change_description,
        priority=_severity_priority(str(suggestion.get("severity") or "medium")),
        confidence=float(suggestion.get("confidence", 0.0) or 0.0),
        severity=str(suggestion.get("severity") or "medium"),
        target=target,
    )


def _browser_workflow_candidate(suggestion: dict) -> AutonomousSelfModificationCandidate | None:
    target = _normalize_text(str(suggestion.get("target") or ""))
    text = _normalize_text(f"{suggestion.get('target', '')} {suggestion.get('finding', '')} {suggestion.get('suggestion', '')}")
    browserish = {
        "open_url",
        "scan_ui_elements",
        "hybrid_browser_navigate",
        "click_element",
        "type_text",
    }
    if target not in browserish and not any(keyword in text for keyword in ("browser", "visual", "workflow", "selector", "click", "navigate")):
        return None
    change_description = (
        f"Autonomer Low-Risk-Fix aus Self-Improvement Suggestion #{suggestion.get('id')}: "
        f"Verbessere Browser-Workflow-Planung oder Evaluationslogik fuer '{suggestion.get('target', '')}' "
        f"auf Basis von '{suggestion.get('finding', '')}'. "
        f"Halte die Anpassung klein und beschraenke sie auf erlaubte Browser-Workflow-Dateien."
    )
    return AutonomousSelfModificationCandidate(
        source_kind="improvement_suggestion",
        source_id=str(suggestion.get("id") or ""),
        file_path="orchestration/browser_workflow_plan.py",
        change_type="orchestration_policy",
        change_description=change_description,
        priority=max(30, _severity_priority(str(suggestion.get("severity") or "low")) - 10),
        confidence=float(suggestion.get("confidence", 0.0) or 0.0),
        severity=str(suggestion.get("severity") or "low"),
        target=str(suggestion.get("target") or ""),
    )


def build_autonomous_self_modification_candidates(
    suggestions: Sequence[dict],
    *,
    reserved_source_ids: Iterable[str] = (),
) -> list[AutonomousSelfModificationCandidate]:
    reserved = {str(item).strip() for item in reserved_source_ids if str(item).strip()}
    candidates: list[AutonomousSelfModificationCandidate] = []
    seen_sources: set[str] = set()

    for suggestion in suggestions:
        if str(suggestion.get("type") or "") not in {"routing", "tool"}:
            continue
        source_id = str(suggestion.get("id") or "").strip()
        if not source_id or source_id in reserved or source_id in seen_sources:
            continue

        candidate: AutonomousSelfModificationCandidate | None = None
        if str(suggestion.get("type") or "") == "routing":
            candidate = _routing_candidate(suggestion)
        elif str(suggestion.get("type") or "") == "tool":
            candidate = _browser_workflow_candidate(suggestion)

        if candidate is None:
            continue
        seen_sources.add(source_id)
        candidates.append(candidate)

    return sorted(
        candidates,
        key=lambda item: (
            -int(item.priority),
            -float(item.confidence),
            str(item.source_id),
        ),
    )


def evaluate_self_modification_controller(
    *,
    stability_gate_state: str,
    ops_gate_state: str,
    e2e_gate_state: str,
    strict_force_off: bool,
    pending_approvals: int,
    rollback_count_recent: int,
    regression_count_recent: int,
    configured_max_per_cycle: int,
    max_pending_approvals: int,
) -> SelfModificationControllerDecision:
    reasons: list[str] = []
    state = "pass"
    max_apply = max(1, int(configured_max_per_cycle))
    soft_pressure = False

    normalized_stability = _normalize_text(stability_gate_state) or "unknown"
    normalized_ops = _normalize_text(ops_gate_state) or "unknown"
    normalized_e2e = _normalize_text(e2e_gate_state) or "unknown"

    if strict_force_off:
        return SelfModificationControllerDecision(
            state="blocked",
            allow_autonomous_apply=False,
            max_apply_count=0,
            reasons=("strict_force_off",),
        )

    if normalized_stability == "blocked":
        return SelfModificationControllerDecision(
            state="blocked",
            allow_autonomous_apply=False,
            max_apply_count=0,
            reasons=("stability_gate_blocked",),
        )

    if normalized_ops == "blocked":
        return SelfModificationControllerDecision(
            state="blocked",
            allow_autonomous_apply=False,
            max_apply_count=0,
            reasons=("ops_gate_blocked",),
        )

    if normalized_e2e == "blocked":
        return SelfModificationControllerDecision(
            state="blocked",
            allow_autonomous_apply=False,
            max_apply_count=0,
            reasons=("e2e_gate_blocked",),
        )

    if pending_approvals >= max(1, int(max_pending_approvals)):
        return SelfModificationControllerDecision(
            state="blocked",
            allow_autonomous_apply=False,
            max_apply_count=0,
            reasons=(f"pending_approvals>={max_pending_approvals}",),
        )

    if rollback_count_recent >= 3 or regression_count_recent >= 2:
        return SelfModificationControllerDecision(
            state="blocked",
            allow_autonomous_apply=False,
            max_apply_count=0,
            reasons=("recent_rollbacks_or_regressions",),
        )

    if normalized_stability == "warn":
        state = "warn"
        reasons.append("stability_gate_warn")
    if normalized_ops == "warn":
        state = "warn"
        reasons.append("ops_gate_warn")
    if normalized_e2e == "warn":
        state = "warn"
        reasons.append("e2e_gate_warn")
    if pending_approvals > 0:
        state = "warn"
        soft_pressure = True
        reasons.append("pending_approvals_present")
    if rollback_count_recent > 0 or regression_count_recent > 0:
        state = "warn"
        soft_pressure = True
        reasons.append("recent_rollbacks_or_regressions_warn")

    if state == "warn":
        max_apply = min(max_apply, 1 if soft_pressure else 2)

    return SelfModificationControllerDecision(
        state=state,
        allow_autonomous_apply=True,
        max_apply_count=max_apply,
        reasons=tuple(reasons),
    )
