"""Z1 task decomposition contract for general multi-step planning."""

from __future__ import annotations

import json
import re
from typing import Any, Iterable, Mapping


TASK_DECOMPOSITION_SCHEMA_VERSION = 1
_VALID_INTENT_FAMILIES = {
    "single_step",
    "research",
    "plan_only",
    "build_setup",
    "execute_multistep",
}
_VALID_GOAL_SATISFACTION_MODES = {
    "answer_or_artifact_ready",
    "plan_ready",
    "goal_satisfied",
}

_RESEARCH_MARKERS = (
    "recherchi",
    "recherche",
    "suche nach",
    "finde heraus",
    "analysier",
    "quellen",
    "studien",
    "vergleich",
    "fakten",
)
_BUILD_SETUP_MARKERS = (
    "einricht",
    "installier",
    "konfig",
    "setup",
    "anbinden",
    "anbind",
    "integration",
    "integrier",
    "verbinde",
    "deploy",
    "implement",
    "webhook",
    "aufsetzen",
)
_PLAN_MARKERS = (
    "plan",
    "vorgehen",
    "roadmap",
    "strategie",
    "schritte",
    "ablauf",
    "konzept",
)
_DELIVERY_MARKERS = (
    "bericht",
    "report",
    "pdf",
    "dokument",
    "zusammenfassung",
    "tabelle",
    "erstelle",
    "schreibe",
    "generiere",
    "speichere",
    "schicke",
    "sende",
    "exportiere",
)
_MULTISTEP_MARKERS = (
    "danach",
    "und dann",
    "anschließend",
    "anschliessend",
    "im anschluss",
    "zuerst",
    "anschließend",
    "abschließend",
    "abschliessend",
)
_EXPLICIT_SHELL_MARKERS = (
    "pip install",
    "apt install",
    "apt-get install",
    "brew install",
    "systemctl",
    "sudo ",
    "bash ",
    "sh ",
    "terminal",
    "konsole",
    "fuehre aus",
    "führe aus",
    "run command",
    "cmd ",
)


def _clean_text(value: Any, *, limit: int = 220) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if len(text) <= limit:
        return text
    clipped = text[:limit].rsplit(" ", 1)[0].strip()
    return f"{clipped or text[:limit]}..."


def _normalize_text_list(
    values: Iterable[Any] | None,
    *,
    limit_items: int = 8,
    limit_chars: int = 180,
) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for value in values or ():
        text = _clean_text(value, limit=limit_chars)
        if not text:
            continue
        lowered = text.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        normalized.append(text)
        if len(normalized) >= limit_items:
            break
    return normalized


def _normalize_int(value: Any, *, default: int = 0, minimum: int = 0) -> int:
    try:
        return max(minimum, int(value))
    except (TypeError, ValueError):
        return max(minimum, int(default))


def _normalize_yes_no(value: Any) -> str:
    text = str(value or "").strip().lower()
    if text in {"1", "true", "yes", "ja", "on"}:
        return "yes"
    return "no"


def _normalize_constraints(value: Mapping[str, Any] | None) -> dict[str, list[str]]:
    payload = dict(value or {})
    return {
        "hard": _normalize_text_list(payload.get("hard"), limit_items=8),
        "soft": _normalize_text_list(payload.get("soft"), limit_items=8),
        "forbidden_actions": _normalize_text_list(
            payload.get("forbidden_actions"),
            limit_items=8,
        ),
    }


def _normalize_subtasks(value: Iterable[Any] | None) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for raw_item in value or ():
        item = dict(raw_item or {}) if isinstance(raw_item, Mapping) else {}
        subtask_id = _clean_text(item.get("id"), limit=48).lower().replace(" ", "_")
        title = _clean_text(item.get("title"), limit=140)
        if not subtask_id or not title or subtask_id in seen_ids:
            continue
        seen_ids.add(subtask_id)
        normalized.append(
            {
                "id": subtask_id,
                "title": title,
                "kind": _clean_text(item.get("kind"), limit=48).lower() or "generic",
                "status": _clean_text(item.get("status"), limit=32).lower() or "pending",
                "depends_on": _normalize_text_list(
                    item.get("depends_on"),
                    limit_items=6,
                    limit_chars=48,
                ),
                "optional": bool(item.get("optional")),
                "completion_signals": _normalize_text_list(
                    item.get("completion_signals"),
                    limit_items=6,
                    limit_chars=96,
                ),
            }
        )
        if len(normalized) >= 6:
            break
    return normalized


def _normalize_metadata(value: Mapping[str, Any] | None) -> dict[str, Any]:
    payload = dict(value or {})
    return {
        "task_type": _clean_text(payload.get("task_type"), limit=64),
        "site_kind": _clean_text(payload.get("site_kind"), limit=64),
        "response_mode": _clean_text(payload.get("response_mode"), limit=64),
        "frame_kind": _clean_text(payload.get("frame_kind"), limit=64),
        "frame_task_domain": _clean_text(payload.get("frame_task_domain"), limit=64),
        "frame_execution_mode": _clean_text(payload.get("frame_execution_mode"), limit=64),
        "action_count": _normalize_int(payload.get("action_count"), default=0),
        "capability_count": _normalize_int(payload.get("capability_count"), default=0),
        "route_to_meta": _normalize_yes_no(payload.get("route_to_meta")),
        "explicit_shell_execution": _normalize_yes_no(payload.get("explicit_shell_execution")),
    }


def _normalize_task_decomposition(
    *,
    request_id: Any = "",
    source_query: Any = "",
    intent_family: Any = "",
    goal: Any = "",
    constraints: Mapping[str, Any] | None = None,
    subtasks: Iterable[Any] | None = None,
    completion_signals: Iterable[Any] | None = None,
    goal_satisfaction_mode: Any = "",
    planning_needed: Any = False,
    planning_reason: Any = "",
    metadata: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    normalized_intent_family = _clean_text(intent_family, limit=48).lower() or "single_step"
    if normalized_intent_family not in _VALID_INTENT_FAMILIES:
        normalized_intent_family = "single_step"

    normalized_goal_mode = (
        _clean_text(goal_satisfaction_mode, limit=48).lower() or "answer_or_artifact_ready"
    )
    if normalized_goal_mode not in _VALID_GOAL_SATISFACTION_MODES:
        normalized_goal_mode = "answer_or_artifact_ready"

    normalized_subtasks = _normalize_subtasks(subtasks)
    normalized_completion_signals = _normalize_text_list(
        completion_signals,
        limit_items=8,
        limit_chars=96,
    )
    if not normalized_completion_signals and normalized_subtasks:
        normalized_completion_signals = list(normalized_subtasks[-1]["completion_signals"])
    if not normalized_completion_signals:
        normalized_completion_signals = ["goal_satisfied"]

    return {
        "schema_version": TASK_DECOMPOSITION_SCHEMA_VERSION,
        "request_id": _clean_text(request_id, limit=64),
        "source_query": _clean_text(source_query, limit=400),
        "intent_family": normalized_intent_family,
        "goal": _clean_text(goal or source_query, limit=280),
        "constraints": _normalize_constraints(constraints),
        "subtasks": normalized_subtasks,
        "completion_signals": normalized_completion_signals,
        "goal_satisfaction_mode": normalized_goal_mode,
        "planning_needed": bool(planning_needed),
        "planning_reason": _clean_text(planning_reason, limit=180),
        "metadata": _normalize_metadata(metadata),
    }


def _contains_any(text: str, markers: Iterable[str]) -> bool:
    lowered = str(text or "").lower()
    return any(marker in lowered for marker in markers)


def _contains_phrase(text: str, markers: Iterable[str]) -> bool:
    lowered = str(text or "").lower()
    for marker in markers:
        normalized = str(marker or "").strip().lower()
        if not normalized:
            continue
        if " " in normalized:
            if normalized in lowered:
                return True
            continue
        if re.search(rf"\b{re.escape(normalized)}\b", lowered):
            return True
    return False


def _derive_goal(source_query: str, policy: Mapping[str, Any]) -> str:
    goal_spec = dict(policy.get("goal_spec") or {})
    for key in ("summary", "goal", "objective"):
        candidate = _clean_text(goal_spec.get(key), limit=280)
        if candidate:
            return candidate
    return _clean_text(source_query, limit=280)


def _derive_constraints(
    *,
    policy: Mapping[str, Any],
    planning_needed: bool,
    explicit_shell_execution: bool,
) -> dict[str, list[str]]:
    goal_spec = dict(policy.get("goal_spec") or {})
    hard: list[str] = []
    soft: list[str] = []
    forbidden_actions: list[str] = []

    freshness = _clean_text(goal_spec.get("freshness"), limit=48)
    evidence_level = _clean_text(goal_spec.get("evidence_level"), limit=48)
    output_mode = _clean_text(goal_spec.get("output_mode"), limit=48)
    if freshness:
        hard.append(f"freshness={freshness}")
    if evidence_level:
        hard.append(f"evidence_level={evidence_level}")
    if output_mode:
        soft.append(f"output_mode={output_mode}")
    if planning_needed:
        soft.append("plane_vor_der_ausfuehrung")
    if explicit_shell_execution:
        soft.append("expliziter_shell_pfand_vorhanden")
    else:
        forbidden_actions.append("unguardierte_shell_ausfuehrung")

    return {
        "hard": hard,
        "soft": soft,
        "forbidden_actions": forbidden_actions,
    }


def _build_research_subtasks(*, deliver_artifact: bool) -> list[dict[str, Any]]:
    subtasks = [
        {
            "id": "gather_evidence",
            "title": "Relevante Informationen und Quellen sammeln",
            "kind": "research",
            "status": "pending",
            "depends_on": [],
            "optional": False,
            "completion_signals": ["sources_collected", "relevant_facts_verified"],
        },
        {
            "id": "synthesize_answer",
            "title": "Ergebnisse zu einer belastbaren Antwort verdichten",
            "kind": "synthesis",
            "status": "pending",
            "depends_on": ["gather_evidence"],
            "optional": False,
            "completion_signals": ["answer_drafted", "key_points_covered"],
        },
    ]
    if deliver_artifact:
        subtasks.append(
            {
                "id": "deliver_artifact",
                "title": "Ausgabe im angeforderten Format liefern",
                "kind": "delivery",
                "status": "pending",
                "depends_on": ["synthesize_answer"],
                "optional": False,
                "completion_signals": ["artifact_ready", "answer_delivered"],
            }
        )
    return subtasks


def _build_plan_only_subtasks() -> list[dict[str, Any]]:
    return [
        {
            "id": "frame_goal",
            "title": "Ziel, Randbedingungen und Erfolgskriterien festziehen",
            "kind": "analysis",
            "status": "pending",
            "depends_on": [],
            "optional": False,
            "completion_signals": ["goal_framed", "constraints_identified"],
        },
        {
            "id": "draft_plan",
            "title": "Schrittfolge und Alternativen ausarbeiten",
            "kind": "plan",
            "status": "pending",
            "depends_on": ["frame_goal"],
            "optional": False,
            "completion_signals": ["plan_drafted", "major_steps_ordered"],
        },
        {
            "id": "define_verification",
            "title": "Pruefpfad und Abschlusskriterien festlegen",
            "kind": "verification",
            "status": "pending",
            "depends_on": ["draft_plan"],
            "optional": False,
            "completion_signals": ["verification_defined", "plan_ready"],
        },
    ]


def _build_setup_subtasks(*, deliver_artifact: bool) -> list[dict[str, Any]]:
    subtasks = [
        {
            "id": "analyze_target",
            "title": "Zielsystem, Umfeld und Randbedingungen klaeren",
            "kind": "analysis",
            "status": "pending",
            "depends_on": [],
            "optional": False,
            "completion_signals": ["target_understood", "constraints_identified"],
        },
        {
            "id": "prepare_solution",
            "title": "Passende Loesung und konkrete Schritte festlegen",
            "kind": "plan",
            "status": "pending",
            "depends_on": ["analyze_target"],
            "optional": False,
            "completion_signals": ["solution_selected", "execution_steps_defined"],
        },
        {
            "id": "execute_setup",
            "title": "Setup oder Integration umsetzen",
            "kind": "setup",
            "status": "pending",
            "depends_on": ["prepare_solution"],
            "optional": False,
            "completion_signals": ["changes_applied", "setup_completed"],
        },
        {
            "id": "verify_setup",
            "title": "Ergebnis pruefen und Zielzustand bestaetigen",
            "kind": "verification",
            "status": "pending",
            "depends_on": ["execute_setup"],
            "optional": False,
            "completion_signals": ["verification_passed", "goal_satisfied"],
        },
    ]
    if deliver_artifact:
        subtasks.append(
            {
                "id": "deliver_result",
                "title": "Ergebnis und relevante Hinweise dokumentieren",
                "kind": "delivery",
                "status": "pending",
                "depends_on": ["verify_setup"],
                "optional": False,
                "completion_signals": ["artifact_ready", "answer_delivered"],
            }
        )
    return subtasks


def _build_execute_multistep_subtasks(*, has_research: bool, deliver_artifact: bool) -> list[dict[str, Any]]:
    subtasks: list[dict[str, Any]] = []
    if has_research:
        subtasks.append(
            {
                "id": "gather_context",
                "title": "Noetigen Kontext und Fakten sammeln",
                "kind": "research",
                "status": "pending",
                "depends_on": [],
                "optional": False,
                "completion_signals": ["context_collected", "facts_verified"],
            }
        )
        previous_step = "gather_context"
    else:
        subtasks.append(
            {
                "id": "frame_steps",
                "title": "Schrittfolge fuer die Ausfuehrung strukturieren",
                "kind": "plan",
                "status": "pending",
                "depends_on": [],
                "optional": False,
                "completion_signals": ["steps_defined", "execution_ready"],
            }
        )
        previous_step = "frame_steps"

    subtasks.append(
        {
            "id": "execute_primary_work",
            "title": "Primare Arbeit in kontrollierten Teilaufgaben umsetzen",
            "kind": "execution",
            "status": "pending",
            "depends_on": [previous_step],
            "optional": False,
            "completion_signals": ["primary_work_done", "result_ready"],
        }
    )
    previous_step = "execute_primary_work"

    subtasks.append(
        {
            "id": "verify_result",
            "title": "Zwischen- oder Endergebnis pruefen",
            "kind": "verification",
            "status": "pending",
            "depends_on": [previous_step],
            "optional": False,
            "completion_signals": ["verification_passed", "goal_satisfied"],
        }
    )
    previous_step = "verify_result"

    if deliver_artifact:
        subtasks.append(
            {
                "id": "deliver_result",
                "title": "Ergebnis im angeforderten Format liefern",
                "kind": "delivery",
                "status": "pending",
                "depends_on": [previous_step],
                "optional": False,
                "completion_signals": ["artifact_ready", "answer_delivered"],
            }
        )

    return subtasks


def build_task_decomposition(
    *,
    source_query: Any,
    orchestration_policy: Mapping[str, Any] | None = None,
    request_id: Any = "",
) -> dict[str, Any]:
    """Builds the canonical Z1 task decomposition contract."""

    query = _clean_text(source_query, limit=400)
    lowered_query = query.lower()
    policy = dict(orchestration_policy or {})

    task_type = _clean_text(policy.get("task_type"), limit=64)
    site_kind = _clean_text(policy.get("site_kind"), limit=64)
    response_mode = _clean_text(policy.get("response_mode"), limit=64)
    frame_kind = _clean_text(policy.get("frame_kind"), limit=64).lower()
    frame_task_domain = _clean_text(policy.get("frame_task_domain"), limit=64).lower()
    frame_execution_mode = _clean_text(policy.get("frame_execution_mode"), limit=64).lower()
    action_count = _normalize_int(policy.get("action_count"), default=0)
    capability_count = _normalize_int(policy.get("capability_count"), default=0)
    recommended_chain = list(policy.get("recommended_agent_chain") or [])
    chain_length = len(recommended_chain)
    route_to_meta = bool(policy.get("route_to_meta"))

    has_research = _contains_any(lowered_query, _RESEARCH_MARKERS) or "research" in task_type
    has_build_setup = _contains_any(lowered_query, _BUILD_SETUP_MARKERS)
    has_plan = _contains_any(lowered_query, _PLAN_MARKERS)
    has_deliver = _contains_phrase(lowered_query, _DELIVERY_MARKERS) or response_mode in {
        "report",
        "artifact",
        "table",
        "document",
    }
    explicit_shell_execution = _contains_phrase(lowered_query, _EXPLICIT_SHELL_MARKERS)
    has_multistep_signal = (
        _contains_phrase(lowered_query, _MULTISTEP_MARKERS)
        or action_count >= 2
        or chain_length >= 2
        or capability_count >= 3
    )

    intent_family = "single_step"
    if frame_execution_mode == "answer_directly":
        intent_family = "single_step"
    elif frame_task_domain == "setup_build":
        intent_family = "build_setup"
    elif frame_task_domain == "migration_work":
        intent_family = "research"
    elif has_build_setup:
        intent_family = "build_setup"
    elif has_plan and not has_deliver and not has_research:
        intent_family = "plan_only"
    elif has_research and not has_multistep_signal and not has_deliver:
        intent_family = "research"
    elif (
        (has_research and (has_multistep_signal or has_deliver))
        or (has_deliver and has_multistep_signal)
        or (route_to_meta and has_multistep_signal)
    ):
        intent_family = "execute_multistep"

    planning_needed = (
        intent_family in {"build_setup", "plan_only", "execute_multistep"}
        and not explicit_shell_execution
    )
    if frame_execution_mode == "answer_directly":
        planning_needed = False
    if frame_execution_mode == "answer_directly":
        planning_reason = "frame_answer_directly"
    elif intent_family == "plan_only":
        planning_reason = "user_explicitly_requested_a_plan"
    elif intent_family == "build_setup":
        planning_reason = "setup_or_build_request_requires_controlled_subtasks"
    elif intent_family == "execute_multistep":
        planning_reason = "multi_step_delivery_or_execution_request_detected"
    else:
        planning_reason = ""

    if frame_execution_mode == "answer_directly":
        goal_satisfaction_mode = "answer_or_artifact_ready"
        subtasks = [
            {
                "id": "respond",
                "title": "Anfrage direkt bearbeiten",
                "kind": "response",
                "status": "pending",
                "depends_on": [],
                "optional": False,
                "completion_signals": ["answer_delivered"],
            }
        ]
    elif intent_family == "plan_only":
        goal_satisfaction_mode = "plan_ready"
        subtasks = _build_plan_only_subtasks()
    elif intent_family == "build_setup":
        goal_satisfaction_mode = "goal_satisfied"
        subtasks = _build_setup_subtasks(deliver_artifact=has_deliver)
    elif intent_family == "execute_multistep":
        goal_satisfaction_mode = "goal_satisfied"
        subtasks = _build_execute_multistep_subtasks(
            has_research=has_research,
            deliver_artifact=has_deliver,
        )
    elif intent_family == "research":
        goal_satisfaction_mode = "answer_or_artifact_ready"
        subtasks = _build_research_subtasks(deliver_artifact=has_deliver)
    else:
        goal_satisfaction_mode = "answer_or_artifact_ready"
        subtasks = [
            {
                "id": "respond",
                "title": "Anfrage direkt bearbeiten",
                "kind": "response",
                "status": "pending",
                "depends_on": [],
                "optional": False,
                "completion_signals": ["answer_delivered"],
            }
        ]

    return _normalize_task_decomposition(
        request_id=request_id,
        source_query=query,
        intent_family=intent_family,
        goal=_derive_goal(query, policy),
        constraints=_derive_constraints(
            policy=policy,
            planning_needed=planning_needed,
            explicit_shell_execution=explicit_shell_execution,
        ),
        subtasks=subtasks,
        completion_signals=subtasks[-1]["completion_signals"] if subtasks else ["goal_satisfied"],
        goal_satisfaction_mode=goal_satisfaction_mode,
        planning_needed=planning_needed,
        planning_reason=planning_reason,
        metadata={
            "task_type": task_type,
            "site_kind": site_kind,
            "response_mode": response_mode,
            "frame_kind": frame_kind,
            "frame_task_domain": frame_task_domain,
            "frame_execution_mode": frame_execution_mode,
            "action_count": action_count,
            "capability_count": capability_count,
            "route_to_meta": route_to_meta,
            "explicit_shell_execution": explicit_shell_execution,
        },
    )


def parse_task_decomposition(raw: Any) -> dict[str, Any]:
    if isinstance(raw, Mapping):
        loaded = dict(raw)
    elif isinstance(raw, str):
        text = str(raw).strip()
        if not text:
            return {}
        try:
            decoded = json.loads(text)
        except json.JSONDecodeError:
            return {}
        if not isinstance(decoded, Mapping):
            return {}
        loaded = dict(decoded)
    else:
        return {}

    return _normalize_task_decomposition(
        request_id=loaded.get("request_id"),
        source_query=loaded.get("source_query"),
        intent_family=loaded.get("intent_family"),
        goal=loaded.get("goal"),
        constraints=loaded.get("constraints"),
        subtasks=loaded.get("subtasks"),
        completion_signals=loaded.get("completion_signals"),
        goal_satisfaction_mode=loaded.get("goal_satisfaction_mode"),
        planning_needed=loaded.get("planning_needed"),
        planning_reason=loaded.get("planning_reason"),
        metadata=loaded.get("metadata"),
    )
