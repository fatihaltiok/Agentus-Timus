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
    "naechstes ansteht",
    "nächstes ansteht",
    "next step",
    "wo stehen wir",
    "status",
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
    dominant_turn_type: str,
    response_mode: str,
    answer_shape: str,
    has_active_plan: bool,
) -> tuple[str, list[str]]:
    evidence: list[str] = []
    turn_type = _clean_text(dominant_turn_type, limit=64).lower()
    mode = _clean_text(response_mode, limit=64).lower()
    shape = _clean_text(answer_shape, limit=64).lower()

    if shape in {"direct_recommendation", "state_summary", "historical_topic_state", "self_model_status"}:
        evidence.append(f"answer_shape:{shape}")
        return "direct_answer" if shape == "direct_recommendation" else "status_summary", evidence
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
        return "general_advisory", evidence, 0.58
    evidence.append("fallback:general_task")
    return "general_task", evidence, 0.5


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
    if task_domain == "setup_build":
        return (
            ("setup_build", "integration", "developer_workflow"),
            ("location_route",),
            ("current_query", "conversation_state", "open_loop", "recent_user_turn", "topic_memory"),
            "return_build_path_or_start_execution",
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
    recommended_agent_chain: Iterable[str] | None = None,
    active_plan: Mapping[str, Any] | None = None,
) -> MetaRequestFrame:
    has_active_plan = bool(dict(active_plan or {}))
    frame_kind, kind_evidence = _infer_frame_kind(
        dominant_turn_type=dominant_turn_type,
        response_mode=response_mode,
        answer_shape=answer_shape,
        has_active_plan=has_active_plan,
    )
    task_domain, domain_evidence, confidence = _infer_task_domain(
        effective_query=effective_query,
        active_topic=active_topic,
        open_goal=open_goal,
        task_type=task_type,
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
    evidence = tuple(kind_evidence + domain_evidence)

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
