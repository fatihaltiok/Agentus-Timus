"""GDK5 unseen evaluation matrix for the general decision kernel."""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Mapping

from orchestration.general_decision_kernel import build_general_decision_kernel


GDK5_UNSEEN_EVAL_CASES: List[Dict[str, Any]] = [
    {
        "name": "planning_day_structure",
        "query": "Plane meinen Tag mit Fokus auf Lernen und Erholung",
        "kernel_input": {
            "meta_request_frame": {
                "frame_kind": "new_task",
                "task_domain": "planning_advisory",
                "execution_mode": "plan_and_delegate",
                "confidence": 0.88,
            },
            "meta_interaction_mode": {"mode": "assist"},
        },
        "expected_kernel": {
            "turn_kind": "execute",
            "topic_family": "planning",
            "interaction_mode": "assist",
            "evidence_requirement": "task_dependent",
            "execution_permission": "forbidden",
            "min_confidence": 0.75,
        },
        "expected_meta": {
            "task_domain": "planning_advisory",
            "recommended_agent_chain": ["meta"],
            "low_confidence_active": False,
            "authority_execution_permission": "forbidden",
        },
    },
    {
        "name": "free_opinion_think_partner",
        "query": "Was ist deine Meinung dazu, dass kleine lokale Modelle durch gute Architektur stark werden?",
        "expected_kernel": {
            "turn_kind": "think",
            "interaction_mode": "think_partner",
            "evidence_requirement": "none",
            "execution_permission": "forbidden",
            "min_confidence": 0.75,
        },
        "expected_meta": {
            "task_domain": "topic_advisory",
            "recommended_agent_chain": ["meta"],
            "response_mode": "summarize_state",
            "low_confidence_active": False,
            "authority_execution_permission": "forbidden",
            "authority_working_memory_query_mode": "objective_only",
            "forbidden_context_classes_includes": ["semantic_recall", "document_knowledge"],
        },
    },
    {
        "name": "personal_decision_support",
        "query": "Hilf mir bei einer Entscheidung zwischen Job A und Job B",
        "kernel_input": {
            "meta_request_frame": {
                "frame_kind": "new_task",
                "task_domain": "life_advisory",
                "execution_mode": "plan_and_delegate",
                "confidence": 0.82,
            },
            "meta_interaction_mode": {"mode": "think_partner"},
        },
        "expected_kernel": {
            "turn_kind": "think",
            "topic_family": "personal_productivity",
            "interaction_mode": "think_partner",
            "evidence_requirement": "none",
            "execution_permission": "forbidden",
            "min_confidence": 0.75,
        },
        "expected_meta": {
            "task_domain": "life_advisory",
            "recommended_agent_chain": ["meta"],
            "low_confidence_active": False,
            "authority_execution_permission": "forbidden",
            "authority_working_memory_query_mode": "objective_only",
        },
    },
    {
        "name": "deep_research_then_support",
        "query": "Mach dich schlau über Quantenbatterien und hilf mir danach",
        "expected_kernel": {
            "turn_kind": "research",
            "topic_family": "general_knowledge",
            "interaction_mode": "inspect",
            "evidence_requirement": "research",
            "execution_permission": "bounded",
            "min_confidence": 0.8,
        },
        "expected_meta": {
            "task_domain": "research_advisory",
            "recommended_agent_chain": ["meta", "executor"],
            "low_confidence_active": False,
            "authority_execution_permission": "bounded",
            "authority_working_memory_query_mode": "evidence_bound",
        },
    },
    {
        "name": "bounded_inspect_preparation",
        "query": "Prüf das kurz: ob wir schon einen PDF Import vorbereitet haben",
        "expected_kernel": {
            "turn_kind": "inspect",
            "interaction_mode": "inspect",
            "evidence_requirement": "bounded",
            "execution_permission": "bounded",
            "min_confidence": 0.75,
        },
        "expected_meta": {
            "task_domain": "document_generation",
            "recommended_agent_chain": ["meta", "document"],
            "low_confidence_active": False,
            "authority_execution_permission": "bounded",
            "authority_working_memory_query_mode": "evidence_bound",
        },
    },
    {
        "name": "docs_next_step",
        "query": "Lies die Doku und sag was als nächstes ansteht",
        "kernel_input": {
            "meta_request_frame": {
                "frame_kind": "direct_answer",
                "task_domain": "docs_status",
                "execution_mode": "answer_directly",
                "confidence": 0.96,
            },
            "meta_interaction_mode": {"mode": "inspect"},
        },
        "expected_kernel": {
            "turn_kind": "inspect",
            "topic_family": "document",
            "interaction_mode": "inspect",
            "evidence_requirement": "bounded",
            "execution_permission": "bounded",
            "min_confidence": 0.9,
        },
        "expected_meta": {
            "task_domain": "docs_status",
            "recommended_agent_chain": ["meta"],
            "low_confidence_active": False,
            "authority_execution_permission": "bounded",
            "authority_working_memory_query_mode": "evidence_bound",
        },
    },
    {
        "name": "open_travel_weekend",
        "query": "Wo kann ich am Wochenende hin in Deutschland",
        "kernel_input": {
            "meta_request_frame": {
                "frame_kind": "clarify_needed",
                "task_domain": "travel_advisory",
                "execution_mode": "clarify_once",
                "confidence": 0.86,
            },
            "meta_interaction_mode": {"mode": "think_partner"},
        },
        "expected_kernel": {
            "turn_kind_in": ["think", "clarify"],
            "topic_family": "travel",
            "interaction_mode": "think_partner",
            "evidence_requirement": "none",
            "execution_permission": "forbidden",
            "min_confidence": 0.75,
        },
        "expected_meta": {
            "task_domain": "travel_advisory",
            "recommended_agent_chain": ["meta"],
            "low_confidence_active": False,
            "authority_execution_permission": "forbidden",
        },
    },
    {
        "name": "research_followup_meaning",
        "query": "Und was bedeutet das für mich?",
        "conversation_state": {
            "active_topic": "Quantenbatterien",
            "active_goal": "Verstehen, ob Quantenbatterien relevant fuer mein Projekt sind",
            "active_domain": "research_advisory",
            "open_loop": "Thema wurde recherchiert",
            "next_expected_step": "Einordnung fuer Nutzer geben",
            "turn_type_hint": "followup",
            "topic_confidence": 0.82,
        },
        "recent_user_turns": ["Mach dich schlau über Quantenbatterien und hilf mir danach"],
        "recent_assistant_turns": ["Ich habe die wichtigsten Punkte zu Quantenbatterien gesammelt."],
        "expected_kernel": {
            "turn_kind": "think",
            "interaction_mode": "think_partner",
            "evidence_requirement": "none",
            "execution_permission": "forbidden",
            "min_confidence": 0.75,
        },
        "expected_meta": {
            "task_domain": "research_advisory",
            "active_domain": "research_advisory",
            "recommended_agent_chain": ["meta"],
            "low_confidence_active": False,
            "authority_execution_permission": "forbidden",
            "authority_working_memory_query_mode": "objective_only",
        },
    },
    {
        "name": "skill_creation_execution",
        "query": "Erstelle einen Skill für PDF-Zusammenfassungen",
        "kernel_input": {
            "meta_request_frame": {
                "frame_kind": "new_task",
                "task_domain": "skill_creation",
                "execution_mode": "plan_and_delegate",
                "confidence": 0.93,
            },
            "meta_interaction_mode": {"mode": "assist"},
        },
        "expected_kernel": {
            "turn_kind": "execute",
            "topic_family": "technical",
            "interaction_mode": "assist",
            "evidence_requirement": "task_dependent",
            "execution_permission": "allowed",
            "min_confidence": 0.85,
        },
        "expected_meta": {
            "task_domain": "skill_creation",
            "recommended_agent_chain": ["meta"],
            "low_confidence_active": False,
            "authority_execution_permission": "allowed",
        },
    },
    {
        "name": "feature_build_execution",
        "query": "Baue eine neue Funktion für Termin-Erinnerungen",
        "kernel_input": {
            "meta_request_frame": {
                "frame_kind": "new_task",
                "task_domain": "setup_build",
                "execution_mode": "plan_and_delegate",
                "confidence": 0.93,
            },
            "meta_interaction_mode": {"mode": "assist"},
        },
        "expected_kernel": {
            "turn_kind": "execute",
            "topic_family": "technical",
            "interaction_mode": "assist",
            "evidence_requirement": "task_dependent",
            "execution_permission": "allowed",
            "min_confidence": 0.85,
        },
        "expected_meta": {
            "task_domain": "setup_build",
            "recommended_agent_chain": ["meta", "executor"],
            "low_confidence_active": False,
            "authority_execution_permission": "allowed",
        },
    },
    {
        "name": "unclear_action_fails_small",
        "query": "mach das mal",
        "kernel_input": {
            "meta_request_frame": {
                "frame_kind": "clarify_needed",
                "task_domain": "topic_advisory",
                "execution_mode": "clarify_once",
                "confidence": 0.82,
            },
            "meta_interaction_mode": {"mode": "think_partner"},
        },
        "expected_kernel": {
            "turn_kind": "clarify",
            "interaction_mode": "think_partner",
            "evidence_requirement": "none",
            "execution_permission": "forbidden",
            "min_confidence": 0.75,
        },
        "expected_meta": {
            "task_domain": "topic_advisory",
            "recommended_agent_chain": ["meta"],
            "response_mode": "clarify_before_execute",
            "low_confidence_active": False,
            "authority_execution_permission": "forbidden",
        },
    },
    {
        "name": "current_live_lookup",
        "query": "Schau nach aktuellen EU KI-Regeln",
        "expected_kernel": {
            "turn_kind": "inspect",
            "interaction_mode": "inspect",
            "evidence_requirement": "bounded",
            "execution_permission": "bounded",
            "min_confidence": 0.75,
        },
        "expected_meta": {
            "task_domain": "topic_advisory",
            "recommended_agent_chain": ["meta"],
            "low_confidence_active": False,
            "authority_execution_permission": "bounded",
            "authority_working_memory_query_mode": "evidence_bound",
        },
    },
]


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    if isinstance(value, set):
        return sorted(value)
    if value in (None, ""):
        return []
    return [value]


def _matches_expected(actual: Any, expected: Any) -> bool:
    if isinstance(expected, tuple):
        return actual in expected
    if isinstance(expected, set):
        return actual in expected
    return actual == expected


def score_gdk5_expectations(actual: Mapping[str, Any], expected: Mapping[str, Any]) -> Dict[str, Any]:
    checks: Dict[str, bool] = {}
    for raw_key, expected_value in dict(expected or {}).items():
        key = str(raw_key or "")
        if not key:
            continue
        if key.startswith("min_"):
            actual_key = key[4:]
            try:
                checks[key] = float(actual.get(actual_key) or 0.0) >= float(expected_value)
            except (TypeError, ValueError):
                checks[key] = False
            continue
        if key.endswith("_in"):
            actual_key = key[:-3]
            checks[key] = actual.get(actual_key) in set(_as_list(expected_value))
            continue
        if key.endswith("_includes"):
            actual_key = key[: -len("_includes")]
            actual_values = set(_as_list(actual.get(actual_key)))
            checks[key] = set(_as_list(expected_value)).issubset(actual_values)
            continue
        checks[key] = _matches_expected(actual.get(key), expected_value)

    passed = sum(1 for value in checks.values() if value)
    total = len(checks)
    score = 1.0 if total <= 0 else round(max(0.0, min(1.0, passed / total)), 3)
    return {
        "checks": checks,
        "passed": total == passed,
        "passed_checks": passed,
        "total_checks": total,
        "score": score,
    }


def build_gdk5_kernel_input(case: Mapping[str, Any]) -> Dict[str, Any]:
    kernel_input = dict(case.get("kernel_input") or {})
    return {
        "effective_query": str(case.get("query") or ""),
        **kernel_input,
    }


def flatten_gdk5_kernel(kernel: Mapping[str, Any]) -> Dict[str, Any]:
    return {
        "turn_kind": str(kernel.get("turn_kind") or ""),
        "topic_family": str(kernel.get("topic_family") or ""),
        "interaction_mode": str(kernel.get("interaction_mode") or ""),
        "evidence_requirement": str(kernel.get("evidence_requirement") or ""),
        "execution_permission": str(kernel.get("execution_permission") or ""),
        "confidence": float(kernel.get("confidence") or 0.0),
        "clarify_if_below_threshold": bool(kernel.get("clarify_if_below_threshold")),
        "answer_ready": bool(kernel.get("answer_ready")),
    }


def evaluate_gdk5_kernel_case(case: Mapping[str, Any]) -> Dict[str, Any]:
    kernel = build_general_decision_kernel(**build_gdk5_kernel_input(case)).to_dict()
    actual = flatten_gdk5_kernel(kernel)
    expected = dict(case.get("expected_kernel") or {})
    score = score_gdk5_expectations(actual, expected)
    return {
        "name": str(case.get("name") or ""),
        "query": str(case.get("query") or ""),
        "kernel": kernel,
        "actual": actual,
        "expected": expected,
        **score,
    }


def flatten_gdk5_meta_classification(classification: Mapping[str, Any]) -> Dict[str, Any]:
    frame = dict(classification.get("meta_request_frame") or {})
    kernel = dict(classification.get("general_decision_kernel") or {})
    authority = dict(classification.get("meta_context_authority") or {})
    controller = dict(classification.get("low_confidence_controller") or {})
    return {
        **flatten_gdk5_kernel(kernel),
        "task_domain": str(frame.get("task_domain") or ""),
        "frame_kind": str(frame.get("frame_kind") or ""),
        "active_domain": str(classification.get("active_domain") or ""),
        "recommended_agent_chain": list(classification.get("recommended_agent_chain") or []),
        "response_mode": str(classification.get("response_mode") or ""),
        "low_confidence_active": bool(controller.get("active")),
        "authority_execution_permission": str(authority.get("decision_execution_permission") or ""),
        "authority_working_memory_query_mode": str(authority.get("working_memory_query_mode") or ""),
        "forbidden_context_classes": list(authority.get("forbidden_context_classes") or []),
    }


def evaluate_gdk5_meta_case(case: Mapping[str, Any]) -> Dict[str, Any]:
    from orchestration.meta_orchestration import classify_meta_task

    classification = classify_meta_task(
        str(case.get("query") or ""),
        action_count=0,
        conversation_state=dict(case.get("conversation_state") or {}),
        recent_user_turns=list(case.get("recent_user_turns") or []),
        recent_assistant_turns=list(case.get("recent_assistant_turns") or []),
    )
    actual = flatten_gdk5_meta_classification(classification)
    expected = dict(case.get("expected_meta") or {})
    score = score_gdk5_expectations(actual, expected)
    return {
        "name": str(case.get("name") or ""),
        "query": str(case.get("query") or ""),
        "classification": classification,
        "actual": actual,
        "expected": expected,
        **score,
    }


def summarize_gdk5_results(results: Iterable[Mapping[str, Any]]) -> Dict[str, Any]:
    items = [dict(item) for item in results]
    total = len(items)
    passed = sum(1 for item in items if bool(item.get("passed")))
    return {
        "total": total,
        "passed": passed,
        "failed": max(0, total - passed),
        "score": 1.0 if total <= 0 else round(max(0.0, min(1.0, passed / total)), 3),
        "failed_cases": [str(item.get("name") or "") for item in items if not item.get("passed")],
    }
