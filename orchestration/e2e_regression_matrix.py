"""Central E2E regression matrix for production-critical Timus flows."""

from __future__ import annotations

from typing import Any, Dict, List

E2E_WARN_MCP_HEALTH_LATENCY_MS = 1500
E2E_STARTUP_GRACE_SECONDS = 45
E2E_WARN_STALE_RESTART_STATUS_SECONDS = 1800


def _flow_status(ok: bool, *, degraded: bool = False) -> str:
    if ok:
        return "warn" if degraded else "pass"
    return "warn" if degraded else "fail"


def _service_uptime_seconds(service: Dict[str, Any]) -> float:
    try:
        return max(0.0, float((service or {}).get("uptime_seconds") or 0.0))
    except Exception:
        return 0.0


def _within_startup_grace(services: Dict[str, Any]) -> bool:
    for service in (services or {}).values():
        if bool((service or {}).get("ok", False)) and _service_uptime_seconds(service) <= E2E_STARTUP_GRACE_SECONDS:
            return True
    return False


def _restart_status_drift(restart: Dict[str, Any]) -> bool:
    if not bool((restart or {}).get("exists", False)):
        return False
    status = str((restart or {}).get("status", "unknown") or "unknown").strip().lower()
    phase = str((restart or {}).get("phase", "") or "").strip().lower()
    age_seconds = float((restart or {}).get("age_seconds") or 0.0)
    return status in {"running", "unknown"} and phase in {"preflight", "launcher", "launcher_error", "running"} and age_seconds >= E2E_WARN_STALE_RESTART_STATUS_SECONDS


def summarize_e2e_matrix(flows: List[Dict[str, Any]]) -> Dict[str, Any]:
    total = len(flows)
    passed = sum(1 for flow in flows if flow.get("status") == "pass")
    warned = sum(1 for flow in flows if flow.get("status") == "warn")
    failed = sum(1 for flow in flows if flow.get("status") == "fail")
    blocking_failed = sum(1 for flow in flows if flow.get("blocking") and flow.get("status") == "fail")
    overall = (
        "fail"
        if blocking_failed > 0
        else "warn"
        if failed > 0 or warned > 0
        else "pass"
    )
    return {
        "overall": overall,
        "total": total,
        "passed": passed,
        "warned": warned,
        "failed": failed,
        "blocking_failed": blocking_failed,
    }


def build_e2e_regression_matrix(
    *,
    snapshot: Dict[str, Any],
    email_status: Dict[str, Any],
    browser_eval_results: List[Dict[str, Any]],
) -> Dict[str, Any]:
    services = (snapshot or {}).get("services", {}) or {}
    local = (snapshot or {}).get("local", {}) or {}
    ops = (snapshot or {}).get("ops", {}) or {}
    restart = (snapshot or {}).get("restart", {}) or {}

    mcp_ok = bool((services.get("mcp", {}) or {}).get("ok", False))
    dispatcher_ok = bool((services.get("dispatcher", {}) or {}).get("ok", False))
    mcp_health_ok = str(((local.get("mcp_health", {}) or {}).get("data", {}) or {}).get("status", "")).lower() == "healthy"
    mcp_health_latency = int((local.get("mcp_health", {}) or {}).get("latency_ms") or 0)
    autonomy_ok = bool((local.get("autonomy_health", {}) or {}).get("ok", False))
    agent_status_ok = bool((local.get("agent_status", {}) or {}).get("ok", False))
    ops_state = str((ops or {}).get("state", "unknown")).strip().lower()
    startup_grace = _within_startup_grace(services)
    restart_status_stale = _restart_status_drift(restart)

    telegram_status_ok = mcp_ok and dispatcher_ok and mcp_health_ok
    telegram_status_degraded = (
        (telegram_status_ok and (
            mcp_health_latency >= E2E_WARN_MCP_HEALTH_LATENCY_MS or not autonomy_ok or not agent_status_ok
        ))
        or (not telegram_status_ok and mcp_ok and dispatcher_ok and startup_grace)
    )
    restart_ok = telegram_status_ok
    restart_degraded = (
        (restart_ok and ops_state in {"warn", "critical"})
        or (mcp_ok and dispatcher_ok and startup_grace)
        or (restart_ok and restart_status_stale)
    )
    email_ok = bool((email_status or {}).get("success", False))
    email_degraded = bool((email_status or {}).get("authenticated", False)) and not email_ok

    browser_passed = sum(1 for item in browser_eval_results if item.get("passed"))
    browser_total = len(browser_eval_results)
    browser_all_ok = browser_total > 0 and browser_passed == browser_total
    browser_blind = browser_total == 0
    browser_avg_score = round(
        (
            sum(float(item.get("score", 1.0 if item.get("passed") else 0.0)) for item in browser_eval_results) / browser_total
        ),
        3,
    ) if browser_total > 0 else 0.0
    browser_degraded = (
        (browser_total > 0 and browser_passed >= max(1, browser_total - 1) and not browser_all_ok)
        or browser_blind
        or (browser_total > 0 and browser_avg_score >= 0.7 and not browser_all_ok)
    )
    telegram_message = (
        "Telegram-/Status-Pfad gesund"
        if telegram_status_ok and not telegram_status_degraded
        else "Telegram-/Status-Pfad im Startup-Grace-Fenster"
        if not telegram_status_ok and mcp_ok and dispatcher_ok and startup_grace
        else "Telegram-/Status-Pfad degradiert: lokale Kontrollsignale oder Latenz auffaellig"
        if telegram_status_ok
        else "Telegram-/Status-Pfad ungesund: Services oder MCP-Health fehlerhaft"
    )
    restart_message = (
        "Restart-/Recovery-Pfad gesund"
        if restart_ok and not restart_degraded
        else "Restart-/Recovery-Pfad im Startup-Grace-Fenster"
        if mcp_ok and dispatcher_ok and startup_grace and not restart_status_stale
        else "Restart-/Recovery-Pfad degradiert: Restart-Artefakt oder Ops-Signale auffaellig"
        if restart_ok
        else "Restart-/Recovery-Pfad ungesund: Kernservices nicht aktiv"
    )
    browser_message = (
        f"Meta→Visual Browser-Evals grün ({browser_passed}/{browser_total})"
        if browser_all_ok
        else "Meta→Visual Browser-Evals blind: keine echten Evaluationsdaten"
        if browser_blind
        else f"Meta→Visual Browser-Evals unvollständig ({browser_passed}/{browser_total})"
    )

    flows = [
        {
            "flow": "telegram_status",
            "status": _flow_status(telegram_status_ok, degraded=telegram_status_degraded),
            "blocking": True,
            "message": telegram_message,
            "evidence": {
                "mcp_service": services.get("mcp", {}),
                "dispatcher_service": services.get("dispatcher", {}),
                "mcp_health": local.get("mcp_health", {}),
                "agent_status": local.get("agent_status", {}),
                "autonomy_health": local.get("autonomy_health", {}),
                "startup_grace": startup_grace,
            },
        },
        {
            "flow": "email_backend",
            "status": _flow_status(email_ok, degraded=email_degraded),
            "blocking": True,
            "message": (
                f"E-Mail-Backend {email_status.get('backend', 'unknown')} bereit"
                if email_ok
                else f"E-Mail-Backend nicht bereit: {email_status.get('error', 'unknown')}"
            ),
            "evidence": email_status,
        },
        {
            "flow": "restart_recovery",
            "status": _flow_status(restart_ok, degraded=restart_degraded),
            "blocking": True,
            "message": restart_message,
            "evidence": {
                "mcp_active": services.get("mcp", {}).get("active", "unknown"),
                "dispatcher_active": services.get("dispatcher", {}).get("active", "unknown"),
                "ops_state": ops.get("state", "unknown"),
                "critical_alerts": ops.get("critical_alerts", 0),
                "warnings": ops.get("warnings", 0),
                "restart_status": restart,
                "startup_grace": startup_grace,
            },
        },
        {
            "flow": "meta_visual_browser",
            "status": _flow_status(browser_all_ok, degraded=browser_degraded),
            "blocking": True,
            "message": browser_message,
            "evidence": {
                "cases": browser_eval_results,
                "passed_cases": browser_passed,
                "total_cases": browser_total,
                "avg_score": browser_avg_score,
                "blind": browser_blind,
            },
        },
    ]
    return {
        "summary": summarize_e2e_matrix(flows),
        "flows": flows,
    }
