"""Interner Interaktionsmodus fuer Meta: pruefen oder aktiv assistieren."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Dict, Mapping, Tuple


_CONVERSATION_ASSIST_HINTS = (
    "was haeltst du",
    "was hältst du",
    "deine meinung",
    "deine einschätzung",
    "deine einschaetzung",
    "wie wuerdest du das einschaetzen",
    "wie würdest du das einschätzen",
    "hilf mir beim denken",
    "denk mit mir",
    "lass uns das durchdenken",
    "brainstorm",
    "ohne recherche",
    "nichts ausfuehren",
    "nichts ausführen",
    "nur deine meinung",
    "nur deine einschätzung",
    "nur deine einschaetzung",
)

_EXPLICIT_INSPECT_HINTS = (
    "nur pruefen",
    "nur prüfen",
    "nur schauen",
    "nur checken",
    "nicht umsetzen",
    "nichts bauen",
)

_INSPECT_HINTS = (
    "schau nach",
    "schau mal nach",
    "pruef",
    "prüf",
    "pruefe",
    "prüfe",
    "finde heraus",
    "lies ",
    "lese ",
    "such ",
    "suche ",
    "recherchiere",
    "mach dich schlau",
    "was gibt es schon",
)

_EXPLICIT_ASSIST_HINTS = (
    "jetzt umsetzen",
    "setz es jetzt um",
    "baue es jetzt",
    "fuehre das jetzt aus",
    "führe das jetzt aus",
)

_ASSIST_HINTS = (
    "richte",
    "einrichten",
    "setz um",
    "umsetzen",
    "baue",
    "bau ",
    "erstelle",
    "implementiere",
    "mach fertig",
    "plane meinen tag",
    "plan meinen tag",
)


def _clean_text(value: Any, *, limit: int = 240) -> str:
    text = " ".join(str(value or "").strip().split())
    if len(text) <= limit:
        return text
    clipped = text[:limit].rsplit(" ", 1)[0].strip()
    return f"{clipped or text[:limit]}..."


@dataclass(frozen=True)
class MetaInteractionMode:
    schema_version: int
    mode: str
    mode_reason: str
    explicit_override: bool
    answer_style: str
    execution_policy: str
    completion_expectation: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def parse_meta_interaction_mode(value: Mapping[str, Any] | None) -> Dict[str, Any]:
    payload = dict(value or {})
    return {
        "schema_version": int(payload.get("schema_version") or 1),
        "mode": _clean_text(payload.get("mode"), limit=32).lower() or "assist",
        "mode_reason": _clean_text(payload.get("mode_reason"), limit=120),
        "explicit_override": bool(payload.get("explicit_override")),
        "answer_style": _clean_text(payload.get("answer_style"), limit=64),
        "execution_policy": _clean_text(payload.get("execution_policy"), limit=96),
        "completion_expectation": _clean_text(payload.get("completion_expectation"), limit=120),
    }


def build_meta_interaction_mode(
    *,
    effective_query: str,
    meta_request_frame: Mapping[str, Any] | None = None,
    policy_decision: Mapping[str, Any] | None = None,
) -> MetaInteractionMode:
    query = _clean_text(effective_query, limit=320).lower()
    frame = dict(meta_request_frame or {})
    policy = dict(policy_decision or {})

    task_domain = _clean_text(frame.get("task_domain"), limit=64).lower()
    frame_kind = _clean_text(frame.get("frame_kind"), limit=64).lower()
    execution_mode = _clean_text(frame.get("execution_mode"), limit=64).lower()
    answer_shape = _clean_text(policy.get("answer_shape"), limit=64).lower()
    policy_reason = _clean_text(policy.get("policy_reason"), limit=80).lower()

    if any(hint in query for hint in _CONVERSATION_ASSIST_HINTS):
        return MetaInteractionMode(
            schema_version=1,
            mode="assist",
            mode_reason="explicit_conversation_assist_language",
            explicit_override=True,
            answer_style="reason_with_user_with_evidence_when_needed",
            execution_policy="plan_delegate_or_execute",
            completion_expectation="useful_answer_or_next_action",
        )

    if any(hint in query for hint in _EXPLICIT_INSPECT_HINTS):
        return MetaInteractionMode(
            schema_version=1,
            mode="inspect",
            mode_reason="explicit_inspection_language",
            explicit_override=True,
            answer_style="report_findings",
            execution_policy="bounded_evidence_only",
            completion_expectation="findings_or_gaps_reported",
        )

    if any(hint in query for hint in _EXPLICIT_ASSIST_HINTS):
        return MetaInteractionMode(
            schema_version=1,
            mode="assist",
            mode_reason="explicit_assist_language",
            explicit_override=True,
            answer_style="action_or_plan",
            execution_policy="plan_delegate_or_execute",
            completion_expectation="concrete_next_action_or_result",
        )

    if answer_shape in {"self_model_status", "state_summary", "direct_response", "direct_recommendation"} or frame_kind in {
        "direct_answer",
        "status_summary",
    }:
        return MetaInteractionMode(
            schema_version=1,
            mode="assist",
            mode_reason="direct_answer_or_status_frame",
            explicit_override=False,
            answer_style="direct_answer",
            execution_policy="answer_or_delegate_when_evidence_needed",
            completion_expectation="direct_answer_given",
        )

    if task_domain in {"docs_status", "research_advisory"}:
        return MetaInteractionMode(
            schema_version=1,
            mode="inspect",
            mode_reason=f"task_domain:{task_domain}",
            explicit_override=False,
            answer_style="report_findings",
            execution_policy="bounded_evidence_only",
            completion_expectation="findings_or_next_research_path_named",
        )

    if task_domain in {"travel_advisory", "topic_advisory", "life_advisory"}:
        return MetaInteractionMode(
            schema_version=1,
            mode="assist",
            mode_reason=f"task_domain:{task_domain}",
            explicit_override=False,
            answer_style="reason_with_user_with_evidence_when_needed",
            execution_policy="plan_delegate_or_execute",
            completion_expectation="advisory_answer_options_or_action",
        )

    if task_domain == "setup_build":
        mode_reason = "task_domain:setup_build"
        if "vorbereitungen" in query or "was gibt es schon" in query:
            return MetaInteractionMode(
                schema_version=1,
                mode="inspect",
                mode_reason="setup_build_preparation_check",
                explicit_override=False,
                answer_style="report_findings",
                execution_policy="bounded_evidence_only",
                completion_expectation="existing_preparations_or_gap_named",
            )
        return MetaInteractionMode(
            schema_version=1,
            mode="assist",
            mode_reason=mode_reason,
            explicit_override=False,
            answer_style="action_or_plan",
            execution_policy="plan_delegate_or_execute",
            completion_expectation="build_path_or_execution_started",
        )

    if task_domain == "planning_advisory":
        return MetaInteractionMode(
            schema_version=1,
            mode="assist",
            mode_reason="task_domain:planning_advisory",
            explicit_override=False,
            answer_style="structured_plan",
            execution_policy="deliver_concrete_plan_without_side_effects",
            completion_expectation="usable_plan_or_constraints_named",
        )

    if execution_mode == "answer_directly" or policy_reason in {
        "next_step_summary_request",
        "state_summary_request",
        "self_model_status_request",
    }:
        return MetaInteractionMode(
            schema_version=1,
            mode="assist",
            mode_reason="frame_answer_directly",
            explicit_override=False,
            answer_style="direct_answer",
            execution_policy="answer_or_delegate_when_evidence_needed",
            completion_expectation="direct_answer_given",
        )

    if any(hint in query for hint in _INSPECT_HINTS):
        return MetaInteractionMode(
            schema_version=1,
            mode="inspect",
            mode_reason="task_language:inspect",
            explicit_override=False,
            answer_style="report_findings",
            execution_policy="bounded_evidence_only",
            completion_expectation="findings_or_gaps_reported",
        )

    if any(hint in query for hint in _ASSIST_HINTS):
        return MetaInteractionMode(
            schema_version=1,
            mode="assist",
            mode_reason="task_language:assist",
            explicit_override=False,
            answer_style="action_or_plan",
            execution_policy="plan_delegate_or_execute",
            completion_expectation="concrete_next_action_or_result",
        )

    return MetaInteractionMode(
        schema_version=1,
        mode="assist",
        mode_reason="default_assist",
        explicit_override=False,
        answer_style="action_or_plan",
        execution_policy="plan_delegate_or_execute",
        completion_expectation="concrete_next_action_or_result",
    )
