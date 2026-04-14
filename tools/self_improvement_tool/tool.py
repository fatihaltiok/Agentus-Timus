"""
tools/self_improvement_tool/tool.py — M12: Self-Improvement MCP-Tools

3 MCP-Tools für die Self-Improvement Engine:
- get_tool_analytics: Tool-Nutzungsstatistiken
- get_routing_stats: Routing-Entscheidungsstatistiken
- get_llm_usage_analytics: Token-/Kostenstatistiken fuer LLM-Calls
- get_llm_budget_status: Budget-Zustaende und Schwellwerte
- get_ops_observability: zentrale Ops-Zusammenfassung
- get_e2e_regression_matrix: produktionskritische Kernflows als Matrix
- get_e2e_release_gate_status: Eskalations- und Canary/Release-Entscheidung aus E2E
- get_improvement_suggestions: Verbesserungsvorschläge
"""

import logging
import os

from tools.tool_registry_v2 import tool, ToolParameter as P, ToolCategory as C

log = logging.getLogger("self_improvement_tool")


def _safe_engine_stat(engine, method_name: str, *, default, **kwargs):
    method = getattr(engine, method_name, None)
    if method is None:
        return default
    try:
        return method(**kwargs)
    except Exception:
        return default


@tool(
    name="get_tool_analytics",
    description=(
        "Gibt Statistiken zur Tool-Nutzung zurück: Erfolgsraten, Laufzeiten "
        "und Häufigkeiten pro Tool und Agent. Hilft Bottlenecks zu identifizieren."
    ),
    parameters=[
        P("agent", "string",  "Agenten-Filter (leer = alle Agenten)", required=False, default=""),
        P("days",  "integer", "Analysezeitraum in Tagen (default: 7)", required=False, default=7),
    ],
    capabilities=["analysis", "system"],
    category=C.SYSTEM,
)
async def get_tool_analytics(agent: str = "", days: int = 7) -> dict:
    """Gibt Tool-Nutzungsstatistiken zurück."""
    from orchestration.self_improvement_engine import get_improvement_engine

    stats = get_improvement_engine().get_tool_stats(
        agent=agent if agent else None,
        days=max(1, min(90, days)),
    )
    return {
        "status": "ok",
        "agent_filter": agent or "all",
        "days": days,
        "count": len(stats),
        "stats": stats,
    }


@tool(
    name="get_routing_stats",
    description=(
        "Gibt Routing-Statistiken zurück: Welcher Agent wie oft gewählt wurde, "
        "durchschnittliche Konfidenz und Erfolgsrate."
    ),
    parameters=[
        P("days", "integer", "Analysezeitraum in Tagen (default: 7)", required=False, default=7),
    ],
    capabilities=["analysis", "system"],
    category=C.SYSTEM,
)
async def get_routing_stats(days: int = 7) -> dict:
    """Gibt Routing-Statistiken zurück."""
    from orchestration.self_improvement_engine import get_improvement_engine

    stats = get_improvement_engine().get_routing_stats(days=max(1, min(90, days)))
    return {"status": "ok", **stats}


@tool(
    name="get_llm_usage_analytics",
    description=(
        "Gibt aggregierte LLM-Nutzung zurueck: Requests, Tokens, Kosten und "
        "Top-Agenten/Modelle fuer den gewaehlten Zeitraum."
    ),
    parameters=[
        P("days", "integer", "Analysezeitraum in Tagen (default: 7)", required=False, default=7),
        P("session_id", "string", "Optionale Session-ID fuer eine fokussierte Kostenansicht", required=False, default=""),
        P("limit", "integer", "Maximale Anzahl Top-Agenten/Modelle (default: 5)", required=False, default=5),
    ],
    capabilities=["analysis", "system"],
    category=C.SYSTEM,
)
async def get_llm_usage_analytics(days: int = 7, session_id: str = "", limit: int = 5) -> dict:
    """Gibt Token-/Kostenstatistiken fuer LLM-Aufrufe zurueck."""
    from orchestration.self_improvement_engine import get_improvement_engine

    stats = get_improvement_engine().get_llm_usage_summary(
        days=max(1, min(90, days)),
        session_id=(session_id or "").strip() or None,
        limit=max(1, min(20, limit)),
    )
    return {"status": "ok", **stats}


@tool(
    name="get_llm_budget_status",
    description=(
        "Gibt den aktuellen LLM-Budgetstatus zurueck: aktive Warn-/Soft-/Hard-Limits, "
        "Fenster und Schwellwerte."
    ),
    parameters=[],
    capabilities=["analysis", "system"],
    category=C.SYSTEM,
)
async def get_llm_budget_status() -> dict:
    """Gibt den aktuellen LLM-Budgetstatus zurueck."""
    from orchestration.llm_budget_guard import get_public_budget_status

    return {"status": "ok", **get_public_budget_status()}


@tool(
    name="get_ops_observability",
    description=(
        "Gibt eine zentrale Ops-Zusammenfassung zurueck: Alerts aus Services, Providern, "
        "Tool-Erfolgsraten, Routing-Risiken, LLM-Usage und Budgetstatus."
    ),
    parameters=[
        P("days", "integer", "Analysezeitraum fuer interne Analytics (default: 7)", required=False, default=7),
        P("limit", "integer", "Maximale Anzahl Alerts (default: 5)", required=False, default=5),
    ],
    capabilities=["analysis", "system"],
    category=C.SYSTEM,
)
async def get_ops_observability(days: int = 7, limit: int = 5) -> dict:
    """Gibt eine zentrale Ops-Zusammenfassung zurueck."""
    from gateway.status_snapshot import collect_status_snapshot
    from orchestration.ops_observability import build_ops_observability_summary
    from orchestration.self_improvement_engine import get_improvement_engine

    safe_days = max(1, min(90, days))
    safe_limit = max(1, min(20, limit))
    live_days = max(1, min(safe_days, int(os.getenv("OPS_ANALYTICS_LIVE_DAYS", "1") or 1)))
    snapshot = await collect_status_snapshot()
    engine = get_improvement_engine()
    ops = build_ops_observability_summary(
        services=snapshot.get("services", {}) or {},
        providers=snapshot.get("providers", {}) or {},
        tool_stats=_safe_engine_stat(engine, "get_tool_stats", default=[], days=live_days),
        routing_stats=_safe_engine_stat(
            engine,
            "get_routing_stats",
            default={"by_agent": {}, "days": live_days},
            days=live_days,
        ),
        llm_usage=_safe_engine_stat(
            engine,
            "get_llm_usage_summary",
            default={
                "analysis_days": live_days,
                "session_id": "",
                "total_requests": 0,
                "successful_requests": 0,
                "failed_requests": 0,
                "success_rate": 0.0,
                "input_tokens": 0,
                "output_tokens": 0,
                "cached_tokens": 0,
                "total_cost_usd": 0.0,
                "avg_latency_ms": 0.0,
                "top_agents": [],
                "top_models": [],
            },
            days=live_days,
            limit=safe_limit,
        ),
        recall_stats=_safe_engine_stat(
            engine,
            "get_conversation_recall_stats",
            default={
                "analysis_days": live_days,
                "total_queries": 0,
                "semantic_hits": 0,
                "recent_hits": 0,
                "summary_hits": 0,
                "none_hits": 0,
                "semantic_rate": 0.0,
                "recent_reply_rate": 0.0,
                "summary_fallback_rate": 0.0,
                "none_rate": 0.0,
                "avg_semantic_candidates": 0.0,
                "avg_recent_reply_candidates": 0.0,
                "avg_top_distance": 0.0,
                "top_sources": [],
            },
            days=live_days,
        ),
        budget=snapshot.get("budget", {}) or {},
        self_healing=snapshot.get("self_healing", {}) or {},
        hardening=snapshot.get("self_hardening", {}) or {},
        live_window_days=live_days,
        trend_window_days=safe_days,
        limit=safe_limit,
    )
    return {"status": "ok", "days": safe_days, "live_days": live_days, **ops}


@tool(
    name="get_e2e_regression_matrix",
    description=(
        "Gibt eine zentrale E2E-Regressionsmatrix fuer produktionskritische Kernflows "
        "zurueck: Telegram/Status, E-Mail, Restart/Recovery und Meta->Visual."
    ),
    parameters=[],
    capabilities=["analysis", "system"],
    category=C.SYSTEM,
)
async def get_e2e_regression_matrix() -> dict:
    """Gibt eine zentrale E2E-Regressionsmatrix zurueck."""
    from gateway.status_snapshot import collect_status_snapshot
    from orchestration.browser_workflow_eval import (
        BROWSER_WORKFLOW_EVAL_CASES,
        evaluate_browser_workflow_case,
    )
    from orchestration.e2e_regression_matrix import build_e2e_regression_matrix
    from tools.email_tool.tool import get_email_status

    snapshot = await collect_status_snapshot()
    email_status = get_email_status()
    browser_results = [
        evaluate_browser_workflow_case(case)
        for case in BROWSER_WORKFLOW_EVAL_CASES
    ]
    matrix = build_e2e_regression_matrix(
        snapshot=snapshot,
        email_status=email_status,
        browser_eval_results=browser_results,
    )
    return {"status": "ok", **matrix}


@tool(
    name="get_e2e_release_gate_status",
    description=(
        "Bewertet die E2E-Regressionsmatrix fuer Release-/Canary-Entscheidungen "
        "und kann optional einen Telegram-Alert senden."
    ),
    parameters=[
        P("current_canary_percent", "integer", "Aktueller Canary-Anteil (default: 0)", required=False, default=0),
        P("notify", "boolean", "Telegram-Alert senden wenn Gate nicht gruen ist", required=False, default=False),
    ],
    capabilities=["analysis", "system"],
    category=C.SYSTEM,
)
async def get_e2e_release_gate_status(
    current_canary_percent: int = 0,
    notify: bool = False,
) -> dict:
    """Gibt den E2E-Release-Gate-Status zurueck."""
    from orchestration.e2e_release_gate import (
        build_e2e_gate_alert_message,
        evaluate_e2e_release_gate,
    )
    from utils.telegram_notify import send_telegram

    matrix_payload = await get_e2e_regression_matrix()
    matrix = {
        "summary": matrix_payload.get("summary", {}),
        "flows": matrix_payload.get("flows", []),
    }
    decision = evaluate_e2e_release_gate(
        matrix,
        current_canary_percent=max(0, min(100, int(current_canary_percent or 0))),
    )
    alert_message = build_e2e_gate_alert_message(matrix, decision)
    alert_sent = False
    if notify and decision.get("state") != "pass":
        alert_sent = await send_telegram(alert_message)
    return {
        "status": "ok",
        "matrix": matrix,
        "decision": decision,
        "alert_message": alert_message,
        "alert_sent": alert_sent,
    }


@tool(
    name="get_improvement_suggestions",
    description=(
        "Gibt Verbesserungsvorschläge der Self-Improvement Engine zurück. "
        "Basiert auf Tool-Erfolgsraten, Routing-Konfidenz und Laufzeit-Analyse."
    ),
    parameters=[
        P("include_applied", "boolean", "Auch bereits angewendete Vorschläge anzeigen", required=False, default=False),
    ],
    capabilities=["analysis", "system"],
    category=C.SYSTEM,
)
async def get_improvement_suggestions(include_applied: bool = False) -> dict:
    """Gibt Verbesserungsvorschläge zurück."""
    from orchestration.autonomy_observation import build_autonomy_observation_summary
    from orchestration.improvement_candidates import build_candidate_operator_views
    from orchestration.improvement_task_autonomy import (
        build_improvement_task_governance_view,
        build_improvement_task_autonomy_decisions,
        get_improvement_task_autonomy_settings,
    )
    from orchestration.improvement_task_bridge import build_improvement_task_bridges
    from orchestration.improvement_task_compiler import compile_improvement_tasks
    from orchestration.improvement_task_execution import build_improvement_hardening_task_payloads
    from orchestration.improvement_task_promotion import evaluate_compiled_task_promotions
    from orchestration.self_improvement_engine import get_improvement_engine
    from orchestration.session_reflection import SessionReflectionLoop

    engine = get_improvement_engine()
    suggestions = engine.get_suggestions(applied=include_applied)
    normalized_candidates = engine.get_normalized_suggestions(applied=include_applied)
    try:
        combined_candidates = await SessionReflectionLoop().get_improvement_suggestions()
    except Exception:
        combined_candidates = normalized_candidates
    compiled_tasks = compile_improvement_tasks(combined_candidates, limit=5)
    promotion_decisions = evaluate_compiled_task_promotions(compiled_tasks, limit=5)
    bridge_decisions = build_improvement_task_bridges(compiled_tasks, promotion_decisions, limit=5)
    execution_candidates = build_improvement_hardening_task_payloads(
        compiled_tasks,
        promotion_decisions,
        bridge_decisions,
        limit=5,
    )
    autonomy_settings = get_improvement_task_autonomy_settings()
    observation_summary = build_autonomy_observation_summary()
    return {
        "status": "ok",
        "count": len(suggestions),
        "candidate_count": len(combined_candidates),
        "suggestions": suggestions,
        "normalized_candidates": combined_candidates,
        "top_candidate_insights": build_candidate_operator_views(combined_candidates, limit=5),
        "top_compiled_tasks": compiled_tasks,
        "top_task_promotion_decisions": promotion_decisions,
        "top_task_bridge_decisions": bridge_decisions,
        "top_task_execution_candidates": execution_candidates,
        "task_autonomy_settings": autonomy_settings,
        "improvement_governance": build_improvement_task_governance_view(),
        "top_task_autonomy_decisions": build_improvement_task_autonomy_decisions(
            execution_candidates,
            allow_self_modify=bool(autonomy_settings.get("allow_self_modify")),
            max_autoenqueue=int(autonomy_settings.get("max_autoenqueue") or 1),
            limit=5,
        ),
        "improvement_runtime": dict(observation_summary.get("improvement_runtime") or {}),
    }
