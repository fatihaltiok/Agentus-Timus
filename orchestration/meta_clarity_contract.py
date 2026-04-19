"""Expliziter Klarheitsvertrag fuer den Meta-Orchestrator."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Dict, Mapping, Tuple


_DIRECT_ANSWER_REQUEST_KINDS = {
    "direct_recommendation",
    "state_summary",
    "historical_recall",
    "self_model_status",
}

_DOC_STATUS_PATTERNS = (
    "docs/",
    "changelog",
    "phase_",
    "phase ",
    "plan.md",
    "naechstes ansteht",
    "nächstes ansteht",
    "next step",
    "wo stehen wir",
    "status",
)
_LOCATION_ROUTE_PATTERNS = (
    "route",
    "weg nach",
    "anfahrt",
    "maps",
    "google maps",
    "travel_mode",
    "destination_query",
    "mit dem auto",
    "driving",
)


@dataclass(frozen=True)
class MetaClarityContract:
    schema_version: int
    primary_objective: str
    request_kind: str
    answer_obligation: str
    completion_condition: str
    direct_answer_required: bool
    allowed_context_slots: Tuple[str, ...]
    forbidden_context_slots: Tuple[str, ...]
    allowed_working_memory_sections: Tuple[str, ...]
    max_related_memories: int
    max_recent_events: int
    delegation_mode: str
    max_delegate_calls: int
    allowed_delegate_agents: Tuple[str, ...]
    force_answer_after_delegate_budget: bool
    rationale: str

    def to_dict(self) -> Dict[str, Any]:
        payload = asdict(self)
        for key, value in tuple(payload.items()):
            if isinstance(value, tuple):
                payload[key] = list(value)
        return payload


def _clean_text(value: Any, *, limit: int = 240) -> str:
    text = " ".join(str(value or "").strip().split())
    if len(text) <= limit:
        return text
    clipped = text[:limit].rsplit(" ", 1)[0].strip()
    return f"{clipped or text[:limit]}..."


def parse_meta_clarity_contract(value: Any) -> Dict[str, Any]:
    if not isinstance(value, Mapping):
        return {}

    max_related_raw = value.get("max_related_memories", -1)
    max_recent_raw = value.get("max_recent_events", -1)

    payload = {
        "schema_version": int(value.get("schema_version") or 1),
        "primary_objective": _clean_text(value.get("primary_objective"), limit=320),
        "request_kind": _clean_text(value.get("request_kind"), limit=64).lower(),
        "answer_obligation": _clean_text(value.get("answer_obligation"), limit=120),
        "completion_condition": _clean_text(value.get("completion_condition"), limit=120),
        "direct_answer_required": bool(value.get("direct_answer_required")),
        "delegation_mode": _clean_text(value.get("delegation_mode"), limit=64).lower(),
        "allowed_context_slots": [
            _clean_text(item, limit=64)
            for item in (value.get("allowed_context_slots") or [])
            if _clean_text(item, limit=64)
        ],
        "forbidden_context_slots": [
            _clean_text(item, limit=64)
            for item in (value.get("forbidden_context_slots") or [])
            if _clean_text(item, limit=64)
        ],
        "allowed_working_memory_sections": [
            _clean_text(item, limit=64)
            for item in (value.get("allowed_working_memory_sections") or [])
            if _clean_text(item, limit=64)
        ],
        "allowed_delegate_agents": [
            _clean_text(item, limit=64).lower()
            for item in (value.get("allowed_delegate_agents") or [])
            if _clean_text(item, limit=64)
        ],
        "max_related_memories": max(
            -1,
            -1 if max_related_raw in (None, "") else int(max_related_raw),
        ),
        "max_recent_events": max(
            -1,
            -1 if max_recent_raw in (None, "") else int(max_recent_raw),
        ),
        "max_delegate_calls": max(
            -1,
            -1 if value.get("max_delegate_calls") in (None, "") else int(value.get("max_delegate_calls")),
        ),
        "force_answer_after_delegate_budget": bool(value.get("force_answer_after_delegate_budget")),
        "rationale": _clean_text(value.get("rationale"), limit=220),
    }
    return {key: item for key, item in payload.items() if item not in ("", [], None)}


def _detect_objective_domain(text: Any) -> str:
    lowered = str(text or "").strip().lower()
    if not lowered:
        return ""
    if any(pattern in lowered for pattern in _DOC_STATUS_PATTERNS):
        return "docs_status"
    if any(pattern in lowered for pattern in _LOCATION_ROUTE_PATTERNS):
        return "location_route"
    return ""


def build_meta_clarity_contract(
    *,
    effective_query: str,
    response_mode: str,
    policy_decision: Mapping[str, Any] | None = None,
    task_type: str = "",
    goal_spec: Mapping[str, Any] | None = None,
    task_decomposition: Mapping[str, Any] | None = None,
    meta_execution_plan: Mapping[str, Any] | None = None,
) -> MetaClarityContract:
    policy = parse_meta_clarity_contract(
        {
            "request_kind": str((policy_decision or {}).get("answer_shape") or "").strip().lower(),
        }
    )
    answer_shape = str(policy.get("request_kind") or "").strip().lower()
    response_mode_clean = _clean_text(response_mode, limit=64).lower()
    policy_reason = _clean_text((policy_decision or {}).get("policy_reason"), limit=80).lower()
    decomposition = dict(task_decomposition or {})
    plan = dict(meta_execution_plan or {})
    goal = _clean_text(
        decomposition.get("goal")
        or plan.get("goal")
        or effective_query,
        limit=320,
    )
    next_step_title = _clean_text(
        plan.get("next_step_title")
        or plan.get("goal")
        or decomposition.get("planning_reason"),
        limit=160,
    )

    request_kind = "execute_task"
    answer_obligation = "decide_and_act"
    completion_condition = "next_action_selected"
    allowed_context_slots = (
        "current_query",
        "conversation_state",
        "open_loop",
        "recent_user_turn",
        "topic_memory",
        "historical_topic_memory",
        "preference_memory",
        "semantic_recall",
    )
    forbidden_context_slots: Tuple[str, ...] = ()
    allowed_working_memory_sections = ("KURZZEITKONTEXT", "LANGZEITKONTEXT", "STABILER_KONTEXT")
    max_related_memories = -1
    max_recent_events = -1
    delegation_mode = "full_orchestration"
    max_delegate_calls = -1
    allowed_delegate_agents: Tuple[str, ...] = ()
    force_answer_after_delegate_budget = False
    rationale = "Default-Orchestrierung mit vollem Kontextbudget."
    objective_domain = _detect_objective_domain(goal) or _detect_objective_domain(effective_query)

    if answer_shape == "direct_recommendation" or policy_reason == "next_step_summary_request":
        request_kind = "direct_recommendation"
        answer_obligation = "answer_now_with_single_recommendation"
        completion_condition = "next_recommended_block_or_step_named"
        allowed_context_slots = (
            "current_query",
            "conversation_state",
            "open_loop",
            "recent_user_turn",
            "historical_topic_memory",
        )
        forbidden_context_slots = (
            "assistant_fallback_context",
            "topic_memory",
            "preference_memory",
            "semantic_recall",
        )
        allowed_working_memory_sections = ("KURZZEITKONTEXT",)
        max_related_memories = 0
        max_recent_events = 4
        delegation_mode = "single_evidence_fetch"
        max_delegate_calls = 1
        force_answer_after_delegate_budget = True
        if objective_domain == "docs_status":
            allowed_delegate_agents = ("shell", "document")
        else:
            allowed_delegate_agents = ("shell", "document", "research", "system")
        rationale = "Direkte Empfehlung braucht aktuelle Frage und kurze Verlaufsanker, aber kein breites Altgedaechtnis."
    elif answer_shape == "state_summary" or policy_reason == "state_summary_request":
        request_kind = "state_summary"
        answer_obligation = "summarize_current_state_directly"
        completion_condition = "current_state_summarized"
        allowed_context_slots = (
            "current_query",
            "conversation_state",
            "open_loop",
            "recent_user_turn",
            "historical_topic_memory",
        )
        forbidden_context_slots = (
            "assistant_fallback_context",
            "preference_memory",
        )
        allowed_working_memory_sections = ("KURZZEITKONTEXT", "LANGZEITKONTEXT")
        max_related_memories = 2
        max_recent_events = 6
        delegation_mode = "single_evidence_fetch"
        max_delegate_calls = 1
        force_answer_after_delegate_budget = True
        allowed_delegate_agents = ("shell", "document", "system")
        rationale = "Statusfragen duerfen State- und Verlaufskontext sehen, aber keine irrelevanten Praeferenzpfade."
    elif answer_shape == "historical_topic_state" or policy_reason == "historical_topic_recall":
        request_kind = "historical_recall"
        answer_obligation = "answer_now_from_relevant_history"
        completion_condition = "historical_topic_recalled"
        allowed_context_slots = (
            "current_query",
            "conversation_state",
            "historical_topic_memory",
            "recent_user_turn",
        )
        forbidden_context_slots = (
            "assistant_fallback_context",
            "topic_memory",
            "preference_memory",
        )
        allowed_working_memory_sections = ("KURZZEITKONTEXT", "LANGZEITKONTEXT")
        max_related_memories = 3
        max_recent_events = 6
        delegation_mode = "direct_only"
        max_delegate_calls = 0
        rationale = "Historische Rueckfragen brauchen gezielte Verlaufsspuren, nicht breite thematische Seitenpfade."
    elif answer_shape == "self_model_status" or policy_reason == "self_model_status_request":
        request_kind = "self_model_status"
        answer_obligation = "answer_now_from_self_model_and_runtime"
        completion_condition = "self_capability_state_explained"
        allowed_context_slots = (
            "current_query",
            "conversation_state",
            "preference_memory",
            "recent_user_turn",
        )
        forbidden_context_slots = ("assistant_fallback_context",)
        allowed_working_memory_sections = ("KURZZEITKONTEXT", "STABILER_KONTEXT")
        max_related_memories = 1
        max_recent_events = 4
        delegation_mode = "single_evidence_fetch"
        max_delegate_calls = 1
        force_answer_after_delegate_budget = True
        allowed_delegate_agents = ("system", "shell")
        rationale = "Selbststatus darf Stabilkontext nutzen, aber keine thematisch fremden Langzeitpfade."
    elif response_mode_clean == "clarify_before_execute":
        request_kind = "clarify_question"
        answer_obligation = "ask_one_clarifying_question_only_if_needed"
        completion_condition = "material_ambiguity_resolved"
        allowed_context_slots = (
            "current_query",
            "conversation_state",
            "open_loop",
            "recent_user_turn",
        )
        forbidden_context_slots = (
            "assistant_fallback_context",
            "topic_memory",
            "preference_memory",
            "semantic_recall",
        )
        allowed_working_memory_sections = ("KURZZEITKONTEXT",)
        max_related_memories = 0
        max_recent_events = 4
        delegation_mode = "direct_only"
        max_delegate_calls = 0
        rationale = "Klaerfragen brauchen Klarheit ueber den aktuellen Turn, nicht semantisches Altgewicht."
    elif response_mode_clean == "resume_open_loop":
        request_kind = "resume_action"
        answer_obligation = "continue_current_plan_or_statefully_reframe"
        completion_condition = "next_plan_step_resolved"
        allowed_context_slots = (
            "current_query",
            "conversation_state",
            "open_loop",
            "recent_user_turn",
            "historical_topic_memory",
        )
        forbidden_context_slots = ("assistant_fallback_context",)
        allowed_working_memory_sections = ("KURZZEITKONTEXT", "LANGZEITKONTEXT")
        max_related_memories = 2
        max_recent_events = 8
        delegation_mode = "bounded_chain"
        max_delegate_calls = 2
        rationale = "Resume-Faelle brauchen Plananschluss, aber keine beliebigen Alt-Praeferenzen."
    elif response_mode_clean == "acknowledge_and_store":
        request_kind = "acknowledgment"
        answer_obligation = "confirm_and_store_without_menu"
        completion_condition = "preference_or_instruction_acknowledged"
        allowed_context_slots = (
            "current_query",
            "conversation_state",
            "recent_user_turn",
            "preference_memory",
        )
        forbidden_context_slots = ("assistant_fallback_context",)
        allowed_working_memory_sections = ("KURZZEITKONTEXT", "STABILER_KONTEXT")
        max_related_memories = 1
        max_recent_events = 4
        delegation_mode = "direct_only"
        max_delegate_calls = 0
        rationale = "Praeferenz-Updates sollen bestaetigt werden, nicht in breite Themennavigation kippen."

    if str((goal_spec or {}).get("output_mode") or "").strip().lower() in {"report", "artifact", "table"}:
        completion_condition = "requested_output_prepared"
    if next_step_title and request_kind == "resume_action":
        completion_condition = f"next_plan_step_resolved:{next_step_title}"

    direct_answer_required = request_kind in _DIRECT_ANSWER_REQUEST_KINDS
    primary_objective = goal if goal else _clean_text(effective_query, limit=320)

    return MetaClarityContract(
        schema_version=1,
        primary_objective=primary_objective,
        request_kind=request_kind,
        answer_obligation=answer_obligation,
        completion_condition=completion_condition,
        direct_answer_required=direct_answer_required,
        allowed_context_slots=allowed_context_slots,
        forbidden_context_slots=forbidden_context_slots,
        allowed_working_memory_sections=allowed_working_memory_sections,
        max_related_memories=max_related_memories,
        max_recent_events=max_recent_events,
        delegation_mode=delegation_mode,
        max_delegate_calls=max_delegate_calls,
        allowed_delegate_agents=allowed_delegate_agents,
        force_answer_after_delegate_budget=force_answer_after_delegate_budget,
        rationale=rationale,
    )


def apply_meta_clarity_to_bundle(
    bundle: Mapping[str, Any] | None,
    clarity_contract: Mapping[str, Any] | None,
) -> Dict[str, Any]:
    payload = dict(bundle or {})
    contract = parse_meta_clarity_contract(clarity_contract or {})
    slots = list(payload.get("context_slots") or [])
    if not slots or not contract:
        return payload

    allowed = set(contract.get("allowed_context_slots") or [])
    forbidden = set(contract.get("forbidden_context_slots") or [])
    filtered_slots = []
    suppressed = list(payload.get("suppressed_context") or [])

    for item in slots:
        if not isinstance(item, Mapping):
            continue
        slot = _clean_text(item.get("slot"), limit=64)
        content = _clean_text(item.get("content"), limit=180)
        if not slot:
            continue
        if slot in forbidden or (allowed and slot not in allowed):
            suppressed.append(
                {
                    "source": slot,
                    "reason": "clarity_contract_filtered_context",
                    "content_preview": content[:140],
                }
            )
            continue
        filtered_slots.append(dict(item))

    payload["context_slots"] = filtered_slots
    payload["suppressed_context"] = suppressed[:8]
    return payload


def filter_working_memory_context(
    context: str,
    clarity_contract: Mapping[str, Any] | None,
) -> str:
    contract = parse_meta_clarity_contract(clarity_contract or {})
    allowed_sections = tuple(contract.get("allowed_working_memory_sections") or ())
    text = str(context or "").strip()
    if not text or not allowed_sections:
        return text

    parts = text.split("\n\n")
    if not parts:
        return text

    header = parts[0]
    kept = [header]
    allowed = set(allowed_sections)
    for block in parts[1:]:
        first_line = block.splitlines()[0].strip() if block.splitlines() else ""
        if first_line in allowed:
            kept.append(block)

    if len(kept) <= 1:
        return ""
    return "\n\n".join(kept).strip()
