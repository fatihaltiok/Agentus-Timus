from __future__ import annotations

import asyncio
import json
import os
from datetime import datetime
from typing import Any, Mapping, Sequence

from gateway.status_snapshot import collect_status_snapshot
from utils.http_health import fetch_http_text

_DOCTOR_CONTRACT_VERSION = "timus_doctor_v1"
_DEFAULT_DISPATCHER_HEALTH_URL = os.getenv("DISPATCHER_HEALTH_URL", "http://127.0.0.1:5010/health").strip()


def _iso_now() -> str:
    return datetime.now().astimezone().replace(microsecond=0).isoformat()


def _text(value: Any, *, limit: int = 160) -> str:
    text = str(value or "").strip()
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "..."


def _normalize_items(values: Sequence[Any] | None, *, limit: int = 4) -> list[str]:
    items: list[str] = []
    for raw in list(values or []):
        item = _text(raw, limit=120)
        if not item or item in items:
            continue
        items.append(item)
        if len(items) >= limit:
            break
    return items


def _severity_rank(value: str) -> int:
    return {"none": 0, "info": 1, "warn": 2, "critical": 3}.get(_text(value, limit=32).lower(), 0)


def _state_rank(value: str) -> int:
    return {"unknown": 0, "ok": 1, "warn": 2, "critical": 3}.get(_text(value, limit=32).lower(), 0)


def _build_dispatcher_probe(url: str) -> dict[str, Any]:
    try:
        response = fetch_http_text(url, timeout=3.0)
        body = str(response.get("body") or "").strip()
        try:
            data = json.loads(body) if body else {}
        except Exception:
            data = {"status": body}
        return {
            "ok": int(response.get("status_code") or 0) == 200,
            "status_code": int(response.get("status_code") or 0),
            "data": data if isinstance(data, Mapping) else {},
            "error": "",
            "url": url,
        }
    except Exception as exc:
        return {
            "ok": False,
            "status_code": None,
            "data": {},
            "error": str(exc),
            "url": url,
        }


def _normalize_dispatcher_health(probe: Mapping[str, Any]) -> dict[str, Any]:
    payload = probe.get("data")
    data = payload if isinstance(payload, Mapping) else {}
    mcp_payload = data.get("mcp")
    mcp = mcp_payload if isinstance(mcp_payload, Mapping) else {}
    degraded_reasons = _normalize_items(data.get("degraded_reasons") or [], limit=6)
    status = _text(data.get("status"), limit=32).lower()
    if not status:
        status = "error" if not bool(probe.get("ok")) else "unknown"
    phase = _text(data.get("phase"), limit=64).lower()
    ready = bool(data.get("ready"))
    tools_loaded = bool(data.get("tools_loaded"))
    service_ok = bool(probe.get("ok"))

    reason = "steady_state"
    if not service_ok:
        reason = _text(probe.get("error"), limit=160) or "dispatcher_health_unreachable"
    elif status == "starting":
        reason = f"phase:{phase or 'starting'}"
    elif status == "degraded":
        reason = degraded_reasons[0] if degraded_reasons else "dispatcher_degraded"
    elif status == "error":
        reason = _text(data.get("error"), limit=160) or phase or "dispatcher_error"
    elif not ready:
        reason = f"phase:{phase or 'unknown'}"

    return {
        "status": status,
        "phase": phase,
        "ready": ready,
        "ok": service_ok,
        "reason": reason,
        "status_code": probe.get("status_code"),
        "started_at": _text(data.get("started_at"), limit=64),
        "ready_at": _text(data.get("ready_at"), limit=64),
        "last_heartbeat_at": _text(data.get("last_heartbeat_at"), limit=64),
        "tools_loaded": tools_loaded,
        "tool_description_count": int(data.get("tool_description_count") or 0),
        "degraded_reasons": degraded_reasons,
        "mcp_reachable": bool(mcp.get("reachable")),
        "mcp_ready": bool(mcp.get("ready")),
        "mcp_status": _text(mcp.get("status"), limit=32).lower(),
        "mcp_detail": _text(mcp.get("detail"), limit=96),
        "url": _text(probe.get("url"), limit=160),
    }


def _build_service_rows(snapshot: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    local_payload = snapshot.get("local")
    local = local_payload if isinstance(local_payload, Mapping) else {}
    qdrant_ready_payload = local.get("qdrant_ready")
    qdrant_ready = qdrant_ready_payload if isinstance(qdrant_ready_payload, Mapping) else {}
    for name, value in dict(snapshot.get("services") or {}).items():
        service = value if isinstance(value, Mapping) else {}
        row = {
            "active": _text(service.get("active"), limit=32),
            "ok": bool(service.get("ok")),
            "detail": _text(service.get("detail"), limit=160),
            "uptime_seconds": float(service.get("uptime_seconds") or 0.0),
        }
        if name == "qdrant":
            row["ready_ok"] = bool(qdrant_ready.get("ok", True)) if qdrant_ready else bool(service.get("ok"))
            row["ready_status_code"] = qdrant_ready.get("status_code")
            row["ready_error"] = _text(qdrant_ready.get("error"), limit=160)
        rows[_text(name, limit=64)] = row
    return rows


def _build_provider_rows(snapshot: Mapping[str, Any], *, limit: int = 6) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for name, value in list(dict(snapshot.get("providers") or {}).items())[:limit]:
        provider = value if isinstance(value, Mapping) else {}
        rows.append(
            {
                "provider": _text(name, limit=64),
                "state": _text(provider.get("state"), limit=32).lower(),
                "status_code": provider.get("status_code"),
                "latency_ms": provider.get("latency_ms"),
                "base_url": _text(provider.get("base_url"), limit=160),
                "api_configured": bool(provider.get("api_configured")),
            }
        )
    return rows


def build_timus_doctor_report(
    snapshot: Mapping[str, Any],
    *,
    dispatcher_health: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    services = _build_service_rows(snapshot)
    ops_payload = snapshot.get("ops")
    ops = ops_payload if isinstance(ops_payload, Mapping) else {}
    ops_gate_payload = snapshot.get("ops_gate")
    ops_gate = ops_gate_payload if isinstance(ops_gate_payload, Mapping) else {}
    budget_payload = snapshot.get("budget")
    budget = budget_payload if isinstance(budget_payload, Mapping) else {}
    mcp_runtime_payload = snapshot.get("mcp_runtime")
    mcp_runtime = mcp_runtime_payload if isinstance(mcp_runtime_payload, Mapping) else {}
    request_runtime_payload = snapshot.get("request_runtime")
    request_runtime = request_runtime_payload if isinstance(request_runtime_payload, Mapping) else {}
    stability_gate_payload = snapshot.get("stability_gate")
    stability_gate = stability_gate_payload if isinstance(stability_gate_payload, Mapping) else {}
    dispatcher_runtime = _normalize_dispatcher_health(dispatcher_health or {})
    provider_rows = _build_provider_rows(snapshot)

    issues: list[dict[str, Any]] = []

    def add_issue(component: str, severity: str, code: str, detail: str, *, action: str = "") -> None:
        issues.append(
            {
                "component": _text(component, limit=64),
                "severity": _text(severity, limit=32).lower() or "warn",
                "code": _text(code, limit=96).lower(),
                "detail": _text(detail, limit=160),
                "action": _text(action, limit=160),
            }
        )

    for name, row in services.items():
        if not bool(row.get("ok")):
            add_issue(
                name,
                "critical",
                f"service_{name}_inactive",
                f"{name} active={row.get('active') or 'unknown'}",
                action=f"Pruefe {name}.service via systemctl status und Journal.",
            )
        elif name == "qdrant" and not bool(row.get("ready_ok", True)):
            add_issue(
                "qdrant",
                "critical",
                "qdrant_readyz_failed",
                row.get("ready_error") or f"readyz status={row.get('ready_status_code')}",
                action="Pruefe Qdrant-Readyz und Storage/Index-Zustand.",
            )

    mcp_state = _text(mcp_runtime.get("state"), limit=32).lower()
    if mcp_state not in {"", "healthy"}:
        add_issue(
            "mcp_runtime",
            "critical" if mcp_state in {"outage"} else "warn",
            f"mcp_runtime_{mcp_state or 'unknown'}",
            _text(mcp_runtime.get("reason"), limit=160) or mcp_state or "unknown",
            action="Pruefe MCP-Health, Restart-Status und offene Self-Healing-Incidents.",
        )

    dispatcher_status = _text(dispatcher_runtime.get("status"), limit=32).lower()
    if dispatcher_status not in {"", "healthy"}:
        add_issue(
            "dispatcher_runtime",
            "critical" if dispatcher_status in {"error"} else "warn",
            f"dispatcher_{dispatcher_status or 'unknown'}",
            _text(dispatcher_runtime.get("reason"), limit=160),
            action="Pruefe Dispatcher-Health, MCP-Erreichbarkeit und Component-Lifecycle.",
        )
    elif not bool(dispatcher_runtime.get("ready")):
        add_issue(
            "dispatcher_runtime",
            "warn",
            "dispatcher_not_ready",
            _text(dispatcher_runtime.get("reason"), limit=160) or "dispatcher not ready",
            action="Pruefe Dispatcher-Phase und Component-Initialisierung.",
        )

    budget_state = _text(budget.get("state"), limit=32).lower()
    if budget_state in {"warn", "soft_limit", "hard_limit"}:
        add_issue(
            "budget",
            "critical" if budget_state == "hard_limit" else "warn",
            f"budget_{budget_state}",
            _text(budget.get("message"), limit=160) or budget_state,
            action="Pruefe Budget-Scope-Limits und LLM-Nutzung.",
        )

    if bool(ops_gate.get("release_blocked")):
        add_issue(
            "ops_gate",
            "critical",
            "release_blocked",
            f"state={_text(ops_gate.get('state'), limit=32)} canary={ops_gate.get('recommended_canary_percent')}",
            action="Pruefe Ops-Gate, Alerts und Top-Outlier vor weiterem Rollout.",
        )

    for provider in provider_rows:
        provider_state = _text(provider.get("state"), limit=32).lower()
        if provider_state in {"error", "auth_error"}:
            add_issue(
                f"provider:{provider.get('provider')}",
                "warn",
                f"provider_{provider_state}",
                f"{provider.get('provider')} status={provider.get('status_code')}",
                action="Pruefe API-Key, Base-URL und Provider-Limits.",
            )

    issues.sort(key=lambda item: (_severity_rank(str(item.get("severity"))), str(item.get("component"))), reverse=True)
    actions = _normalize_items([item.get("action") for item in issues if item.get("action")], limit=6)

    ok_service_count = sum(1 for row in services.values() if bool(row.get("ok")))
    service_count = len(services)
    unhealthy_provider_count = sum(1 for row in provider_rows if _text(row.get("state"), limit=32).lower() in {"error", "auth_error"})
    ready = (
        service_count > 0
        and ok_service_count == service_count
        and all(bool(row.get("ready_ok", True)) for row in services.values())
        and mcp_state in {"", "healthy"}
        and dispatcher_status in {"healthy"}
        and bool(dispatcher_runtime.get("ready"))
    )

    state = _text(ops.get("state"), limit=32).lower() or ("ok" if ready else "warn")
    highest_issue_severity = max((_severity_rank(str(item.get("severity"))) for item in issues), default=0)
    if highest_issue_severity >= _severity_rank("critical"):
        state = "critical"
    elif highest_issue_severity >= _severity_rank("warn") and _state_rank(state) < _state_rank("warn"):
        state = "warn"
    elif ready and state == "unknown":
        state = "ok"

    return {
        "contract_version": _DOCTOR_CONTRACT_VERSION,
        "generated_at": _iso_now(),
        "state": state,
        "ready": ready,
        "summary": {
            "service_count": service_count,
            "ok_service_count": ok_service_count,
            "failing_services": int(ops.get("failing_services") or max(0, service_count - ok_service_count)),
            "unhealthy_providers": int(ops.get("unhealthy_providers") or unhealthy_provider_count),
            "critical_alerts": int(ops.get("critical_alerts") or 0),
            "warnings": int(ops.get("warnings") or 0),
            "issue_count": len(issues),
            "action_count": len(actions),
        },
        "stack": {
            "services": services,
            "runtime": {
                "mcp": {
                    "state": mcp_state or "unknown",
                    "reason": _text(mcp_runtime.get("reason"), limit=160),
                    "ready": bool(mcp_runtime.get("ready")),
                    "warmup_pending": bool(mcp_runtime.get("warmup_pending")),
                    "restart_status": _text(mcp_runtime.get("restart_status"), limit=32),
                    "restart_phase": _text(mcp_runtime.get("restart_phase"), limit=64),
                },
                "dispatcher": dispatcher_runtime,
                "request": {
                    "state": _text(request_runtime.get("state"), limit=32).lower(),
                    "reason": _text(request_runtime.get("reason"), limit=160),
                    "chat_requests_total": int(request_runtime.get("chat_requests_total") or 0),
                    "chat_failed_total": int(request_runtime.get("chat_failed_total") or 0),
                    "task_failed_total": int(request_runtime.get("task_failed_total") or 0),
                },
                "stability_gate": {
                    "state": _text(stability_gate.get("state"), limit=32).lower(),
                    "circuit_breakers_open": int(stability_gate.get("circuit_breakers_open") or 0),
                    "quarantined_incidents": int(stability_gate.get("quarantined_incidents") or 0),
                },
                "ops_gate": {
                    "state": _text(ops_gate.get("state"), limit=32).lower(),
                    "release_blocked": bool(ops_gate.get("release_blocked")),
                    "recommended_canary_percent": int(ops_gate.get("recommended_canary_percent") or 0),
                },
            },
            "budget": {
                "state": budget_state or "unknown",
                "message": _text(budget.get("message"), limit=160),
                "window_days": int(budget.get("window_days") or 0),
            },
            "providers": provider_rows,
        },
        "issues": issues,
        "actions": actions,
    }


async def collect_timus_doctor_report(
    *,
    mcp_base_url: str | None = None,
    dispatcher_health_url: str | None = None,
) -> dict[str, Any]:
    snapshot = await collect_status_snapshot(mcp_base_url)
    dispatcher_url = _text(dispatcher_health_url or _DEFAULT_DISPATCHER_HEALTH_URL, limit=240)
    dispatcher_probe = await asyncio.to_thread(_build_dispatcher_probe, dispatcher_url)
    report = build_timus_doctor_report(snapshot, dispatcher_health=dispatcher_probe)
    report["snapshot"] = snapshot
    return report


def render_timus_doctor_report(report: Mapping[str, Any]) -> str:
    summary = dict(report.get("summary") or {})
    stack = dict(report.get("stack") or {})
    runtime = dict(stack.get("runtime") or {})
    services = dict(stack.get("services") or {})
    mcp = dict(runtime.get("mcp") or {})
    dispatcher = dict(runtime.get("dispatcher") or {})
    budget = dict(stack.get("budget") or {})
    lines = [
        "Timus Doctor",
        "",
        "State",
        f"- state: {_text(report.get('state'), limit=32)}",
        f"- ready: {'yes' if bool(report.get('ready')) else 'no'}",
        f"- services: {int(summary.get('ok_service_count') or 0)}/{int(summary.get('service_count') or 0)} ok",
        f"- providers_unhealthy: {int(summary.get('unhealthy_providers') or 0)}",
        f"- issues: {int(summary.get('issue_count') or 0)}",
        "",
        "Core",
    ]
    for name in ("qdrant", "mcp", "dispatcher"):
        service = dict(services.get(name) or {})
        if not service:
            continue
        suffix = ""
        if name == "qdrant":
            suffix = f" | ready {'yes' if bool(service.get('ready_ok', True)) else 'no'}"
        lines.append(
            f"- {name}: active={_text(service.get('active'), limit=32) or 'unknown'} | ok={'yes' if bool(service.get('ok')) else 'no'}{suffix}"
        )
    lines.append(
        f"- mcp_runtime: {_text(mcp.get('state'), limit=32) or 'unknown'} | {_text(mcp.get('reason'), limit=120) or 'steady_state'}"
    )
    lines.append(
        f"- dispatcher_runtime: {_text(dispatcher.get('status'), limit=32) or 'unknown'} | phase={_text(dispatcher.get('phase'), limit=64) or 'unknown'} | ready={'yes' if bool(dispatcher.get('ready')) else 'no'}"
    )
    if _text(budget.get("state"), limit=32):
        lines.append(f"- budget: {_text(budget.get('state'), limit=32)}")

    issues = list(report.get("issues") or [])
    lines.append("")
    lines.append("Issues")
    if issues:
        for item in issues[:6]:
            lines.append(
                f"- [{_text(item.get('severity'), limit=16)}] {_text(item.get('component'), limit=64)}: {_text(item.get('detail'), limit=140)}"
            )
    else:
        lines.append("- none")

    actions = list(report.get("actions") or [])
    lines.append("")
    lines.append("Actions")
    if actions:
        for item in actions[:6]:
            lines.append(f"- {item}")
    else:
        lines.append("- none")
    return "\n".join(lines)
