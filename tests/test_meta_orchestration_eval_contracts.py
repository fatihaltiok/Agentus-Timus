from __future__ import annotations

import deal

from orchestration.meta_orchestration_eval import evaluate_meta_orchestration_case, evaluate_meta_replan_case


@deal.post(lambda r: 0.0 <= float(r.get("score", 0.0)) <= 1.0)
@deal.post(
    lambda r: 0.0 <= float((r.get("benchmark", {}) or {}).get("capability_score", 0.0)) <= 1.0
)
@deal.post(lambda r: isinstance((r.get("decision", {}) or {}).get("recommended_agent_chain", []), list))
def _contract_evaluate_meta_orchestration_case(case: dict) -> dict:
    raw_chain = (case or {}).get("expected_agent_chain", [])
    safe_chain = raw_chain if isinstance(raw_chain, list) else []
    raw_capabilities = (case or {}).get("expected_capabilities", [])
    safe_capabilities = raw_capabilities if isinstance(raw_capabilities, list) else []
    normalized = {
        "name": str((case or {}).get("name", "") or ""),
        "query": str((case or {}).get("query", "") or ""),
        "expected_route_to_meta": bool((case or {}).get("expected_route_to_meta", False)),
        "expected_task_type": str((case or {}).get("expected_task_type", "") or ""),
        "expected_entry_agent": str((case or {}).get("expected_entry_agent", "") or ""),
        "expected_agent_chain": [str(item) for item in safe_chain],
        "expected_recipe_id": None
        if (case or {}).get("expected_recipe_id") is None
        else str((case or {}).get("expected_recipe_id", "") or ""),
        "expected_structured_handoff": bool((case or {}).get("expected_structured_handoff", False)),
        "expected_capabilities": [str(item) for item in safe_capabilities],
    }
    return evaluate_meta_orchestration_case(normalized)


@deal.post(lambda r: 0.0 <= float(r.get("score", 0.0)) <= 1.0)
@deal.post(lambda r: isinstance(str(r.get("initial_recipe_id", "") or ""), str))
@deal.post(lambda r: isinstance(str(r.get("replanned_recipe_id", "") or ""), str))
def _contract_evaluate_meta_replan_case(case: dict) -> dict:
    runtime = (case or {}).get("runtime_constraints", {})
    safe_runtime = runtime if isinstance(runtime, dict) else {}
    learning = (case or {}).get("learning_snapshot", {})
    safe_learning = learning if isinstance(learning, dict) else {}
    failed_stage = (case or {}).get("failed_stage", {})
    safe_failed_stage = failed_stage if isinstance(failed_stage, dict) else {}
    alt_scores = (case or {}).get("alternative_recipe_scores", [])
    safe_alt_scores = alt_scores if isinstance(alt_scores, list) else []
    normalized = {
        "name": str((case or {}).get("name", "") or ""),
        "query": str((case or {}).get("query", "") or ""),
        "runtime_constraints": dict(safe_runtime),
        "learning_snapshot": dict(safe_learning),
        "failed_stage": dict(safe_failed_stage),
        "alternative_recipe_scores": list(safe_alt_scores),
        "expected_initial_recipe": str((case or {}).get("expected_initial_recipe", "") or ""),
        "expected_replan_recipe": str((case or {}).get("expected_replan_recipe", "") or ""),
    }
    return evaluate_meta_replan_case(normalized)
