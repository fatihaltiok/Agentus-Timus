"""Z2 meta plan compiler for explicit multi-step execution plans."""

from __future__ import annotations

import json
import re
from typing import Any, Iterable, Mapping

from orchestration.task_decomposition_contract import (
    build_task_decomposition,
    parse_task_decomposition,
)


META_EXECUTION_PLAN_SCHEMA_VERSION = 1
_VALID_PLAN_MODES = {
    "direct_response",
    "lightweight_lookup",
    "plan_only",
    "multi_step_execution",
}


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
    limit_chars: int = 120,
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


def _normalize_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "yes", "ja", "on"}


def _normalize_int(value: Any, *, default: int = 0, minimum: int = 0) -> int:
    try:
        return max(minimum, int(value))
    except (TypeError, ValueError):
        return max(minimum, int(default))


def _normalize_constraints(value: Mapping[str, Any] | None) -> dict[str, list[str]]:
    payload = dict(value or {})
    return {
        "hard": _normalize_text_list(payload.get("hard"), limit_items=8),
        "soft": _normalize_text_list(payload.get("soft"), limit_items=8),
        "forbidden_actions": _normalize_text_list(payload.get("forbidden_actions"), limit_items=8),
    }


def _normalize_step(step: Mapping[str, Any] | None) -> dict[str, Any]:
    payload = dict(step or {})
    return {
        "id": _clean_text(payload.get("id"), limit=64).lower().replace(" ", "_") or "step",
        "title": _clean_text(payload.get("title"), limit=160),
        "step_kind": _clean_text(payload.get("step_kind"), limit=48).lower() or "generic",
        "assigned_agent": _clean_text(payload.get("assigned_agent"), limit=48).lower() or "meta",
        "status": _clean_text(payload.get("status"), limit=32).lower() or "pending",
        "depends_on": _normalize_text_list(payload.get("depends_on"), limit_items=6, limit_chars=48),
        "optional": bool(payload.get("optional")),
        "completion_signals": _normalize_text_list(
            payload.get("completion_signals"),
            limit_items=8,
            limit_chars=96,
        )
        or ["step_completed"],
        "recipe_stage_id": _clean_text(payload.get("recipe_stage_id"), limit=64),
        "expected_output": _clean_text(payload.get("expected_output"), limit=160),
        "source_subtask_id": _clean_text(payload.get("source_subtask_id"), limit=64),
        "delegation_mode": _clean_text(payload.get("delegation_mode"), limit=48).lower() or "meta_only",
    }


def _normalize_steps(steps: Iterable[Any] | None) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for raw_step in steps or ():
        step = _normalize_step(raw_step if isinstance(raw_step, Mapping) else {})
        if step["id"] in seen_ids:
            suffix = 2
            base_id = step["id"]
            while f"{base_id}_{suffix}" in seen_ids:
                suffix += 1
            step["id"] = f"{base_id}_{suffix}"
        seen_ids.add(step["id"])
        normalized.append(step)
        if len(normalized) >= 12:
            break
    return normalized


def _normalize_metadata(payload: Mapping[str, Any] | None) -> dict[str, Any]:
    data = dict(payload or {})
    return {
        "task_type": _clean_text(data.get("task_type"), limit=64),
        "site_kind": _clean_text(data.get("site_kind"), limit=64),
        "response_mode": _clean_text(data.get("response_mode"), limit=64),
        "recipe_id": _clean_text(data.get("recipe_id"), limit=64),
        "compiler_mode": _clean_text(data.get("compiler_mode"), limit=48),
        "recipe_stage_count": _normalize_int(data.get("recipe_stage_count"), default=0),
        "step_count": _normalize_int(data.get("step_count"), default=0),
    }


def _normalize_plan(
    *,
    plan_id: Any = "",
    source_query: Any = "",
    goal: Any = "",
    summary: Any = "",
    intent_family: Any = "",
    planning_needed: Any = False,
    plan_mode: Any = "",
    goal_satisfaction_mode: Any = "",
    constraints: Mapping[str, Any] | None = None,
    agent_chain: Iterable[Any] | None = None,
    steps: Iterable[Any] | None = None,
    next_step_id: Any = "",
    blocked_by: Iterable[Any] | None = None,
    status: Any = "",
    last_completed_step_id: Any = "",
    last_completed_step_title: Any = "",
    metadata: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    normalized_plan_mode = _clean_text(plan_mode, limit=48).lower() or "direct_response"
    if normalized_plan_mode not in _VALID_PLAN_MODES:
        normalized_plan_mode = "direct_response"

    normalized_steps = _normalize_steps(steps)
    normalized_next_step_id = _clean_text(next_step_id, limit=64).lower().replace(" ", "_")
    if normalized_steps and not normalized_next_step_id:
        normalized_next_step_id = normalized_steps[0]["id"]

    return {
        "schema_version": META_EXECUTION_PLAN_SCHEMA_VERSION,
        "plan_id": _clean_text(plan_id, limit=64),
        "source_query": _clean_text(source_query, limit=400),
        "goal": _clean_text(goal, limit=280),
        "summary": _clean_text(summary, limit=220),
        "intent_family": _clean_text(intent_family, limit=48).lower() or "single_step",
        "planning_needed": bool(planning_needed),
        "plan_mode": normalized_plan_mode,
        "goal_satisfaction_mode": _clean_text(goal_satisfaction_mode, limit=64)
        or "answer_or_artifact_ready",
        "constraints": _normalize_constraints(constraints),
        "agent_chain": _normalize_text_list(agent_chain, limit_items=8, limit_chars=48),
        "steps": normalized_steps,
        "next_step_id": normalized_next_step_id,
        "blocked_by": _normalize_text_list(blocked_by, limit_items=6, limit_chars=96),
        "status": _clean_text(status, limit=32).lower() or ("completed" if not normalized_steps else "active"),
        "last_completed_step_id": _clean_text(last_completed_step_id, limit=64).lower().replace(" ", "_"),
        "last_completed_step_title": _clean_text(last_completed_step_title, limit=180),
        "metadata": _normalize_metadata(metadata),
    }


def _fallback_policy_from_handoff(handoff: Mapping[str, Any], source_query: str) -> dict[str, Any]:
    recipe_stages = list(handoff.get("recipe_stages") or [])
    return {
        "task_type": handoff.get("task_type"),
        "site_kind": handoff.get("site_kind"),
        "response_mode": handoff.get("response_mode"),
        "action_count": max(len(recipe_stages), 1 if source_query else 0),
        "capability_count": len(list(handoff.get("required_capabilities") or [])),
        "recommended_agent_chain": list(handoff.get("recommended_agent_chain") or []),
        "route_to_meta": True,
        "recommended_recipe_id": handoff.get("recommended_recipe_id"),
    }


def _derive_plan_mode(
    *,
    planning_needed: bool,
    intent_family: str,
    recipe_stages: list[dict[str, Any]],
) -> str:
    if intent_family == "plan_only":
        return "plan_only"
    if recipe_stages or planning_needed:
        return "multi_step_execution"
    if intent_family in {"research", "single_step"}:
        return "lightweight_lookup"
    return "direct_response"


def _extract_keywords(*values: Any) -> set[str]:
    keywords: set[str] = set()
    for value in values:
        for token in re.findall(r"[a-z0-9_]{4,}", str(value or "").lower()):
            keywords.add(token)
    return keywords


def _infer_step_kind_from_stage(stage: Mapping[str, Any]) -> str:
    agent = _clean_text(stage.get("agent"), limit=48).lower()
    stage_id = _clean_text(stage.get("stage_id"), limit=64).lower()
    if agent in {"document", "communication"}:
        return "delivery"
    if "verify" in stage_id or "validation" in stage_id or "check" in stage_id:
        return "verification"
    if agent == "research":
        return "research"
    if agent == "meta":
        return "plan"
    if agent in {"visual", "executor", "shell", "system", "development"}:
        return "execution"
    return "generic"


def _infer_agent_for_subtask(subtask: Mapping[str, Any], handoff: Mapping[str, Any]) -> str:
    kind = _clean_text(subtask.get("kind"), limit=48).lower()
    task_type = _clean_text(handoff.get("task_type"), limit=64).lower()
    site_kind = _clean_text(handoff.get("site_kind"), limit=64).lower()
    chain = [
        _clean_text(item, limit=48).lower()
        for item in handoff.get("recommended_agent_chain") or []
        if _clean_text(item, limit=48)
    ]

    if kind in {"analysis", "plan"}:
        return "meta"
    if kind == "research":
        return "research" if "research" in chain else ("executor" if "executor" in chain else "meta")
    if kind == "delivery":
        if "document" in chain:
            return "document"
        if "communication" in chain:
            return "communication"
        return "meta"
    if kind == "verification":
        if "research" in chain and any(token in task_type for token in {"research", "youtube", "content"}):
            return "research"
        return "meta"
    if kind in {"setup", "execution"}:
        if "visual" in chain and site_kind in {"web", "youtube", "x", "linkedin", "maps"}:
            return "visual"
        for candidate in ("executor", "development", "shell", "system", "research", "visual"):
            if candidate in chain:
                return candidate
    if kind == "response":
        for candidate in chain:
            if candidate != "meta":
                return candidate
    return "meta"


def _score_stage_match(
    *,
    subtask: Mapping[str, Any],
    stage: Mapping[str, Any],
    handoff: Mapping[str, Any],
) -> int:
    score = 0
    step_kind = _infer_step_kind_from_stage(stage)
    subtask_kind = _clean_text(subtask.get("kind"), limit=48).lower()
    if step_kind == subtask_kind:
        score += 5
    if _infer_agent_for_subtask(subtask, handoff) == _clean_text(stage.get("agent"), limit=48).lower():
        score += 3

    subtask_keywords = _extract_keywords(subtask.get("id"), subtask.get("title"), subtask.get("completion_signals"))
    stage_keywords = _extract_keywords(stage.get("stage_id"), stage.get("goal"), stage.get("expected_output"))
    overlap = subtask_keywords.intersection(stage_keywords)
    score += min(len(overlap), 3)

    if subtask_kind in {"execution", "setup"} and _clean_text(stage.get("agent"), limit=48).lower() in {
        "visual",
        "executor",
        "shell",
        "system",
        "development",
    }:
        score += 2
    if subtask_kind == "delivery" and _clean_text(stage.get("agent"), limit=48).lower() in {"document", "communication"}:
        score += 2
    return score


def _select_best_subtask(
    *,
    stage: Mapping[str, Any],
    subtasks: list[dict[str, Any]],
    handoff: Mapping[str, Any],
    used_subtask_ids: set[str],
) -> dict[str, Any] | None:
    best_subtask: dict[str, Any] | None = None
    best_score = 0
    for subtask in subtasks:
        subtask_id = _clean_text(subtask.get("id"), limit=64)
        if not subtask_id or subtask_id in used_subtask_ids:
            continue
        score = _score_stage_match(subtask=subtask, stage=stage, handoff=handoff)
        if score > best_score:
            best_score = score
            best_subtask = subtask
    if best_score <= 0:
        return None
    return best_subtask


def _build_recipe_stage_steps(
    *,
    handoff: Mapping[str, Any],
    subtasks: list[dict[str, Any]],
    used_subtask_ids: set[str],
) -> list[dict[str, Any]]:
    steps: list[dict[str, Any]] = []
    previous_step_id = ""
    for index, raw_stage in enumerate(handoff.get("recipe_stages") or (), start=1):
        stage = dict(raw_stage or {})
        stage_id = _clean_text(stage.get("stage_id"), limit=64).lower() or f"recipe_stage_{index}"
        matched_subtask = _select_best_subtask(
            stage=stage,
            subtasks=subtasks,
            handoff=handoff,
            used_subtask_ids=used_subtask_ids,
        )
        if matched_subtask:
            used_subtask_ids.add(_clean_text(matched_subtask.get("id"), limit=64))
        completion_signals = _normalize_text_list(
            (matched_subtask or {}).get("completion_signals"),
            limit_items=8,
            limit_chars=96,
        )
        if not completion_signals:
            completion_signals = _normalize_text_list([stage.get("expected_output"), "stage_completed"])
        steps.append(
            {
                "id": stage_id,
                "title": _clean_text(
                    (matched_subtask or {}).get("title") or stage.get("goal") or stage.get("expected_output") or stage_id,
                    limit=160,
                ),
                "step_kind": _clean_text(
                    (matched_subtask or {}).get("kind") or _infer_step_kind_from_stage(stage),
                    limit=48,
                ).lower()
                or "generic",
                "assigned_agent": _clean_text(stage.get("agent"), limit=48).lower() or "meta",
                "status": "pending",
                "depends_on": [previous_step_id] if previous_step_id else [],
                "optional": bool(stage.get("optional")),
                "completion_signals": completion_signals,
                "recipe_stage_id": stage_id,
                "expected_output": _clean_text(stage.get("expected_output"), limit=160),
                "source_subtask_id": _clean_text((matched_subtask or {}).get("id"), limit=64),
                "delegation_mode": "recipe_stage",
            }
        )
        previous_step_id = stage_id
    return steps


def _build_subtask_only_steps(
    *,
    handoff: Mapping[str, Any],
    subtasks: list[dict[str, Any]],
    used_subtask_ids: set[str],
) -> list[dict[str, Any]]:
    steps: list[dict[str, Any]] = []
    previous_step_id = ""
    for subtask in subtasks:
        subtask_id = _clean_text(subtask.get("id"), limit=64)
        if not subtask_id or subtask_id in used_subtask_ids:
            continue
        step_id = f"plan_{subtask_id}"
        steps.append(
            {
                "id": step_id,
                "title": _clean_text(subtask.get("title"), limit=160),
                "step_kind": _clean_text(subtask.get("kind"), limit=48).lower() or "generic",
                "assigned_agent": _infer_agent_for_subtask(subtask, handoff),
                "status": "pending",
                "depends_on": [f"plan_{dep}" for dep in (subtask.get("depends_on") or []) if _clean_text(dep, limit=64)]
                or ([previous_step_id] if previous_step_id and not (subtask.get("depends_on") or []) else []),
                "optional": bool(subtask.get("optional")),
                "completion_signals": _normalize_text_list(subtask.get("completion_signals"), limit_items=8, limit_chars=96)
                or ["step_completed"],
                "recipe_stage_id": "",
                "expected_output": "",
                "source_subtask_id": subtask_id,
                "delegation_mode": "meta_only",
            }
        )
        previous_step_id = step_id
    return steps


def _inject_plan_only_steps(
    *,
    handoff: Mapping[str, Any],
    subtasks: list[dict[str, Any]],
    steps: list[dict[str, Any]],
    used_subtask_ids: set[str],
) -> list[dict[str, Any]]:
    if not steps:
        return _build_subtask_only_steps(handoff=handoff, subtasks=subtasks, used_subtask_ids=used_subtask_ids)

    prefix_steps: list[dict[str, Any]] = []
    suffix_steps: list[dict[str, Any]] = []
    delivery_insert_index: int | None = None
    for index, step in enumerate(steps):
        if step["step_kind"] == "delivery" or step["assigned_agent"] in {"document", "communication"}:
            delivery_insert_index = index
            break

    last_existing_id = steps[-1]["id"]
    previous_prefix_id = ""
    for subtask in subtasks:
        subtask_id = _clean_text(subtask.get("id"), limit=64)
        if not subtask_id or subtask_id in used_subtask_ids:
            continue
        subtask_kind = _clean_text(subtask.get("kind"), limit=48).lower()
        base_step = {
            "id": f"plan_{subtask_id}",
            "title": _clean_text(subtask.get("title"), limit=160),
            "step_kind": subtask_kind or "generic",
            "assigned_agent": _infer_agent_for_subtask(subtask, handoff),
            "status": "pending",
            "depends_on": [f"plan_{dep}" for dep in (subtask.get("depends_on") or []) if _clean_text(dep, limit=64)],
            "optional": bool(subtask.get("optional")),
            "completion_signals": _normalize_text_list(subtask.get("completion_signals"), limit_items=8, limit_chars=96)
            or ["step_completed"],
            "recipe_stage_id": "",
            "expected_output": "",
            "source_subtask_id": subtask_id,
            "delegation_mode": "meta_only",
        }
        if subtask_kind in {"analysis", "plan"}:
            if not base_step["depends_on"] and previous_prefix_id:
                base_step["depends_on"] = [previous_prefix_id]
            previous_prefix_id = base_step["id"]
            prefix_steps.append(base_step)
        elif subtask_kind == "verification" and delivery_insert_index is not None:
            anchor_step_id = steps[max(delivery_insert_index - 1, 0)]["id"]
            base_step["depends_on"] = base_step["depends_on"] or [anchor_step_id]
            suffix_steps.insert(0, base_step)
        else:
            base_step["depends_on"] = base_step["depends_on"] or [last_existing_id]
            suffix_steps.append(base_step)
    if prefix_steps:
        first_step_id = steps[0]["id"]
        for step in steps:
            if not step["depends_on"]:
                step["depends_on"] = [prefix_steps[-1]["id"]]
                break
        if prefix_steps[-1]["id"] == first_step_id:
            prefix_steps[-1]["id"] = f"{prefix_steps[-1]['id']}_plan"
    if suffix_steps and delivery_insert_index is not None:
        steps = steps[:delivery_insert_index] + suffix_steps + steps[delivery_insert_index:]
    else:
        steps = steps + suffix_steps
    return prefix_steps + steps


def build_meta_execution_plan(
    *,
    source_query: Any = "",
    handoff_payload: Mapping[str, Any] | None = None,
    task_decomposition: Mapping[str, Any] | str | None = None,
) -> dict[str, Any]:
    """Compile an explicit execution plan for Meta from decomposition and recipe data."""

    handoff = dict(handoff_payload or {})
    normalized_source_query = _clean_text(
        source_query or handoff.get("original_user_task") or "",
        limit=400,
    )
    decomposition = parse_task_decomposition(
        task_decomposition or handoff.get("task_decomposition") or {}
    )
    if not decomposition:
        decomposition = build_task_decomposition(
            source_query=normalized_source_query,
            orchestration_policy=_fallback_policy_from_handoff(handoff, normalized_source_query),
        )

    subtasks = [dict(item) for item in decomposition.get("subtasks") or []]
    used_subtask_ids: set[str] = set()
    recipe_steps = _build_recipe_stage_steps(
        handoff=handoff,
        subtasks=subtasks,
        used_subtask_ids=used_subtask_ids,
    )
    steps = _inject_plan_only_steps(
        handoff=handoff,
        subtasks=subtasks,
        steps=recipe_steps,
        used_subtask_ids=used_subtask_ids,
    )
    if not steps:
        steps = _build_subtask_only_steps(
            handoff=handoff,
            subtasks=subtasks,
            used_subtask_ids=used_subtask_ids,
        )

    normalized_steps = _normalize_steps(steps)
    next_step_id = normalized_steps[0]["id"] if normalized_steps else ""
    intent_family = _clean_text(decomposition.get("intent_family"), limit=48).lower() or "single_step"
    planning_needed = bool(decomposition.get("planning_needed"))
    plan_mode = _derive_plan_mode(
        planning_needed=planning_needed,
        intent_family=intent_family,
        recipe_stages=list(handoff.get("recipe_stages") or []),
    )
    agent_chain = list(handoff.get("recommended_agent_chain") or [])
    plan_id = _clean_text(
        decomposition.get("request_id")
        or f"{handoff.get('task_type') or 'task'}:{handoff.get('recommended_recipe_id') or plan_mode}:{len(normalized_steps)}",
        limit=64,
    ).replace(" ", "_")

    return _normalize_plan(
        plan_id=plan_id,
        source_query=normalized_source_query,
        goal=decomposition.get("goal") or normalized_source_query,
        summary=(
            f"{plan_mode} ueber {len(normalized_steps)} Schritte fuer {intent_family}"
            if normalized_steps
            else f"{plan_mode} ohne explizite Schritte"
        ),
        intent_family=intent_family,
        planning_needed=planning_needed,
        plan_mode=plan_mode,
        goal_satisfaction_mode=decomposition.get("goal_satisfaction_mode"),
        constraints=decomposition.get("constraints"),
        agent_chain=agent_chain,
        steps=normalized_steps,
        next_step_id=next_step_id,
        blocked_by=[],
        status="active" if normalized_steps else "completed",
        metadata={
            "task_type": handoff.get("task_type"),
            "site_kind": handoff.get("site_kind"),
            "response_mode": handoff.get("response_mode"),
            "recipe_id": handoff.get("recommended_recipe_id"),
            "compiler_mode": "recipe_enriched" if handoff.get("recipe_stages") else "decomposition_only",
            "recipe_stage_count": len(list(handoff.get("recipe_stages") or [])),
            "step_count": len(normalized_steps),
        },
    )


def parse_meta_execution_plan(raw: Any) -> dict[str, Any]:
    if isinstance(raw, Mapping):
        if not raw:
            return {}
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

    normalized = _normalize_plan(
        plan_id=loaded.get("plan_id"),
        source_query=loaded.get("source_query"),
        goal=loaded.get("goal"),
        summary=loaded.get("summary"),
        intent_family=loaded.get("intent_family"),
        planning_needed=loaded.get("planning_needed"),
        plan_mode=loaded.get("plan_mode"),
        goal_satisfaction_mode=loaded.get("goal_satisfaction_mode"),
        constraints=loaded.get("constraints"),
        agent_chain=loaded.get("agent_chain"),
        steps=loaded.get("steps"),
        next_step_id=loaded.get("next_step_id"),
        blocked_by=loaded.get("blocked_by"),
        status=loaded.get("status"),
        last_completed_step_id=loaded.get("last_completed_step_id"),
        last_completed_step_title=loaded.get("last_completed_step_title"),
        metadata=loaded.get("metadata"),
    )
    if not any(
        [
            normalized.get("plan_id"),
            normalized.get("source_query"),
            normalized.get("goal"),
            normalized.get("summary"),
            normalized.get("steps"),
            normalized.get("agent_chain"),
            normalized.get("planning_needed"),
            (normalized.get("metadata") or {}).get("task_type"),
            (normalized.get("metadata") or {}).get("recipe_id"),
        ]
    ):
        return {}
    return normalized
