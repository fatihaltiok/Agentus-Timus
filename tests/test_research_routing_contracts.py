from __future__ import annotations

import deal

from orchestration.meta_orchestration import classify_meta_task
from orchestration.orchestration_policy import evaluate_query_orchestration


@deal.post(lambda r: r["task_type"] == "knowledge_research")
@deal.post(lambda r: r["recommended_entry_agent"] == "meta")
@deal.post(lambda r: r["recommended_agent_chain"] == ["meta", "research"])
def broad_research_routes_via_meta() -> dict:
    return classify_meta_task("Recherchiere KI-Agenten fuer Unternehmen", action_count=1)


@deal.post(lambda r: r["task_type"] == "knowledge_research")
@deal.post(lambda r: r["recommended_entry_agent"] == "research")
@deal.post(lambda r: r["recommended_agent_chain"] == ["research"])
def strict_research_stays_direct() -> dict:
    return classify_meta_task(
        "Recherchiere aktuelle Entwicklungen zu KI-Agenten mit Quellen und Studien",
        action_count=1,
    )


@deal.post(lambda r: r["route_to_meta"] is True)
@deal.post(lambda r: r["recommended_agent_chain"] == ["meta", "research"])
def broad_policy_routes_to_meta() -> dict:
    return evaluate_query_orchestration("Recherchiere KI-Agenten fuer Unternehmen")
