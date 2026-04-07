"""Runtime policy for orchestration lanes and safe parallel delegation."""

from __future__ import annotations

import re
from typing import Any, Dict, List

from orchestration.meta_orchestration import classify_meta_task, extract_effective_meta_query
from orchestration.self_selected_strategy import (
    build_task_profile,
    select_strategy,
    select_tool_affordances,
)


_CAPABILITY_KEYWORDS = {
    "research": (
        "recherchiere",
        "recherche",
        "finde heraus",
        "suche nach",
        "informiere mich",
    ),
    "document": (
        "pdf",
        "bericht",
        "dokument",
        "docx",
        "xlsx",
        "exportiere",
        "speichere",
    ),
    "communication": (
        "email",
        "e-mail",
        "mail",
        "sende",
        "schicke",
        "schreibe eine nachricht",
    ),
    "visual": (
        "browser",
        "webseite",
        "website",
        "gehe auf",
        "klicke",
        "tippe",
        "wähle",
        "waehle",
        "formular",
    ),
    "system": (
        "logs",
        "systemstatus",
        "service status",
        "prozesse",
    ),
    "shell": (
        "systemctl",
        "bash",
        "terminal",
        "sudo",
        "skript ausführen",
        "skript ausfuehren",
    ),
    "data": (
        "csv",
        "excel",
        "json",
        "statistik",
        "daten analysieren",
    ),
    "development": (
        "python",
        "code",
        "skript",
        "implementiere",
        "debugge",
    ),
}

_WORKFLOW_CONNECTORS = (
    "danach",
    "anschließend",
    "anschliessend",
    "und dann",
    "im anschluss",
    "abschließend",
    "abschliessend",
)

_DELIVERABLE_CONNECTORS = (
    "und sende",
    "und schicke",
    "und speichere",
    "und erstelle",
    "und exportiere",
    "mit anhang",
)

_LOGIN_MARKERS = (
    "login",
    "log in",
    "sign in",
    "anmelden",
    "einloggen",
    "logge dich ein",
)

_INTERACTIVE_BROWSER_DOMAINS = (
    "booking.com",
    "youtube",
    "youtu.be",
    "x.com",
    "twitter",
    "linkedin",
    "outlook",
    "github.com/login",
)

_DEPENDENCY_PATTERNS = (
    r"\baus schritt\b",
    r"\baus dem ergebnis\b",
    r"\bmit dem ergebnis\b",
    r"\bnutze (?:das|den|die)\b",
    r"\bverwende (?:das|den|die)\b",
    r"\bartifacts?\b",
    r"\bmetadata\b",
    r"\bpdf_filepath\b",
    r"\battachment_path\b",
    r"\bergebnis von\b",
    r"\bresult\[[^\]]+\]",
)


def evaluate_query_orchestration(query: str) -> Dict[str, Any]:
    normalized = extract_effective_meta_query(query).strip().lower()
    capability_hits = {
        capability: [keyword for keyword in keywords if keyword in normalized]
        for capability, keywords in _CAPABILITY_KEYWORDS.items()
    }
    capability_hits = {
        capability: keywords
        for capability, keywords in capability_hits.items()
        if keywords
    }

    action_count = sum(
        1
        for token in (
            "recherchiere",
            "analysiere",
            "erstelle",
            "schreibe",
            "sende",
            "schicke",
            "speichere",
            "suche nach",
            "suche",
            "finde",
            "gib ein",
            "trage",
            "fülle",
            "fuelle",
            "gehe auf",
            "klicke",
            "tippe",
            "wähle",
            "waehle",
            "öffne",
            "oeffne",
        )
        if token in normalized
    )
    dependency_markers = [token for token in _WORKFLOW_CONNECTORS if token in normalized]
    deliverable_markers = [token for token in _DELIVERABLE_CONNECTORS if token in normalized]
    has_login_workflow = any(marker in normalized for marker in _LOGIN_MARKERS) and any(
        token in normalized for token in ("benutzername", "username", "email", "e-mail", "passwort", "password")
    )
    has_interactive_browser_workflow = (
        any(domain in normalized for domain in _INTERACTIVE_BROWSER_DOMAINS)
        and action_count >= 2
    )

    route_to_meta = (
        len(capability_hits) >= 2
        or action_count >= 3
        or bool(dependency_markers)
        or bool(deliverable_markers)
        or has_login_workflow
        or has_interactive_browser_workflow
    )
    meta_task = classify_meta_task(query, action_count=action_count)
    task_profile = build_task_profile(normalized, meta_task)
    tool_affordances = select_tool_affordances(meta_task, task_profile)
    selected_strategy = select_strategy(normalized, meta_task, task_profile, tool_affordances)
    route_to_meta = route_to_meta or meta_task["recommended_entry_agent"] == "meta" or len(
        meta_task["recommended_agent_chain"]
    ) > 1
    return {
        "route_to_meta": route_to_meta,
        "capabilities": sorted(capability_hits.keys()),
        "capability_count": len(capability_hits),
        "action_count": action_count,
        "dependency_markers": dependency_markers,
        "deliverable_markers": deliverable_markers,
        "task_type": meta_task["task_type"],
        "site_kind": meta_task["site_kind"],
        "required_capabilities": meta_task["required_capabilities"],
        "recommended_entry_agent": (
            "meta"
            if route_to_meta and meta_task["recommended_entry_agent"] != "meta"
            else meta_task["recommended_entry_agent"]
        ),
        "recommended_agent_chain": (
            meta_task["recommended_agent_chain"]
            if not route_to_meta or meta_task["recommended_agent_chain"][0] == "meta"
            else ["meta"] + meta_task["recommended_agent_chain"]
        ),
        "needs_structured_handoff": bool(route_to_meta or meta_task["needs_structured_handoff"]),
        "meta_classification_reason": meta_task["reason"],
        "recommended_recipe_id": meta_task.get("recommended_recipe_id"),
        "recipe_stages": list(meta_task.get("recipe_stages") or []),
        "recipe_recoveries": list(meta_task.get("recipe_recoveries") or []),
        "alternative_recipes": list(meta_task.get("alternative_recipes") or []),
        "goal_spec": dict(meta_task.get("goal_spec") or {}),
        "capability_graph": dict(meta_task.get("capability_graph") or {}),
        "adaptive_plan": dict(meta_task.get("adaptive_plan") or {}),
        "meta_context_bundle": dict(meta_task.get("meta_context_bundle") or {}),
        "task_profile": task_profile,
        "tool_affordances": tool_affordances,
        "selected_strategy": selected_strategy,
        "reason": (
            "multi_capability"
            if len(capability_hits) >= 2
            else "workflow_connectors"
            if dependency_markers
            else "deliverable_chain"
            if deliverable_markers
            else "login_workflow"
            if has_login_workflow
            else "interactive_browser_workflow"
            if has_interactive_browser_workflow
            else "multi_action"
            if action_count >= 3
            else "single_lane"
        ),
    }


def evaluate_parallel_tasks(tasks: List[Dict[str, Any]]) -> Dict[str, Any]:
    dependent_task_ids: List[str] = []
    reasons: List[str] = []
    safe_tasks = tasks or []
    if len(safe_tasks) < 2:
        return {
            "allowed": True,
            "policy_state": "allowed",
            "reason": "single_task",
            "dependent_task_ids": [],
            "independent_task_ids": [
                str((task or {}).get("task_id") or f"task-{idx}")
                for idx, task in enumerate(safe_tasks, start=1)
            ],
        }

    for idx, task in enumerate(safe_tasks, start=1):
        text = str((task or {}).get("task", "")).strip().lower()
        task_id = str((task or {}).get("task_id") or f"task-{idx}")
        if any(token in text for token in _WORKFLOW_CONNECTORS):
            dependent_task_ids.append(task_id)
            reasons.append("workflow_connector")
            continue
        if any(token in text for token in _DELIVERABLE_CONNECTORS):
            dependent_task_ids.append(task_id)
            reasons.append("deliverable_chain")
            continue
        if any(re.search(pattern, text) for pattern in _DEPENDENCY_PATTERNS):
            dependent_task_ids.append(task_id)
            reasons.append("explicit_dependency")

    independent_task_ids = [
        str((task or {}).get("task_id") or f"task-{idx}")
        for idx, task in enumerate(safe_tasks, start=1)
        if str((task or {}).get("task_id") or f"task-{idx}") not in dependent_task_ids
    ]
    allowed = not dependent_task_ids
    return {
        "allowed": allowed,
        "policy_state": "allowed" if allowed else "blocked",
        "reason": "independent_tasks" if allowed else reasons[0],
        "dependent_task_ids": dependent_task_ids,
        "independent_task_ids": independent_task_ids,
    }
