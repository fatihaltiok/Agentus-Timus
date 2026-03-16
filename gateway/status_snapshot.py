"""
gateway/status_snapshot.py

Strukturierte Status-Snapshots fuer Telegram /status:
- lokale Timus-Komponenten (MCP, Agent-Status, Autonomy-Health)
- systemd-Service-Status
- Agent → Modell/Provider-Zuordnung
- Live-Readiness fuer genutzte LLM-Provider/APIs
"""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, List, Tuple

import httpx

from agent.providers import AgentModelConfig, ModelProvider, MultiProviderClient, get_provider_client
from memory.qdrant_provider import normalize_qdrant_mode, resolve_qdrant_ready_url
from orchestration.llm_budget_guard import get_public_budget_status
from orchestration.ops_observability import build_ops_observability_summary
from orchestration.ops_release_gate import evaluate_ops_release_gate
from orchestration.self_hardening_runtime import get_self_hardening_runtime_summary
from orchestration.self_stabilization_gate import evaluate_self_stabilization_gate
from orchestration.self_improvement_engine import get_improvement_engine
from orchestration.task_queue import SelfHealingCircuitBreakerState, SelfHealingIncidentStatus, get_queue

_DEFAULT_MCP_BASE_URL = os.getenv("MCP_URL", "http://127.0.0.1:5000").rstrip("/")
_LOCAL_TIMEOUT_S = float(os.getenv("TELEGRAM_STATUS_LOCAL_TIMEOUT", "3"))
_PROVIDER_TIMEOUT_S = float(os.getenv("TELEGRAM_STATUS_PROVIDER_TIMEOUT", "6"))
_RESTART_STATUS_PATH = Path(__file__).resolve().parents[1] / "logs" / "timus_restart_status.json"

_AGENT_STATUS_ORDER: List[Tuple[str, str]] = [
    ("executor", "executor"),
    ("research", "deep_research"),
    ("reasoning", "reasoning"),
    ("creative", "creative"),
    ("development", "development"),
    ("meta", "meta"),
    ("visual", "visual"),
    ("data", "data"),
    ("document", "document"),
    ("communication", "communication"),
    ("system", "system"),
    ("shell", "shell"),
    ("image", "image"),
]


def _service_state(service_name: str) -> Dict[str, Any]:
    try:
        show_proc = subprocess.run(
            [
                "systemctl",
                "show",
                service_name,
                "--property=ActiveState",
                "--property=SubState",
                "--property=ActiveEnterTimestampMonotonic",
                "--property=ExecMainPID",
            ],
            capture_output=True,
            text=True,
            timeout=4,
        )
        proc = subprocess.run(
            ["systemctl", "is-active", service_name],
            capture_output=True,
            text=True,
            timeout=4,
        )
        active = (proc.stdout or proc.stderr).strip() or "unknown"
        show_values: Dict[str, str] = {}
        for line in (show_proc.stdout or "").splitlines():
            if "=" not in line:
                continue
            key, value = line.split("=", 1)
            show_values[key] = value
        active_enter_mono_us = int(show_values.get("ActiveEnterTimestampMonotonic", "0") or 0)
        uptime_seconds = 0.0
        if active == "active" and active_enter_mono_us > 0:
            uptime_seconds = max(0.0, time.monotonic() - (active_enter_mono_us / 1_000_000.0))
        return {
            "service": service_name,
            "active": active,
            "ok": active == "active",
            "sub_state": show_values.get("SubState", ""),
            "main_pid": int(show_values.get("ExecMainPID", "0") or 0),
            "uptime_seconds": round(uptime_seconds, 3),
        }
    except Exception as exc:
        return {
            "service": service_name,
            "active": "unknown",
            "ok": False,
            "error": str(exc),
            "sub_state": "",
            "main_pid": 0,
            "uptime_seconds": 0.0,
        }


def _read_restart_status() -> Dict[str, Any]:
    if not _RESTART_STATUS_PATH.exists():
        return {
            "exists": False,
            "status": "missing",
            "phase": "",
            "request_id": "",
            "age_seconds": None,
            "stale": False,
        }
    try:
        payload = json.loads(_RESTART_STATUS_PATH.read_text(encoding="utf-8"))
        age_seconds = max(0.0, time.time() - _RESTART_STATUS_PATH.stat().st_mtime)
        return {
            "exists": True,
            "status": str(payload.get("status", "unknown") or "unknown"),
            "phase": str(payload.get("phase", "") or ""),
            "request_id": str(payload.get("request_id", "") or ""),
            "age_seconds": round(age_seconds, 3),
            "stale": False,
            "payload": payload,
        }
    except Exception as exc:
        return {
            "exists": True,
            "status": "error",
            "phase": "",
            "request_id": "",
            "age_seconds": None,
            "stale": False,
            "error": str(exc),
        }


async def _fetch_local_json(client: httpx.AsyncClient, url: str) -> Dict[str, Any]:
    started = time.perf_counter()
    try:
        response = await client.get(url, timeout=_LOCAL_TIMEOUT_S)
        latency_ms = round((time.perf_counter() - started) * 1000)
        try:
            data = response.json()
        except Exception:
            data = {"status": (response.text or "").strip()}
        return {
            "ok": response.status_code == 200,
            "status_code": response.status_code,
            "latency_ms": latency_ms,
            "data": data,
            "error": "",
        }
    except Exception as exc:
        return {
            "ok": False,
            "status_code": None,
            "latency_ms": round((time.perf_counter() - started) * 1000),
            "data": {},
            "error": str(exc),
        }


def _configured_model_provider(config_key: str) -> Tuple[str, ModelProvider]:
    model_env, provider_env, fallback_model, fallback_provider = AgentModelConfig.AGENT_CONFIGS[config_key]
    model = os.getenv(model_env, fallback_model).strip() or fallback_model
    provider_raw = os.getenv(provider_env, fallback_provider.value).strip().lower()
    try:
        provider = ModelProvider(provider_raw)
    except Exception:
        provider = fallback_provider
    return model, provider


def _providers_to_check() -> List[ModelProvider]:
    used = []
    for _, config_key in _AGENT_STATUS_ORDER:
        _, provider = _configured_model_provider(config_key)
        if provider not in used:
            used.append(provider)

    provider_client = get_provider_client()
    for provider in ModelProvider:
        if provider_client.has_provider(provider) and provider not in used:
            used.append(provider)
    return used


def _qdrant_server_mode_enabled() -> bool:
    return normalize_qdrant_mode(os.getenv("QDRANT_MODE")) == "server"


async def _check_provider_api(
    client: httpx.AsyncClient,
    provider: ModelProvider,
    *,
    provider_client: MultiProviderClient,
) -> Dict[str, Any]:
    env_name = MultiProviderClient.API_KEY_ENV[provider]
    api_key = provider_client.get_api_key(provider)
    base_url = provider_client.get_base_url(provider)
    if not api_key:
        return {
            "provider": provider.value,
            "state": "missing",
            "ok": False,
            "env": env_name,
            "base_url": base_url,
            "status_code": None,
            "latency_ms": None,
            "detail": f"{env_name} fehlt",
        }

    if provider in {
        ModelProvider.OPENAI,
        ModelProvider.ZAI,
        ModelProvider.DEEPSEEK,
        ModelProvider.INCEPTION,
        ModelProvider.NVIDIA,
        ModelProvider.OPENROUTER,
    }:
        url = f"{base_url.rstrip('/')}/models"
        headers = {"Authorization": f"Bearer {api_key}"}
    elif provider == ModelProvider.ANTHROPIC:
        url = f"{base_url.rstrip('/')}/v1/models"
        headers = {
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
        }
    elif provider == ModelProvider.GOOGLE:
        url = f"{base_url.rstrip('/')}/models"
        headers = {}
    else:
        return {
            "provider": provider.value,
            "state": "unsupported",
            "ok": False,
            "env": env_name,
            "base_url": base_url,
            "status_code": None,
            "latency_ms": None,
            "detail": "kein Health-Adapter",
        }

    params = {"key": api_key} if provider == ModelProvider.GOOGLE else None
    started = time.perf_counter()
    try:
        response = await client.get(url, headers=headers, params=params, timeout=_PROVIDER_TIMEOUT_S)
        latency_ms = round((time.perf_counter() - started) * 1000)
        if response.status_code == 200:
            state = "ok"
            detail = "api ok"
        elif response.status_code in {401, 403}:
            state = "auth_error"
            detail = f"http {response.status_code}"
        else:
            state = "error"
            detail = f"http {response.status_code}"
        return {
            "provider": provider.value,
            "state": state,
            "ok": state == "ok",
            "env": env_name,
            "base_url": base_url,
            "status_code": response.status_code,
            "latency_ms": latency_ms,
            "detail": detail,
        }
    except Exception as exc:
        return {
            "provider": provider.value,
            "state": "error",
            "ok": False,
            "env": env_name,
            "base_url": base_url,
            "status_code": None,
            "latency_ms": round((time.perf_counter() - started) * 1000),
            "detail": str(exc),
        }


def _build_agent_rows(
    runtime_agents: Dict[str, Dict[str, Any]],
    provider_checks: Dict[str, Dict[str, Any]],
) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for runtime_name, config_key in _AGENT_STATUS_ORDER:
        model, provider = _configured_model_provider(config_key)
        runtime = runtime_agents.get(runtime_name, {}) or {}
        provider_info = provider_checks.get(provider.value, {})
        rows.append(
            {
                "agent": runtime_name,
                "runtime_status": str(runtime.get("status", "idle") or "idle"),
                "last_run": runtime.get("last_run"),
                "last_query": runtime.get("last_query", ""),
                "provider": provider.value,
                "model": model,
                "provider_state": provider_info.get("state", "unknown"),
            }
        )
    return rows


def _build_api_control_summary(
    provider_checks: Dict[str, Dict[str, Any]],
    usage_summary: Dict[str, Any],
    budget_status: Dict[str, Any],
) -> Dict[str, Any]:
    usage_by_provider = {
        str(item.get("provider", "") or ""): item
        for item in (usage_summary.get("top_providers", []) or [])
        if str(item.get("provider", "") or "")
    }
    rows: List[Dict[str, Any]] = []
    for provider_name, info in (provider_checks or {}).items():
        usage = usage_by_provider.get(provider_name, {})
        rows.append(
            {
                "provider": provider_name,
                "api_env": str(info.get("env", "") or ""),
                "api_configured": bool(info.get("env")) and str(info.get("state", "missing")) != "missing",
                "state": str(info.get("state", "unknown") or "unknown"),
                "base_url": str(info.get("base_url", "") or ""),
                "latency_ms": info.get("latency_ms"),
                "status_code": info.get("status_code"),
                "detail": str(info.get("detail", "") or ""),
                "total_requests": int(usage.get("total_requests", 0) or 0),
                "total_cost_usd": round(float(usage.get("total_cost_usd", 0.0) or 0.0), 6),
                "input_tokens": int(usage.get("input_tokens", 0) or 0),
                "output_tokens": int(usage.get("output_tokens", 0) or 0),
            }
        )
    rows.sort(key=lambda item: (-float(item.get("total_cost_usd", 0.0) or 0.0), item.get("provider", "")))
    return {
        "active_provider_count": sum(1 for row in rows if row.get("api_configured")),
        "total_requests": int(usage_summary.get("total_requests", 0) or 0),
        "total_cost_usd": round(float(usage_summary.get("total_cost_usd", 0.0) or 0.0), 6),
        "budget_state": str((budget_status or {}).get("state", "unknown") or "unknown"),
        "providers": rows,
    }


def _safe_engine_stat(engine: Any, method_name: str, *, default: Any, **kwargs: Any) -> Any:
    method = getattr(engine, method_name, None)
    if method is None:
        return default
    try:
        return method(**kwargs)
    except Exception:
        return default


def _build_self_healing_summary() -> Dict[str, Any]:
    try:
        queue = get_queue()
        metrics = queue.get_self_healing_metrics()
        resource_guard = queue.get_self_healing_runtime_state("resource_guard") or {}
        resource_guard_meta = resource_guard.get("metadata", {}) or {}
        open_breakers = queue.list_self_healing_circuit_breakers(
            states=[SelfHealingCircuitBreakerState.OPEN],
            limit=4,
        )
        incidents = queue.list_self_healing_incidents(
            statuses=[SelfHealingIncidentStatus.OPEN],
            limit=4,
        )
        rows: List[Dict[str, Any]] = []
        for incident in incidents:
            incident_key = str(incident.get("incident_key", "") or "")
            notify_state = queue.get_self_healing_runtime_state(f"incident_notify:{incident_key.lower()}") or {}
            notify_meta = notify_state.get("metadata", {}) or {}
            phase_state = queue.get_self_healing_runtime_state(f"incident_phase:{incident_key.lower()}") or {}
            phase_meta = phase_state.get("metadata", {}) or {}
            quarantine_state = queue.get_self_healing_runtime_state(f"incident_quarantine:{incident_key.lower()}") or {}
            quarantine_meta = quarantine_state.get("metadata", {}) or {}
            memory_state = queue.get_self_healing_runtime_state(
                f"incident_memory:{str(incident.get('component', '') or '').lower()}:{str(incident.get('signal', '') or '').lower()}"
            ) or {}
            memory_meta = memory_state.get("metadata", {}) or {}
            rows.append(
                {
                    "incident_key": incident_key,
                    "component": str(incident.get("component", "") or ""),
                    "signal": str(incident.get("signal", "") or ""),
                    "severity": str(incident.get("severity", "") or ""),
                    "last_seen_at": str(incident.get("last_seen_at", "") or ""),
                    "recovery_phase": str(phase_state.get("state_value", "unknown") or "unknown"),
                    "recovery_stage": str(phase_meta.get("stage", "") or ""),
                    "memory_state": str(memory_state.get("state_value", "new") or "new"),
                    "memory_seen_count": int(memory_meta.get("seen_count", 0) or 0),
                    "memory_last_outcome": str(memory_meta.get("last_outcome", "") or ""),
                    "quarantine_state": str(quarantine_state.get("state_value", "none") or "none"),
                    "quarantine_until": str(quarantine_meta.get("quarantine_until", "") or ""),
                    "notification_state": str(notify_state.get("state_value", "none") or "none"),
                    "cooldown_until": str(notify_meta.get("cooldown_until", "") or ""),
                    "last_sent_at": str(notify_meta.get("last_sent_at", "") or ""),
                    "last_channels": list(notify_meta.get("last_channels", []) or []),
                }
            )
        return {
            "open_incidents": int(metrics.get("open_incidents", 0) or 0),
            "degrade_mode": str(metrics.get("degrade_mode", "normal") or "normal"),
            "last_open": metrics.get("last_open"),
            "circuit_breakers_open": int(metrics.get("circuit_breakers_open", 0) or 0),
            "open_breakers": [
                {
                    "breaker_key": str(row.get("breaker_key", "") or ""),
                    "component": str(row.get("component", "") or ""),
                    "signal": str(row.get("signal", "") or ""),
                    "opened_until": str(row.get("opened_until", "") or ""),
                }
                for row in open_breakers
            ],
            "resource_guard_state": str(resource_guard.get("state_value", "inactive") or "inactive"),
            "resource_guard_reason": str(resource_guard_meta.get("reason", "") or ""),
            "resource_guard_until": str(resource_guard_meta.get("deferred_until", "") or ""),
            "incidents": rows,
        }
    except Exception:
        return {
            "open_incidents": 0,
            "degrade_mode": "unknown",
            "last_open": None,
            "circuit_breakers_open": 0,
            "open_breakers": [],
            "resource_guard_state": "unknown",
            "resource_guard_reason": "",
            "resource_guard_until": "",
            "incidents": [],
        }


def _build_self_hardening_summary() -> Dict[str, Any]:
    try:
        queue = get_queue()
        return get_self_hardening_runtime_summary(queue)
    except Exception:
        return {
            "state": "unknown",
            "last_event": "",
            "last_status": "",
            "last_pattern_name": "",
            "last_component": "",
            "last_requested_fix_mode": "",
            "last_execution_mode": "",
            "last_route_target": "",
            "last_reason": "",
            "last_task_id": "",
            "last_goal_id": "",
            "last_target_file_path": "",
            "last_change_type": "",
            "sample_lines": [],
            "metrics": {},
            "updated_at": "",
        }


async def collect_status_snapshot(mcp_base_url: str | None = None) -> Dict[str, Any]:
    base_url = (mcp_base_url or _DEFAULT_MCP_BASE_URL).rstrip("/")
    provider_client = get_provider_client()
    providers = _providers_to_check()
    qdrant_server_mode = _qdrant_server_mode_enabled()

    async with httpx.AsyncClient(trust_env=False) as client:
        local_tasks = {
            "mcp_health": asyncio.create_task(_fetch_local_json(client, f"{base_url}/health")),
            "agent_status": asyncio.create_task(_fetch_local_json(client, f"{base_url}/agent_status")),
            "autonomy_health": asyncio.create_task(_fetch_local_json(client, f"{base_url}/autonomy/health")),
        }
        if qdrant_server_mode:
            local_tasks["qdrant_ready"] = asyncio.create_task(
                _fetch_local_json(client, resolve_qdrant_ready_url(os.getenv("QDRANT_URL")))
            )
        provider_tasks = {
            provider.value: asyncio.create_task(
                _check_provider_api(client, provider, provider_client=provider_client)
            )
            for provider in providers
        }

        local_results = {name: await task for name, task in local_tasks.items()}
        provider_results = {name: await task for name, task in provider_tasks.items()}

    runtime_agents = (local_results["agent_status"].get("data", {}) or {}).get("agents", {}) or {}
    services = {
        "mcp": _service_state("timus-mcp.service"),
        "dispatcher": _service_state("timus-dispatcher.service"),
    }
    if qdrant_server_mode:
        qdrant_service = _service_state("qdrant.service")
        qdrant_ready = local_results.get("qdrant_ready", {}) or {}
        if qdrant_service.get("ok", False) and not bool(qdrant_ready.get("ok", False)):
            qdrant_service = dict(qdrant_service)
            qdrant_service["ok"] = False
            qdrant_service["active"] = "degraded"
            qdrant_service["detail"] = str(qdrant_ready.get("error", "") or "readyz failed")
        services["qdrant"] = qdrant_service

    try:
        usage_summary = get_improvement_engine().get_llm_usage_summary(days=1, limit=3)
    except Exception:
        usage_summary = {
            "analysis_days": 1,
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
        }
    try:
        budget_status = get_public_budget_status()
    except Exception:
        budget_status = {"state": "unknown", "message": "", "scopes": [], "soft_max_tokens": 0, "window_days": 1}
    self_healing_summary = _build_self_healing_summary()
    self_hardening_summary = _build_self_hardening_summary()

    try:
        improvement_engine = get_improvement_engine()
        ops_summary = build_ops_observability_summary(
            services=services,
            providers=provider_results,
            tool_stats=_safe_engine_stat(improvement_engine, "get_tool_stats", default=[], days=7),
            routing_stats=_safe_engine_stat(
                improvement_engine,
                "get_routing_stats",
                default={"by_agent": {}, "days": 7},
                days=7,
            ),
            llm_usage=usage_summary,
            budget=budget_status,
            self_healing=self_healing_summary,
            hardening=self_hardening_summary,
            limit=4,
        )
    except Exception:
        ops_summary = {
            "state": "unknown",
            "critical_alerts": 0,
            "warnings": 0,
            "failing_services": 0,
            "unhealthy_providers": 0,
            "alerts": [],
            "top_tool_failures": [],
            "top_routing_risks": [],
            "llm_success_rate": 0.0,
        }

    return {
        "services": services,
        "restart": _read_restart_status(),
        "local": local_results,
        "providers": provider_results,
        "agents": _build_agent_rows(runtime_agents, provider_results),
        "usage": usage_summary,
        "budget": budget_status,
        "ops": ops_summary,
        "ops_gate": evaluate_ops_release_gate(ops_summary),
        "self_healing": self_healing_summary,
        "self_hardening": self_hardening_summary,
        "stability_gate": evaluate_self_stabilization_gate(self_healing_summary),
        "api_control": _build_api_control_summary(provider_results, usage_summary, budget_status),
        "thinking": bool((local_results["agent_status"].get("data", {}) or {}).get("thinking", False)),
    }


def _runtime_icon(status: str) -> str:
    normalized = (status or "").strip().lower()
    return {
        "thinking": "🤔",
        "running": "🔄",
        "completed": "✅",
        "error": "❌",
        "idle": "⚪",
    }.get(normalized, "•")


def _provider_icon(state: str) -> str:
    normalized = (state or "").strip().lower()
    return {
        "ok": "🟢",
        "missing": "⚪",
        "auth_error": "🟠",
        "error": "🔴",
        "unsupported": "⚪",
    }.get(normalized, "•")


def _service_icon(ok: bool) -> str:
    return "🟢" if ok else "🔴"


def format_status_message(snapshot: Dict[str, Any], summary_lines: List[str]) -> str:
    services = snapshot.get("services", {}) or {}
    local = snapshot.get("local", {}) or {}
    providers = snapshot.get("providers", {}) or {}
    agents = snapshot.get("agents", []) or []
    usage = snapshot.get("usage", {}) or {}
    budget = snapshot.get("budget", {}) or {}
    ops = snapshot.get("ops", {}) or {}
    ops_gate = snapshot.get("ops_gate", {}) or {}
    self_healing = snapshot.get("self_healing", {}) or {}
    self_hardening = snapshot.get("self_hardening", {}) or {}
    stability_gate = snapshot.get("stability_gate", {}) or {}
    thinking = snapshot.get("thinking", False)

    mcp_health = local.get("mcp_health", {}) or {}
    mcp_payload = mcp_health.get("data", {}) or {}
    autonomy = local.get("autonomy_health", {}) or {}
    autonomy_payload = (autonomy.get("data", {}) or {}).get("health", {}) or {}

    core_lines = [
        "Core",
        f"{_service_icon(services.get('mcp', {}).get('ok', False))} MCP Service: {services.get('mcp', {}).get('active', 'unknown')} | "
        f"HTTP {mcp_payload.get('status', 'down')} | RPC {mcp_payload.get('total_rpc_methods', '?')} | "
        f"{mcp_health.get('latency_ms', '?')} ms",
        f"{_service_icon(services.get('dispatcher', {}).get('ok', False))} Dispatcher: {services.get('dispatcher', {}).get('active', 'unknown')}",
        f"{'🤔' if thinking else '⚪'} Thinking: {'aktiv' if thinking else 'inaktiv'}",
    ]
    if "qdrant" in services:
        qdrant_ready = local.get("qdrant_ready", {}) or {}
        ready_suffix = ""
        if qdrant_ready:
            ready_suffix = f" | ready {qdrant_ready.get('status_code', '?')} | {qdrant_ready.get('latency_ms', '?')} ms"
        core_lines.append(
            f"{_service_icon(services.get('qdrant', {}).get('ok', False))} Qdrant: {services.get('qdrant', {}).get('active', 'unknown')}{ready_suffix}"
        )
    if autonomy_payload:
        core_lines.append(
            "🛠️ Autonomy-Health: "
            f"Goals {autonomy_payload.get('goals', {}).get('open_alignment_rate', 0.0)}% | "
            f"Plans {autonomy_payload.get('planning', {}).get('active_plans', 0)} | "
            f"Healing {autonomy_payload.get('healing', {}).get('degrade_mode', 'normal')}"
        )

    healing_lines = ["", "Self-Healing"]
    healing_lines.append(
        f"🧯 Open {self_healing.get('open_incidents', 0)} | Degrade {self_healing.get('degrade_mode', 'unknown')}"
    )
    if stability_gate:
        healing_lines.append(
            "• Gate {state} | Breakers {breakers} | Quarantine {quarantine} | Cooldown {cooldown} | Patterns {patterns}".format(
                state=stability_gate.get("state", "unknown"),
                breakers=stability_gate.get("circuit_breakers_open", 0),
                quarantine=stability_gate.get("quarantined_incidents", 0),
                cooldown=stability_gate.get("cooldown_incidents", 0),
                patterns=stability_gate.get("known_bad_patterns", 0),
            )
        )
    if str(self_healing.get("resource_guard_state", "inactive")) != "inactive":
        guard_until = str(self_healing.get("resource_guard_until", "") or "")
        guard_suffix = f" | bis {guard_until[:16]}" if guard_until else ""
        healing_lines.append(
            f"• Resource-Guard {self_healing.get('resource_guard_state', 'unknown')} | {self_healing.get('resource_guard_reason', '')}{guard_suffix}"
        )
    for breaker in (self_healing.get("open_breakers", []) or [])[:2]:
        opened_until = str(breaker.get("opened_until", "") or "")
        opened_suffix = f" | offen bis {opened_until[:16]}" if opened_until else ""
        healing_lines.append(
            f"• Breaker {breaker.get('component', '?')}/{breaker.get('signal', '?')}{opened_suffix}"
        )
    for incident in (self_healing.get("incidents", []) or [])[:3]:
        cooldown_until = str(incident.get("cooldown_until", "") or "")
        cooldown_suffix = f" | cooldown bis {cooldown_until[:16]}" if cooldown_until else ""
        quarantine_until = str(incident.get("quarantine_until", "") or "")
        quarantine_suffix = f" | quarantine bis {quarantine_until[:16]}" if quarantine_until else ""
        healing_lines.append(
            "• {component}/{signal} [{severity}] | {phase}/{stage} | memory {memory} ({seen}x/{outcome}) | quarantine {quarantine} | notify {notify}{cooldown}{quarantine_suffix}".format(
                component=incident.get("component", "?"),
                signal=incident.get("signal", "?"),
                severity=incident.get("severity", "?"),
                phase=incident.get("recovery_phase", "unknown"),
                stage=incident.get("recovery_stage", "") or "stage?",
                memory=incident.get("memory_state", "new"),
                seen=incident.get("memory_seen_count", 0),
                outcome=incident.get("memory_last_outcome", "-") or "-",
                quarantine=incident.get("quarantine_state", "none"),
                notify=incident.get("notification_state", "none"),
                cooldown=cooldown_suffix,
                quarantine_suffix=quarantine_suffix,
            )
        )

    hardening_lines = ["", "M18 Hardening"]
    hardening_lines.append(
        f"🛠️ State {self_hardening.get('state', 'unknown')} | "
        f"Event {self_hardening.get('last_event', 'n/a') or 'n/a'} | "
        f"Status {self_hardening.get('last_status', 'n/a') or 'n/a'}"
    )
    hardening_lines.append(
        f"• Pattern {self_hardening.get('last_pattern_name', 'n/a') or 'n/a'} | "
        f"Route {self_hardening.get('last_route_target', 'n/a') or 'n/a'} | "
        f"Exec {self_hardening.get('last_execution_mode', 'n/a') or 'n/a'}"
    )
    hardening_metrics = self_hardening.get("metrics", {}) or {}
    hardening_lines.append(
        f"• Proposals {hardening_metrics.get('proposals_total', 0)} | "
        f"Tasks {hardening_metrics.get('tasks_created_total', 0)} | "
        f"SM Attempts {hardening_metrics.get('self_modify_attempts_total', 0)} | "
        f"SM Success {hardening_metrics.get('self_modify_successes_total', 0)}"
    )

    provider_lines = ["", "LLM/API Health"]
    for provider_name, info in providers.items():
        status_code = info.get("status_code")
        latency = info.get("latency_ms")
        suffix = []
        if status_code is not None:
            suffix.append(f"HTTP {status_code}")
        if latency is not None:
            suffix.append(f"{latency} ms")
        suffix_text = " | " + " | ".join(suffix) if suffix else ""
        provider_lines.append(
            f"{_provider_icon(info.get('state', 'unknown'))} {provider_name}: "
            f"{info.get('state', 'unknown')}{suffix_text}"
        )

    ops_lines = ["", "Ops"]
    ops_icon = {
        "ok": "🟢",
        "warn": "🟠",
        "critical": "🔴",
        "unknown": "⚪",
    }.get(str(ops.get("state", "unknown")).lower(), "⚪")
    ops_lines.append(
        f"{ops_icon} State {ops.get('state', 'unknown')} | Critical {ops.get('critical_alerts', 0)} | "
        f"Warnings {ops.get('warnings', 0)} | Services {ops.get('failing_services', 0)} | "
        f"Providers {ops.get('unhealthy_providers', 0)}"
    )
    slo = ops.get("slo", {}) or {}
    if slo:
        ops_lines.append(
            "• SLO: breached {breached} | healthy {healthy}".format(
                breached=slo.get("breached", 0),
                healthy=slo.get("healthy", 0),
            )
        )
    error_classes = ops.get("error_classes", {}) or {}
    if error_classes:
        ops_lines.append(
            "• Classes: avail {availability} | latency {latency} | reliability {reliability} | "
            "routing {routing} | budget {budget} | orchestration {orchestration}".format(
                availability=error_classes.get("availability", 0),
                latency=error_classes.get("latency", 0),
                reliability=error_classes.get("reliability", 0),
                routing=error_classes.get("routing", 0),
                budget=error_classes.get("budget", 0),
                orchestration=error_classes.get("orchestration", 0),
            )
        )
    for alert in (ops.get("alerts", []) or [])[:4]:
        alert_class = alert.get("error_class", "")
        class_suffix = f" [{alert_class}]" if alert_class else ""
        ops_lines.append(f"• {alert.get('severity', 'warn')}{class_suffix}: {alert.get('message', '')}")
    top_outliers = (ops.get("top_outliers", []) or [])[:2]
    for outlier in top_outliers:
        ops_lines.append(f"• Outlier {outlier.get('target', '?')}: {outlier.get('message', '')}")
    if ops_gate:
        ops_lines.append(
            "• Gate "
            f"{ops_gate.get('state', 'unknown')} | "
            f"ReleaseBlocked {ops_gate.get('release_blocked', False)} | "
            f"Canary {ops_gate.get('recommended_canary_percent', 0)}%"
        )

    usage_lines = ["", "Kosten / Usage"]
    usage_lines.append(
        "💸 Requests {total_requests} | Input {input_tokens} | Output {output_tokens} | "
        "Cache {cached_tokens} | Cost ${total_cost_usd:.6f} | Ø {avg_latency_ms} ms".format(
            total_requests=usage.get("total_requests", 0),
            input_tokens=usage.get("input_tokens", 0),
            output_tokens=usage.get("output_tokens", 0),
            cached_tokens=usage.get("cached_tokens", 0),
            total_cost_usd=float(usage.get("total_cost_usd", 0.0) or 0.0),
            avg_latency_ms=usage.get("avg_latency_ms", 0.0),
        )
    )
    if budget:
        alert_icon = {
            "ok": "🟢",
            "warn": "🟠",
            "soft_limit": "🟠",
            "hard_limit": "🔴",
            "unknown": "⚪",
        }.get(str(budget.get("state", "unknown")).lower(), "⚪")
        usage_lines.append(
            "{icon} Budget {state} | Window {window}d | Soft MaxTokens {soft_tokens}".format(
                icon=alert_icon,
                state=budget.get("state", "unknown"),
                window=budget.get("window_days", 1),
                soft_tokens=budget.get("soft_max_tokens", 0),
            )
        )
        if budget.get("message"):
            usage_lines.append(f"• Alert: {budget.get('message')}")
        for scope in budget.get("scopes", [])[:3]:
            usage_lines.append(
                "• {scope}: ${current:.6f} | warn ${warn:.6f} | soft ${soft:.6f} | hard ${hard:.6f} | {state}".format(
                    scope=scope.get("scope", "?"),
                    current=float(scope.get("current_cost_usd", 0.0) or 0.0),
                    warn=float(scope.get("warn_usd", 0.0) or 0.0),
                    soft=float(scope.get("soft_limit_usd", 0.0) or 0.0),
                    hard=float(scope.get("hard_limit_usd", 0.0) or 0.0),
                    state=scope.get("state", "ok"),
                )
            )
    for item in usage.get("top_agents", [])[:3]:
        usage_lines.append(
            f"• Agent {item.get('agent', '?')}: ${float(item.get('total_cost_usd', 0.0) or 0.0):.6f} | "
            f"{item.get('total_requests', 0)} req"
        )

    agent_lines = ["", "Agenten"]
    for row in agents:
        model = str(row.get("model", ""))[:34]
        agent_lines.append(
            f"{_runtime_icon(row.get('runtime_status', 'idle'))} {row.get('agent'):<13} "
            f"{row.get('runtime_status', 'idle'):<10} | {row.get('provider', '?'):<10} | {model}"
        )

    lines = ["🤖 Timus Status", ""]
    lines.extend(core_lines)
    lines.append("")
    lines.extend(summary_lines)
    lines.extend(healing_lines)
    lines.extend(hardening_lines)
    lines.extend(ops_lines)
    lines.extend(provider_lines)
    lines.extend(usage_lines)
    lines.extend(agent_lines)
    return "\n".join(lines)
