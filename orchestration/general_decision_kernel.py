"""Allgemeiner Decision-Kernel vor Frame-, Mode- und Kontextlogik."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Dict, Iterable, Mapping, Tuple


_THINK_HINTS = (
    "was haeltst du",
    "was hältst du",
    "deine meinung",
    "deine einschätzung",
    "deine einschaetzung",
    "wie wuerdest du",
    "wie würdest du",
    "hilf mir beim denken",
    "denk mit mir",
    "durchdenken",
    "brainstorm",
    "wie war nochmal",
)

_INSPECT_HINTS = (
    "schau nach",
    "schau mal nach",
    "schau mal was",
    "pruef",
    "prüf",
    "pruefe",
    "prüfe",
    "lies ",
    "lese ",
    "such ",
    "suche ",
    "finde heraus",
)

_RESEARCH_HINTS = (
    "mach dich schlau",
    "recherchiere",
    "informier dich",
    "lies dich in",
    "arbeite dich in",
)

_EXECUTE_HINTS = (
    "starte den browser",
    "gehe auf",
    "öffne",
    "oeffne",
    "zeig mir den weg",
    "route nach",
    "richte",
    "einrichten",
    "setz um",
    "umsetzen",
    "baue",
    "bau ",
    "erstelle",
    "implementiere",
    "mach fertig",
    "speichere",
    "extrahiere",
    "hole aus",
    "hol aus",
    "schreibe einen bericht",
    "bericht dazu",
    "plane meinen tag",
    "plan meinen tag",
    "plane meine woche",
    "führe das aus",
    "fuehre das aus",
)

_CLARIFY_HINTS = (
    "was meinst du genau",
    "was genau meinst du",
    "welche informationen brauchst du",
    "soll ich praezisieren",
    "soll ich präzisieren",
)

_CORRECTION_HINTS = (
    "das hast du falsch verstanden",
    "das hast du nicht verstanden",
    "was hast du eben nicht verstanden",
    "ich hab dich das gefragt",
    "ich habe dich das gefragt",
    "ich habe dir doch",
    "ich hab dir doch",
    "nein ich meinte",
    "nein, ich meinte",
)

_NEW_TOPIC_HINTS = (
    "anderes thema",
    "neue frage",
    "etwas anderes",
    "wechseln wir das thema",
)

_STANDALONE_QUESTION_HINTS = (
    "wo kann ich",
    "wohin",
    "wie kann ich",
    "was ist",
    "was kann ich",
    "welche",
    "welcher",
    "welches",
    "wer ",
    "wo ",
    "wann ",
    "warum ",
    "wieso ",
)

_TECHNICAL_DOMAINS = {
    "setup_build",
    "skill_creation",
    "location_route",
    "self_status",
    "youtube_content",
}
_DOCUMENT_DOMAINS = {"docs_status"}
_PLANNING_DOMAINS = {"planning_advisory"}
_TRAVEL_DOMAINS = {"travel_advisory"}
_PERSONAL_DOMAINS = {"life_advisory"}
_KNOWLEDGE_DOMAINS = {"migration_work", "research_advisory"}
_ADVISORY_DOMAINS = {"topic_advisory"}
_THINK_PARTNER_DOMAINS = {"travel_advisory", "topic_advisory", "life_advisory", "self_status"}
_INSPECT_DOMAINS = {"docs_status", "research_advisory"}


def _token_count(text: str) -> int:
    return len([token for token in str(text or "").split() if token.strip()])


def _looks_like_short_resume_update(
    *,
    query: str,
    active_topic: str,
    open_goal: str,
    next_step: str,
    active_domain: str,
) -> bool:
    lowered = _clean_text(query, limit=320).lower()
    if not lowered:
        return False
    if not any(
        str(item or "").strip()
        for item in (active_topic, open_goal, next_step, active_domain)
    ):
        return False
    if _contains_any(lowered, _NEW_TOPIC_HINTS):
        return False
    if _contains_any(lowered, _THINK_HINTS + _INSPECT_HINTS + _RESEARCH_HINTS + _EXECUTE_HINTS + _CLARIFY_HINTS):
        return False
    if _contains_any(lowered, _CORRECTION_HINTS):
        return True
    if "?" in lowered:
        return False
    word_count = _token_count(lowered)
    if word_count == 0 or word_count > 28:
        return False
    return bool(str(next_step or "").strip()) or word_count <= 18


def _looks_like_standalone_question(query: str) -> bool:
    lowered = _clean_text(query, limit=320).lower()
    if not lowered:
        return False
    if "?" in lowered:
        return True
    return _contains_any(lowered, _STANDALONE_QUESTION_HINTS)


def _interaction_mode_for_kernel(turn_kind: str, candidate_domain: str) -> str:
    domain = _clean_text(candidate_domain, limit=64).lower()
    if turn_kind in {"think", "inform", "clarify"}:
        return "think_partner"
    if turn_kind == "inspect":
        return "inspect"
    if turn_kind == "research":
        return "inspect"
    if turn_kind == "resume":
        if domain in _INSPECT_DOMAINS:
            return "inspect"
        if domain in {"migration_work", "research_advisory"}:
            return "inspect"
        if domain in {"setup_build", "planning_advisory"}:
            return "assist"
        return "think_partner"
    return "assist"


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
class GeneralDecisionKernel:
    schema_version: int
    turn_kind: str
    topic_family: str
    interaction_mode: str
    evidence_requirement: str
    execution_permission: str
    confidence: float
    clarify_if_below_threshold: bool
    rationale: str
    evidence: Tuple[str, ...]

    def to_dict(self) -> Dict[str, Any]:
        payload = asdict(self)
        payload["evidence"] = list(self.evidence)
        return payload


def parse_general_decision_kernel(value: Mapping[str, Any] | None) -> Dict[str, Any]:
    payload = dict(value or {})
    return {
        "schema_version": int(payload.get("schema_version") or 1),
        "turn_kind": _clean_text(payload.get("turn_kind"), limit=64).lower(),
        "topic_family": _clean_text(payload.get("topic_family"), limit=64).lower(),
        "interaction_mode": _clean_text(payload.get("interaction_mode"), limit=32).lower(),
        "evidence_requirement": _clean_text(payload.get("evidence_requirement"), limit=32).lower(),
        "execution_permission": _clean_text(payload.get("execution_permission"), limit=32).lower(),
        "confidence": round(float(payload.get("confidence") or 0.0), 2),
        "clarify_if_below_threshold": bool(payload.get("clarify_if_below_threshold")),
        "rationale": _clean_text(payload.get("rationale"), limit=220),
        "evidence": [
            _clean_text(item, limit=120)
            for item in (payload.get("evidence") or [])
            if _clean_text(item, limit=120)
        ],
    }


def _topic_family_for_domain(task_domain: str) -> str:
    domain = _clean_text(task_domain, limit=64).lower()
    if domain in _TECHNICAL_DOMAINS:
        return "technical"
    if domain in _DOCUMENT_DOMAINS:
        return "document"
    if domain in _PLANNING_DOMAINS:
        return "planning"
    if domain in _TRAVEL_DOMAINS:
        return "travel"
    if domain in _PERSONAL_DOMAINS:
        return "personal_productivity"
    if domain in _KNOWLEDGE_DOMAINS:
        return "general_knowledge"
    if domain in _ADVISORY_DOMAINS:
        return "advisory"
    return "technical" if domain else "general_knowledge"


def _infer_turn_kind(
    *,
    query: str,
    dominant_turn_type: str,
    response_mode: str,
    active_topic: str,
    open_goal: str,
    next_step: str,
    active_domain: str,
    has_active_plan: bool,
    frame_kind: str,
    task_domain: str,
    execution_mode: str,
    interaction_mode: str,
) -> tuple[str, list[str]]:
    lowered = _clean_text(query, limit=320).lower()
    evidence: list[str] = []
    domain = _clean_text(task_domain, limit=64).lower()
    frame = _clean_text(frame_kind, limit=64).lower()
    execution = _clean_text(execution_mode, limit=64).lower()
    mode = _clean_text(interaction_mode, limit=32).lower()
    turn_type = _clean_text(dominant_turn_type, limit=64).lower()
    response = _clean_text(response_mode, limit=64).lower()

    if frame == "clarify_needed" or _contains_any(lowered, _CLARIFY_HINTS):
        evidence.append("frame_or_query:clarify")
        return "clarify", evidence
    if _contains_any(lowered, _THINK_HINTS):
        evidence.append("query:think")
        return "think", evidence
    if has_active_plan and (frame == "resume_plan" or execution == "resume_existing_plan"):
        evidence.append("frame_or_execution:resume")
        return "resume", evidence
    if _contains_any(lowered, _RESEARCH_HINTS):
        evidence.append("query:research")
        return "research", evidence
    if _contains_any(lowered, _INSPECT_HINTS):
        evidence.append("query:inspect")
        return "inspect", evidence
    if _contains_any(lowered, _EXECUTE_HINTS):
        evidence.append("query:execute")
        return "execute", evidence
    if (turn_type == "followup" or response == "resume_open_loop") and not _looks_like_standalone_question(lowered):
        evidence.append("turn_or_response:resume")
        return "resume", evidence
    if _looks_like_short_resume_update(
        query=lowered,
        active_topic=active_topic,
        open_goal=open_goal,
        next_step=next_step,
        active_domain=active_domain,
    ):
        evidence.append("query:short_resume_update")
        return "resume", evidence
    if domain == "docs_status":
        evidence.append("domain:docs_status")
        return "inspect", evidence
    if mode == "inspect":
        if domain in {"migration_work", "research_advisory"}:
            evidence.append("mode_or_domain:research")
            return "research", evidence
        evidence.append("interaction_mode:inspect")
        return "inspect", evidence
    if mode == "think_partner":
        if domain == "self_status" or frame == "status_summary":
            evidence.append("frame_or_domain:inform")
            return "inform", evidence
        if _contains_any(lowered, _THINK_HINTS) or domain in {"travel_advisory", "life_advisory", "topic_advisory"}:
            evidence.append("mode_or_query:think")
            return "think", evidence
        evidence.append("mode:think_partner_default")
        return "inform", evidence
    if domain in {"migration_work", "research_advisory"}:
        evidence.append("domain:research")
        return "research", evidence
    if frame in {"direct_answer", "status_summary"}:
        evidence.append("frame:inform")
        return "inform", evidence
    evidence.append("default:execute")
    return "execute", evidence


def _infer_evidence_requirement(turn_kind: str, task_domain: str) -> str:
    if turn_kind == "think":
        return "none"
    if turn_kind == "inform":
        return "bounded" if task_domain == "docs_status" else "none"
    if turn_kind == "inspect":
        return "bounded"
    if turn_kind == "research":
        return "research"
    if turn_kind == "execute":
        return "task_dependent"
    if turn_kind == "resume":
        return "state_bound"
    return "none"


def _infer_execution_permission(turn_kind: str, interaction_mode: str, task_domain: str) -> str:
    mode = _clean_text(interaction_mode, limit=32).lower()
    if turn_kind in {"think", "inform", "clarify"}:
        return "forbidden"
    if turn_kind == "resume":
        if mode == "think_partner":
            return "forbidden"
        if mode == "inspect":
            return "bounded"
        if task_domain == "planning_advisory":
            return "forbidden"
        return "allowed"
    if turn_kind in {"inspect", "research"}:
        return "bounded"
    if task_domain == "planning_advisory" and mode == "assist":
        return "forbidden"
    if mode == "assist" or turn_kind in {"execute", "resume"}:
        return "allowed"
    return "bounded"


def build_general_decision_kernel(
    *,
    effective_query: str,
    dominant_turn_type: str = "",
    response_mode: str = "",
    active_topic: str = "",
    open_goal: str = "",
    next_step: str = "",
    active_domain: str = "",
    has_active_plan: bool = False,
    meta_request_frame: Mapping[str, Any] | None = None,
    meta_interaction_mode: Mapping[str, Any] | None = None,
) -> GeneralDecisionKernel:
    frame = dict(meta_request_frame or {})
    mode = dict(meta_interaction_mode or {})
    task_domain = _clean_text(frame.get("task_domain"), limit=64).lower() or _clean_text(active_domain, limit=64).lower()
    interaction_mode = _clean_text(mode.get("mode"), limit=32).lower()
    frame_kind = _clean_text(frame.get("frame_kind"), limit=64).lower()
    execution_mode = _clean_text(frame.get("execution_mode"), limit=64).lower()
    frame_confidence = float(frame.get("confidence") or 0.0)
    explicit_override = bool(mode.get("explicit_override"))

    turn_kind, turn_evidence = _infer_turn_kind(
        query=effective_query,
        dominant_turn_type=dominant_turn_type,
        response_mode=response_mode,
        active_topic=active_topic,
        open_goal=open_goal,
        next_step=next_step,
        active_domain=active_domain,
        has_active_plan=has_active_plan,
        frame_kind=frame_kind,
        task_domain=task_domain,
        execution_mode=execution_mode,
        interaction_mode=interaction_mode,
    )
    if not interaction_mode:
        interaction_mode = _interaction_mode_for_kernel(turn_kind, task_domain)
    topic_family = _topic_family_for_domain(task_domain)
    evidence_requirement = _infer_evidence_requirement(turn_kind, task_domain)
    execution_permission = _infer_execution_permission(turn_kind, interaction_mode, task_domain)

    confidence = frame_confidence
    if explicit_override:
        confidence = max(confidence, 0.9)
    elif any(item.startswith("frame_or_query:clarify") for item in turn_evidence):
        confidence = max(confidence, 0.82)
    elif turn_kind == "resume" and any(
        str(item or "").strip() for item in (active_topic, open_goal, next_step, active_domain)
    ):
        confidence = max(confidence, 0.78)
    elif any(item.startswith("query:execute") for item in turn_evidence):
        confidence = max(confidence, 0.78)
    elif any(item.startswith("query:research") for item in turn_evidence):
        confidence = max(confidence, 0.8)
    elif any(item.startswith("query:inspect") for item in turn_evidence):
        confidence = max(confidence, 0.78)
    elif any(item.startswith("mode_or_query:think") for item in turn_evidence):
        confidence = max(confidence, 0.74)
    elif turn_kind in {"inform", "inspect"} and frame_kind in {"direct_answer", "status_summary"}:
        confidence = max(confidence, 0.8)
    elif task_domain:
        confidence = max(confidence, 0.68)
    confidence = round(max(0.0, min(confidence, 1.0)), 2)

    clarify_if_below_threshold = confidence < 0.6 and turn_kind not in {"clarify", "resume"}
    rationale = " | ".join(
        part
        for part in (
            f"turn_kind:{turn_kind}",
            f"topic_family:{topic_family}",
            f"interaction_mode:{interaction_mode or 'unknown'}",
            f"task_domain:{task_domain or 'unknown'}",
        )
        if part
    )

    evidence = tuple(
        item
        for item in (
            *turn_evidence,
            f"frame:{frame_kind or 'unknown'}",
            f"mode:{interaction_mode or 'unknown'}",
            f"domain:{task_domain or 'unknown'}",
        )
        if item
    )

    return GeneralDecisionKernel(
        schema_version=1,
        turn_kind=turn_kind,
        topic_family=topic_family,
        interaction_mode=interaction_mode,
        evidence_requirement=evidence_requirement,
        execution_permission=execution_permission,
        confidence=confidence,
        clarify_if_below_threshold=clarify_if_below_threshold,
        rationale=rationale,
        evidence=evidence,
    )
