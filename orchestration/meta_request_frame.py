"""Kanonischer Request-Frame fuer den Meta-Orchestrator."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Dict, Iterable, Mapping, Tuple


_DOC_STATUS_HINTS = (
    "docs/",
    "changelog",
    "phase_",
    "phase ",
    "plan.md",
)
_STATE_SUMMARY_HINTS = (
    "wo stehen wir",
    "wie ist dein zustand",
    "hast du probleme",
    "was ist dein zustand",
    "aktueller stand",
)
_SELF_STATUS_HINTS = (
    "wie ist dein zustand",
    "was ist dein zustand",
    "hast du probleme",
    "hast du probleme mich zu verstehen",
    "welche probleme hast du",
    "was ist los",
    "wo hakt es",
)
_LOCATION_ROUTE_HINTS = (
    "route",
    "weg nach",
    "anfahrt",
    "maps",
    "google maps",
    "mit dem auto",
    "driving",
)
_SKILL_CREATION_HINTS = (
    "skill-creator",
    "skill creator",
    "skill erstellen",
    "neuen skill",
    "neuer skill",
    "bestehenden skill",
)
_SETUP_BUILD_HINTS = (
    "einrichten",
    "richte",
    "setup",
    "install",
    "konfigurier",
    "konfigur",
    "integrier",
    "integration",
    "verbinde",
    "anruffunktion",
    "api key",
    "twilio",
    "inworld",
)
_MIGRATION_WORK_HINTS = (
    "kanada",
    "canada",
    "auswand",
    "einwander",
    "visa",
    "visum",
    "arbeiten",
    "arbeit",
    "job",
    "beruf",
    "niederlass",
    "fuss fassen",
    "fuß fassen",
    "leben aufbauen",
)
_PLANNING_ADVISORY_HINTS = (
    "plane meinen tag",
    "plan meinen tag",
    "plane mir den tag",
    "meinen tag planen",
    "tagesplan",
    "strukturier meinen tag",
    "plane meine woche",
    "plan meine woche",
    "meine woche strukturieren",
    "hilf mir meinen tag zu planen",
)
_TRAVEL_ADVISORY_HINTS = (
    "wo kann ich am wochenende hin",
    "wo kann ich am weekend hin",
    "wohin am wochenende",
    "ausflugsziel",
    "ausflugsziele",
    "staedtetrip",
    "städte-trip",
    "wohin in deutschland",
    "trip nach",
    "reiseidee",
    "reiseideen",
)
_LIFE_ADVISORY_HINTS = (
    "wie soll ich mit meinem leben",
    "alltag ordnen",
    "mein alltag",
    "mein leben",
    "privatleben",
    "beziehung",
    "stress im alltag",
    "lebensentscheidung",
)
_RESEARCH_ADVISORY_HINTS = (
    "mach dich schlau ueber",
    "mach dich schlau über",
    "informier dich ueber",
    "informier dich über",
    "lies dich in",
    "arbeite dich in",
    "recherchiere ueber",
    "recherchiere über",
    "recherchiere zu",
    "hilf mir dann",
    "und hilf mir dann",
    "steh mir hilfreich zur seite",
    "steh mir hilfreich zur Seite",
    "hilfreich zur seite",
    "hilfreich zur Seite",
)

_DOMAIN_HINTS: dict[str, tuple[str, ...]] = {
    "self_status": _SELF_STATUS_HINTS,
    "skill_creation": _SKILL_CREATION_HINTS,
    "location_route": _LOCATION_ROUTE_HINTS
    + (
        "offenbach",
        "münster",
        "muenster",
        "standort",
        "navigation",
    ),
    "telephony_setup": (
        "twilio",
        "inworld",
        "anruffunktion",
        "telefon",
        "voice",
        "stimme",
        "lennart",
    ),
    "planning_advisory": _PLANNING_ADVISORY_HINTS,
    "research_advisory": _RESEARCH_ADVISORY_HINTS,
    "travel_advisory": _TRAVEL_ADVISORY_HINTS,
    "life_advisory": _LIFE_ADVISORY_HINTS,
    "migration_work": _MIGRATION_WORK_HINTS,
    "docs_status": _DOC_STATUS_HINTS,
}

_CARRIABLE_ADVISORY_DOMAINS = {
    "travel_advisory",
    "life_advisory",
    "topic_advisory",
}


def _clean_text(value: Any, *, limit: int = 240) -> str:
    text = " ".join(str(value or "").strip().split())
    if len(text) <= limit:
        return text
    clipped = text[:limit].rsplit(" ", 1)[0].strip()
    return f"{clipped or text[:limit]}..."


def _contains_any(text: str, patterns: Iterable[str]) -> bool:
    lowered = str(text or "").strip().lower()
    return any(pattern in lowered for pattern in patterns)


@dataclass(frozen=True)
class MetaRequestFrame:
    schema_version: int
    frame_kind: str
    task_domain: str
    execution_mode: str
    primary_objective: str
    topic_anchor: str
    goal_anchor: str
    allowed_memory_domains: Tuple[str, ...]
    forbidden_memory_domains: Tuple[str, ...]
    allowed_context_slots: Tuple[str, ...]
    delegation_budget: int
    allowed_delegate_agents: Tuple[str, ...]
    completion_contract: str
    confidence: float
    evidence: Tuple[str, ...]

    def to_dict(self) -> Dict[str, Any]:
        payload = asdict(self)
        for key, value in tuple(payload.items()):
            if isinstance(value, tuple):
                payload[key] = list(value)
        return payload


def _infer_frame_kind(
    *,
    effective_query: str,
    dominant_turn_type: str,
    response_mode: str,
    answer_shape: str,
    has_active_plan: bool,
) -> tuple[str, list[str]]:
    evidence: list[str] = []
    query_text = _clean_text(effective_query, limit=320).lower()
    turn_type = _clean_text(dominant_turn_type, limit=64).lower()
    mode = _clean_text(response_mode, limit=64).lower()
    shape = _clean_text(answer_shape, limit=64).lower()

    if shape in {"direct_recommendation", "state_summary", "historical_topic_state", "self_model_status"}:
        evidence.append(f"answer_shape:{shape}")
        return "direct_answer" if shape == "direct_recommendation" else "status_summary", evidence
    if _contains_any(query_text, _DOC_STATUS_HINTS):
        evidence.append("query:docs_status_like")
        return "direct_answer", evidence
    if _contains_any(query_text, _STATE_SUMMARY_HINTS):
        evidence.append("query:state_summary_like")
        return "status_summary", evidence
    if mode == "clarify_before_execute":
        evidence.append("response_mode:clarify_before_execute")
        return "clarify_needed", evidence
    if mode == "resume_open_loop" and has_active_plan:
        evidence.append("response_mode:resume_open_loop")
        evidence.append("active_plan:true")
        return "resume_plan", evidence
    if turn_type == "followup":
        evidence.append("dominant_turn_type:followup")
        return "stateful_followup", evidence
    evidence.append(f"dominant_turn_type:{turn_type or 'new_task'}")
    return "new_task", evidence


def _infer_task_domain(
    *,
    effective_query: str,
    active_topic: str,
    open_goal: str,
    task_type: str,
) -> tuple[str, list[str], float]:
    query_text = _clean_text(effective_query, limit=320).lower()
    anchor_text = " | ".join(
        item for item in (_clean_text(active_topic, limit=180), _clean_text(open_goal, limit=180)) if item
    ).lower()
    combined = " | ".join(item for item in (query_text, anchor_text) if item)
    evidence: list[str] = []

    if _contains_any(query_text, _DOC_STATUS_HINTS):
        evidence.append("query:docs_status")
        return "docs_status", evidence, 0.96
    if _contains_any(query_text, _SELF_STATUS_HINTS):
        evidence.append("query:self_status")
        return "self_status", evidence, 0.93
    if _contains_any(query_text, _LOCATION_ROUTE_HINTS):
        evidence.append("query:location_route")
        return "location_route", evidence, 0.95
    if _contains_any(query_text, _SETUP_BUILD_HINTS):
        evidence.append("query:setup_build")
        return "setup_build", evidence, 0.93
    if _contains_any(query_text, _SKILL_CREATION_HINTS):
        evidence.append("query:skill_creation")
        return "skill_creation", evidence, 0.93
    if _contains_any(combined, _MIGRATION_WORK_HINTS):
        evidence.append("query_or_anchor:migration_work")
        return "migration_work", evidence, 0.9 if _contains_any(query_text, _MIGRATION_WORK_HINTS) else 0.82
    if _contains_any(query_text, _PLANNING_ADVISORY_HINTS):
        evidence.append("query:planning_advisory")
        return "planning_advisory", evidence, 0.88
    if _contains_any(query_text, _RESEARCH_ADVISORY_HINTS):
        evidence.append("query:research_advisory")
        return "research_advisory", evidence, 0.9
    if _contains_any(query_text, _TRAVEL_ADVISORY_HINTS):
        evidence.append("query:travel_advisory")
        return "travel_advisory", evidence, 0.86
    if _contains_any(query_text, _LIFE_ADVISORY_HINTS):
        evidence.append("query:life_advisory")
        return "life_advisory", evidence, 0.82

    normalized_task_type = _clean_text(task_type, limit=64).lower()
    task_type_mapping = {
        "knowledge_research": "general_research",
        "simple_live_lookup": "general_research",
        "simple_live_lookup_document": "general_research",
        "communication_task": "communication",
        "document_generation": "document_generation",
        "location_local_search": "location_local_search",
        "location_route": "location_route",
        "system_diagnosis": "system_diagnosis",
        "youtube_content_extraction": "youtube_content",
        "youtube_light_research": "youtube_content",
    }
    mapped = task_type_mapping.get(normalized_task_type)
    if mapped:
        evidence.append(f"task_type:{normalized_task_type}")
        return mapped, evidence, 0.72
    if normalized_task_type == "single_lane":
        evidence.append("task_type:single_lane")
        return "topic_advisory", evidence, 0.58
    evidence.append("fallback:general_task")
    return "general_task", evidence, 0.5


def infer_meta_task_domain_hint(
    *,
    effective_query: str,
    active_topic: str,
    open_goal: str,
    task_type: str,
    carried_domain: str = "",
) -> tuple[str, tuple[str, ...], float]:
    task_domain, evidence, confidence = _infer_task_domain(
        effective_query=effective_query,
        active_topic=active_topic,
        open_goal=open_goal,
        task_type=task_type,
    )
    normalized_carried = _clean_text(carried_domain, limit=64).lower()
    if (
        normalized_carried in _CARRIABLE_ADVISORY_DOMAINS
        and task_domain in {"general_task", "topic_advisory"}
    ):
        query_text = _clean_text(effective_query, limit=320).lower()
        has_stronger_domain = any(
            _contains_any(query_text, patterns)
            for patterns in (
                _DOC_STATUS_HINTS,
                _SELF_STATUS_HINTS,
                _LOCATION_ROUTE_HINTS,
                _SETUP_BUILD_HINTS,
                _SKILL_CREATION_HINTS,
                _MIGRATION_WORK_HINTS,
                _PLANNING_ADVISORY_HINTS,
                _RESEARCH_ADVISORY_HINTS,
                _TRAVEL_ADVISORY_HINTS,
                _LIFE_ADVISORY_HINTS,
            )
        )
        if not has_stronger_domain or task_domain == normalized_carried:
            evidence.append(f"carried_domain:{normalized_carried}")
            return normalized_carried, tuple(evidence), max(confidence, 0.66)
    return task_domain, tuple(evidence), confidence


def _frame_memory_rules(
    *,
    frame_kind: str,
    task_domain: str,
) -> tuple[Tuple[str, ...], Tuple[str, ...], Tuple[str, ...], str]:
    if task_domain == "docs_status":
        return (
            ("docs_status", "project_state", "historical_topic"),
            ("skill_creation", "location_route", "telephony_setup"),
            ("current_query", "conversation_state", "open_loop", "recent_user_turn", "historical_topic_memory"),
            "name_next_step_or_status_directly",
        )
    if task_domain == "migration_work":
        return (
            ("migration_work", "country_research", "work_mobility", "historical_topic"),
            ("skill_creation", "location_route", "telephony_setup"),
            ("current_query", "conversation_state", "open_loop", "recent_user_turn", "topic_memory", "historical_topic_memory"),
            "return_actionable_migration_or_work_path",
        )
    if task_domain == "planning_advisory":
        return (
            ("planning_advisory", "historical_topic", "topic_continuity"),
            ("skill_creation", "location_route", "telephony_setup"),
            ("current_query", "conversation_state", "open_loop", "recent_user_turn", "topic_memory", "historical_topic_memory"),
            "collect_constraints_or_return_planning_structure",
        )
    if task_domain == "travel_advisory":
        return (
            ("travel_advisory", "destination_research", "historical_topic"),
            ("skill_creation", "location_route", "telephony_setup"),
            ("current_query", "conversation_state", "open_loop", "recent_user_turn", "topic_memory", "historical_topic_memory"),
            "recommend_destinations_or_collect_missing_preferences",
        )
    if task_domain == "life_advisory":
        return (
            ("life_advisory", "topic_continuity", "historical_topic"),
            ("skill_creation", "location_route", "telephony_setup"),
            ("current_query", "conversation_state", "open_loop", "recent_user_turn", "topic_memory", "historical_topic_memory"),
            "reason_through_options_without_off_domain_drift",
        )
    if task_domain == "topic_advisory":
        return (
            ("topic_advisory", "topic_continuity", "historical_topic"),
            ("skill_creation", "location_route", "telephony_setup"),
            ("current_query", "conversation_state", "open_loop", "recent_user_turn", "topic_memory", "historical_topic_memory"),
            "answer_or_clarify_within_current_topic",
        )
    if task_domain == "research_advisory":
        return (
            ("research_advisory", "general_research", "historical_topic"),
            ("skill_creation", "location_route", "telephony_setup"),
            ("current_query", "conversation_state", "open_loop", "recent_user_turn", "topic_memory", "historical_topic_memory"),
            "build_topic_understanding_and_support_followups",
        )
    if task_domain == "setup_build":
        return (
            ("setup_build", "integration", "developer_workflow"),
            ("location_route",),
            ("current_query", "conversation_state", "open_loop", "recent_user_turn", "topic_memory"),
            "return_build_path_or_start_execution",
        )
    if task_domain == "self_status":
        return (
            ("self_status", "project_state", "historical_topic"),
            ("skill_creation", "location_route", "telephony_setup"),
            ("current_query", "conversation_state", "recent_user_turn", "historical_topic_memory"),
            "summarize_self_state_without_off_domain_drift",
        )
    if task_domain == "skill_creation":
        return (
            ("skill_creation", "developer_workflow", "historical_topic"),
            ("location_route", "telephony_setup"),
            ("current_query", "conversation_state", "open_loop", "recent_user_turn", "historical_topic_memory"),
            "collect_skill_scope_or_start_skill_flow",
        )
    if frame_kind in {"direct_answer", "status_summary"}:
        return (
            ("project_state", "historical_topic"),
            ("location_route", "skill_creation", "telephony_setup"),
            ("current_query", "conversation_state", "open_loop", "recent_user_turn", "historical_topic_memory"),
            "answer_directly_without_domain_drift",
        )
    return (
        ("topic_continuity", "historical_topic", "general_research"),
        (),
        ("current_query", "conversation_state", "open_loop", "recent_user_turn", "topic_memory", "historical_topic_memory"),
        "address_primary_objective_without_off_frame_drift",
    )


def _infer_execution_mode(frame_kind: str) -> str:
    if frame_kind in {"direct_answer", "status_summary"}:
        return "answer_directly"
    if frame_kind == "clarify_needed":
        return "clarify_once"
    if frame_kind == "resume_plan":
        return "resume_existing_plan"
    return "plan_and_delegate"


def apply_meta_request_frame_routing(
    frame: Mapping[str, Any] | None,
    *,
    task_type: str,
    recommended_chain: Iterable[str] | None,
    reason: str,
    required_capabilities: Iterable[str] | None = None,
) -> dict[str, Any]:
    payload = dict(frame or {})
    frame_kind = _clean_text(payload.get("frame_kind"), limit=64).lower()
    task_domain = _clean_text(payload.get("task_domain"), limit=64).lower()
    execution_mode = _clean_text(payload.get("execution_mode"), limit=64).lower()
    confidence = float(payload.get("confidence") or 0.0)

    chain = [
        _clean_text(item, limit=48).lower()
        for item in (recommended_chain or ())
        if _clean_text(item, limit=48)
    ]
    capabilities = [
        _clean_text(item, limit=64).lower()
        for item in (required_capabilities or ())
        if _clean_text(item, limit=64)
    ]
    normalized_task_type = _clean_text(task_type, limit=64).lower() or "single_lane"
    final_reason = reason

    if frame_kind in {"direct_answer", "status_summary"}:
        return {
            "task_type": "single_lane",
            "recommended_agent_chain": ["meta"],
            "required_capabilities": [],
            "reason": f"frame:{task_domain or frame_kind}",
        }

    if task_domain == "migration_work" and confidence >= 0.85:
        if not chain or chain == ["executor"]:
            chain = ["meta", "research"]
        elif chain[0] != "meta":
            chain = ["meta", *[item for item in chain if item != "meta"]]
        if "research" not in chain:
            chain.append("research")
        for capability in ("content_extraction", "source_research"):
            if capability not in capabilities:
                capabilities.append(capability)
        if normalized_task_type == "single_lane":
            normalized_task_type = "knowledge_research"
        final_reason = "frame:migration_work"
    elif task_domain == "research_advisory":
        if not chain or chain == ["executor"]:
            chain = ["meta", "executor"]
        elif chain[0] != "meta":
            chain = ["meta", *[item for item in chain if item != "meta"]]
        if "executor" not in chain:
            chain.append("executor")
        for capability in ("content_extraction", "source_research"):
            if capability not in capabilities:
                capabilities.append(capability)
        normalized_task_type = "single_lane"
        final_reason = "frame:research_advisory"
    elif task_domain == "planning_advisory":
        chain = ["meta"]
        normalized_task_type = "single_lane"
        final_reason = "frame:planning_advisory"
    elif task_domain in {"travel_advisory", "life_advisory", "topic_advisory"}:
        if normalized_task_type == "single_lane":
            chain = ["meta"]
            final_reason = f"frame:{task_domain}" if reason == "single_lane" else reason
    elif task_domain == "setup_build":
        if not chain or chain == ["executor"]:
            chain = ["meta", "executor"]
        elif chain[0] != "meta":
            chain = ["meta", *[item for item in chain if item != "meta"]]
        normalized_task_type = "single_lane" if normalized_task_type == "single_lane" else normalized_task_type
        final_reason = "frame:setup_build"
    elif task_domain == "skill_creation":
        chain = ["meta"]
        normalized_task_type = "single_lane"
        final_reason = "frame:skill_creation"
    elif task_domain == "docs_status":
        chain = ["meta"]
        normalized_task_type = "single_lane"
        final_reason = "frame:docs_status"
    elif execution_mode == "resume_existing_plan" and not chain:
        chain = ["meta"]
        final_reason = "frame:resume_existing_plan"

    return {
        "task_type": normalized_task_type,
        "recommended_agent_chain": chain or ["meta"],
        "required_capabilities": capabilities,
        "reason": final_reason,
    }


def build_meta_request_frame(
    *,
    effective_query: str,
    dominant_turn_type: str,
    response_mode: str,
    answer_shape: str,
    task_type: str,
    active_topic: str,
    open_goal: str,
    next_step: str,
    active_domain: str = "",
    recommended_agent_chain: Iterable[str] | None = None,
    active_plan: Mapping[str, Any] | None = None,
) -> MetaRequestFrame:
    has_active_plan = bool(dict(active_plan or {}))
    frame_kind, kind_evidence = _infer_frame_kind(
        effective_query=effective_query,
        dominant_turn_type=dominant_turn_type,
        response_mode=response_mode,
        answer_shape=answer_shape,
        has_active_plan=has_active_plan,
    )
    task_domain, domain_evidence, confidence = infer_meta_task_domain_hint(
        effective_query=effective_query,
        active_topic=active_topic,
        open_goal=open_goal,
        task_type=task_type,
        carried_domain=active_domain,
    )
    execution_mode = _infer_execution_mode(frame_kind)
    allowed_memory_domains, forbidden_memory_domains, allowed_context_slots, completion_contract = _frame_memory_rules(
        frame_kind=frame_kind,
        task_domain=task_domain,
    )
    delegate_agents = tuple(
        str(agent or "").strip().lower()
        for agent in (recommended_agent_chain or ())
        if str(agent or "").strip() and str(agent or "").strip().lower() != "meta"
    )
    delegation_budget = 0 if execution_mode == "answer_directly" else len(delegate_agents)
    primary_objective = _clean_text(open_goal or effective_query, limit=320)
    goal_anchor = _clean_text(open_goal or next_step or effective_query, limit=220)
    topic_anchor = _clean_text(active_topic, limit=180)
    evidence = tuple([*kind_evidence, *domain_evidence])

    return MetaRequestFrame(
        schema_version=1,
        frame_kind=frame_kind,
        task_domain=task_domain,
        execution_mode=execution_mode,
        primary_objective=primary_objective,
        topic_anchor=topic_anchor,
        goal_anchor=goal_anchor,
        allowed_memory_domains=allowed_memory_domains,
        forbidden_memory_domains=forbidden_memory_domains,
        allowed_context_slots=allowed_context_slots,
        delegation_budget=delegation_budget,
        allowed_delegate_agents=delegate_agents,
        completion_contract=completion_contract,
        confidence=round(confidence, 2),
        evidence=evidence,
    )


def _matches_domain_hint(text: str, domain: str) -> bool:
    hints = _DOMAIN_HINTS.get(_clean_text(domain, limit=64).lower(), ())
    if not hints:
        return False
    return _contains_any(text, hints)


def apply_meta_request_frame_context_admission(
    frame: Mapping[str, Any] | None,
    *,
    bundle: Mapping[str, Any] | None,
    preference_memory_selection: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    payload = dict(bundle or {})
    context_slots = list(payload.get("context_slots") or [])
    suppressed = list(payload.get("suppressed_context") or [])
    frame_payload = dict(frame or {})
    allowed_slots = {
        _clean_text(item, limit=64)
        for item in (frame_payload.get("allowed_context_slots") or [])
        if _clean_text(item, limit=64)
    }
    forbidden_domains = {
        _clean_text(item, limit=64).lower()
        for item in (frame_payload.get("forbidden_memory_domains") or [])
        if _clean_text(item, limit=64)
    }
    task_domain = _clean_text(frame_payload.get("task_domain"), limit=64).lower()
    execution_mode = _clean_text(frame_payload.get("execution_mode"), limit=64).lower()
    strict_admission = task_domain in {
        "docs_status",
        "migration_work",
        "setup_build",
        "skill_creation",
        "travel_advisory",
        "life_advisory",
        "topic_advisory",
    } or (
        execution_mode == "answer_directly" and bool(forbidden_domains)
    )

    filtered_slots: list[dict[str, Any]] = []
    for item in context_slots:
        if not isinstance(item, Mapping):
            continue
        slot = _clean_text(item.get("slot"), limit=64)
        content = _clean_text(item.get("content"), limit=220)
        if not slot:
            continue
        lowered_content = content.lower()
        blocked_domain = (
            next(
                (domain for domain in forbidden_domains if _matches_domain_hint(lowered_content, domain)),
                "",
            )
            if strict_admission
            else ""
        )
        if strict_admission and blocked_domain:
            suppressed.append(
                {
                    "source": slot,
                    "reason": f"frame_domain_filtered:{blocked_domain}",
                    "content_preview": content[:140],
                }
            )
            continue
        filtered_slots.append(dict(item))

    selection = dict(preference_memory_selection or {})
    selected_preferences = list(selection.get("selected") or [])
    selected_details = list(selection.get("selected_details") or [])
    filtered_preferences: list[str] = []
    filtered_details: list[dict[str, Any]] = []
    filtered_irrelevant = list(selection.get("filtered_irrelevant") or [])

    preference_allowed = (not strict_admission) or (not allowed_slots or "preference_memory" in allowed_slots)
    if preference_allowed:
        for index, item in enumerate(selected_preferences):
            rendered = _clean_text(item, limit=220)
            lowered_rendered = rendered.lower()
            blocked_domain = (
                next(
                    (domain for domain in forbidden_domains if _matches_domain_hint(lowered_rendered, domain)),
                    "",
                )
                if strict_admission
                else ""
            )
            if strict_admission and blocked_domain:
                filtered_irrelevant.append(
                    {
                        "rendered": rendered,
                        "reason": f"frame_domain_filtered:{blocked_domain}",
                    }
                )
                continue
            filtered_preferences.append(item)
            if index < len(selected_details) and isinstance(selected_details[index], Mapping):
                filtered_details.append(dict(selected_details[index]))
    else:
        for item in selected_preferences:
            rendered = _clean_text(item, limit=220)
            filtered_irrelevant.append(
                {
                    "rendered": rendered,
                    "reason": "frame_preference_memory_disallowed",
                }
            )

    selection["selected"] = filtered_preferences
    selection["selected_details"] = filtered_details
    if filtered_irrelevant:
        selection["filtered_irrelevant"] = filtered_irrelevant[:8]

    payload["context_slots"] = filtered_slots
    payload["suppressed_context"] = suppressed[:10]
    return {
        "meta_context_bundle": payload,
        "preference_memory_selection": selection,
    }
