from __future__ import annotations

import json
import os
from types import SimpleNamespace

import pytest

from agent.providers import ModelProvider
from gateway import status_snapshot


class _DummyAsyncClient:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _PlaintextResponse:
    def __init__(self, *, text: str, status_code: int = 200):
        self.text = text
        self.status_code = status_code

    def json(self):
        raise ValueError("not json")


@pytest.mark.asyncio
async def test_fetch_local_json_falls_back_to_plaintext_status():
    class _Client:
        async def get(self, _url: str, timeout: float):
            del timeout
            return _PlaintextResponse(text="all shards are ready", status_code=200)

    result = await status_snapshot._fetch_local_json(_Client(), "http://127.0.0.1:6333/readyz")

    assert result["ok"] is True
    assert result["status_code"] == 200
    assert result["data"]["status"] == "all shards are ready"


@pytest.mark.asyncio
async def test_collect_status_snapshot_builds_agent_rows(monkeypatch):
    monkeypatch.setenv("QDRANT_MODE", "server")
    monkeypatch.setenv("QDRANT_URL", "http://127.0.0.1:6333")

    async def fake_fetch_local_json(_client, url: str):
        if url.endswith("/agent_status"):
            return {
                "ok": True,
                "status_code": 200,
                "latency_ms": 12,
                "data": {
                    "agents": {
                        "meta": {"status": "thinking", "last_run": "2026-03-08T20:00:00Z", "last_query": "plan"},
                        "research": {"status": "completed", "last_run": "2026-03-08T19:59:00Z", "last_query": "news"},
                    },
                    "thinking": True,
                },
                "error": "",
            }
        if url.endswith("/health"):
            return {
                "ok": True,
                "status_code": 200,
                "latency_ms": 25,
                "data": {"status": "healthy", "total_rpc_methods": 123},
                "error": "",
            }
        if url.endswith("/location/status"):
            return {
                "ok": True,
                "status_code": 200,
                "latency_ms": 14,
                "data": {
                    "location": {
                        "display_name": "Alexanderplatz, Berlin, Deutschland",
                        "locality": "Berlin",
                        "device_id": "pixel8",
                        "user_scope": "primary",
                        "presence_status": "live",
                        "privacy_state": "enabled",
                        "usable_for_context": True,
                    },
                    "controls": {
                        "sharing_enabled": True,
                        "context_enabled": True,
                        "background_sync_allowed": True,
                        "preferred_device_id": "pixel8",
                        "allowed_user_scopes": ["primary"],
                        "max_device_entries": 8,
                    },
                    "devices": [
                        {
                            "device_id": "pixel8",
                            "user_scope": "primary",
                            "presence_status": "live",
                            "selected": True,
                        }
                    ],
                    "device_count": 1,
                    "selection_reason": "preferred_device",
                    "active_device_id": "pixel8",
                    "active_user_scope": "primary",
                },
                "error": "",
            }
        if url.endswith("/readyz"):
            return {
                "ok": True,
                "status_code": 200,
                "latency_ms": 11,
                "data": {"title": "qdrant - vector search engine"},
                "error": "",
            }
        return {
            "ok": True,
            "status_code": 200,
            "latency_ms": 18,
            "data": {"health": {"goals": {"open_alignment_rate": 88.0}, "planning": {"active_plans": 3}, "healing": {"degrade_mode": "normal"}}},
            "error": "",
        }

    async def fake_check_provider_api(_client, provider, *, provider_client):
        del provider_client
        states = {
            ModelProvider.OPENROUTER.value: "ok",
            ModelProvider.ZAI.value: "ok",
            ModelProvider.OPENAI.value: "ok",
            ModelProvider.INCEPTION.value: "missing",
        }
        return {
            "provider": provider.value,
            "state": states[provider.value],
            "ok": states[provider.value] == "ok",
            "env": "X",
            "base_url": "https://example.test",
            "status_code": 200 if states[provider.value] == "ok" else None,
            "latency_ms": 42 if states[provider.value] == "ok" else None,
            "detail": "",
        }

    monkeypatch.setattr(status_snapshot, "_fetch_local_json", fake_fetch_local_json)
    monkeypatch.setattr(status_snapshot, "_check_provider_api", fake_check_provider_api)
    monkeypatch.setattr(
        status_snapshot,
        "_service_state",
        lambda svc: {
            "service": svc,
            "active": "active",
            "ok": True,
            "uptime_seconds": 120.0,
        },
    )
    monkeypatch.setattr(
        status_snapshot,
        "_read_restart_status",
        lambda: {
            "exists": False,
            "status": "missing",
            "phase": "",
            "request_id": "",
            "age_seconds": None,
            "stale": False,
        },
    )
    monkeypatch.setattr(status_snapshot, "_providers_to_check", lambda: [ModelProvider.OPENROUTER, ModelProvider.ZAI, ModelProvider.OPENAI, ModelProvider.INCEPTION])
    monkeypatch.setattr(status_snapshot, "get_provider_client", lambda: SimpleNamespace())
    monkeypatch.setattr(
        status_snapshot,
        "get_improvement_engine",
        lambda: SimpleNamespace(
            get_llm_usage_summary=lambda days=1, limit=3: {
                "analysis_days": days,
                "session_id": "",
                "total_requests": 6,
                "successful_requests": 6,
                "failed_requests": 0,
                "success_rate": 1.0,
                "input_tokens": 1200,
                "output_tokens": 260,
                "cached_tokens": 80,
                "total_cost_usd": 0.0345,
                "avg_latency_ms": 155.0,
                "top_agents": [{"agent": "meta", "total_cost_usd": 0.02, "total_requests": 3}],
                "top_models": [{"provider": "openrouter", "model": "z-ai/glm-5", "total_cost_usd": 0.02, "total_requests": 3}],
                "top_providers": [{"provider": "openrouter", "total_cost_usd": 0.02, "total_requests": 3, "input_tokens": 800, "output_tokens": 120}],
            }
        ),
    )
    monkeypatch.setattr(
        status_snapshot,
        "get_queue",
        lambda: SimpleNamespace(
                get_self_healing_metrics=lambda: {
                    "open_incidents": 1,
                    "degrade_mode": "degraded",
                    "circuit_breakers_open": 1,
                    "last_open": {"incident_key": "m3_mcp_health_unavailable"},
                },
            list_self_healing_incidents=lambda statuses=None, limit=4: [
                {
                    "incident_key": "m3_mcp_health_unavailable",
                    "component": "mcp",
                    "signal": "mcp_health",
                    "severity": "high",
                    "last_seen_at": "2026-03-10T15:02:39",
                }
            ],
            list_self_healing_circuit_breakers=lambda states=None, limit=4: [
                {
                    "breaker_key": "mcp:mcp_health",
                    "component": "mcp",
                    "signal": "mcp_health",
                    "opened_until": "2026-03-10T15:18:00",
                    "metadata": {},
                }
            ],
            get_self_healing_runtime_state=lambda key: (
                {
                    "state_key": key,
                    "state_value": "active",
                    "metadata": {
                        "reason": "degrade_mode=degraded,m3_system_pressure",
                        "deferred_until": "2026-03-10T15:22:00",
                    },
                    "updated_at": "2026-03-10T15:02:39",
                }
                if str(key) == "resource_guard"
                else {
                    "state_key": key,
                    "state_value": "known_bad_pattern",
                    "metadata": {
                        "seen_count": 3,
                        "last_outcome": "escalated",
                    },
                    "updated_at": "2026-03-10T15:02:39",
                }
                if str(key).startswith("incident_memory:")
                else {
                    "state_key": key,
                    "state_value": "recovering",
                    "metadata": {
                        "stage": "diagnose",
                    },
                    "updated_at": "2026-03-10T15:02:39",
                }
                if str(key).startswith("incident_phase:")
                else {
                    "state_key": key,
                    "state_value": "active" if str(key).startswith("incident_quarantine:") else "cooldown_active",
                    "metadata": (
                        {
                            "quarantine_until": "2026-03-10T15:15:00",
                        }
                        if str(key).startswith("incident_quarantine:")
                        else {
                            "cooldown_until": "2026-03-10T17:02:39",
                            "last_sent_at": "2026-03-10T15:02:39",
                            "last_channels": ["email"],
                        }
                    ),
                    "updated_at": "2026-03-10T15:02:39",
                }
            ),
            get_policy_runtime_state=lambda key: (
                {
                    "state_key": key,
                    "state_value": "self_modify_finished",
                    "metadata": {
                        "status": "success",
                        "pattern_name": "narrative_synthesis_empty",
                        "component": "deep_research.tool._create_narrative",
                        "requested_fix_mode": "self_modify_safe",
                        "execution_mode": "self_modify_safe",
                        "route_target": "self_modify",
                        "reason": "pytest_targeted:passed",
                    },
                    "updated_at": "2026-03-10T15:05:00",
                }
                if str(key) == "m18_hardening_last_event"
                else {
                    "state_key": key,
                    "state_value": "active",
                    "metadata": {
                        "proposals_total": 2,
                        "tasks_created_total": 2,
                        "self_modify_attempts_total": 1,
                        "self_modify_successes_total": 1,
                    },
                    "updated_at": "2026-03-10T15:05:00",
                }
                if str(key) == "m18_hardening_metrics"
                else None
            ),
        ),
    )
    monkeypatch.setattr(
        status_snapshot,
        "build_autonomy_observation_summary",
        lambda: {
            "request_correlation": {
                "chat_requests_total": 4,
                "chat_completed_total": 3,
                "chat_failed_total": 1,
                "dispatcher_routes_total": 4,
                "request_routes_total": 4,
                "task_routes_total": 1,
                "task_started_total": 1,
                "task_completed_total": 0,
                "task_failed_total": 1,
                "user_visible_failures_total": 1,
                "recent_requests": [
                    {
                        "event_type": "chat_request_received",
                        "observed_at": "2026-03-10T15:09:00+01:00",
                        "request_id": "req-4",
                        "session_id": "canvas_demo",
                        "source": "canvas_chat",
                        "query_preview": "zeige mir den letzten fehler",
                    }
                ],
                "recent_routes": [
                    {
                        "event_type": "request_route_selected",
                        "observed_at": "2026-03-10T15:09:01+01:00",
                        "request_id": "req-4",
                        "session_id": "canvas_demo",
                        "task_id": "",
                        "source": "canvas_chat",
                        "agent": "meta",
                        "route_source": "dispatcher",
                    }
                ],
                "recent_outcomes": [
                    {
                        "event_type": "chat_request_completed",
                        "observed_at": "2026-03-10T15:09:05+01:00",
                        "request_id": "req-4",
                        "session_id": "canvas_demo",
                        "task_id": "",
                        "source": "canvas_chat",
                        "agent": "meta",
                        "error_class": "",
                        "incident_key": "",
                        "query_preview": "zeige mir den letzten fehler",
                    }
                ],
                "recent_failures": [
                    {
                        "event_type": "task_execution_failed",
                        "observed_at": "2026-03-10T15:08:55+01:00",
                        "request_id": "",
                        "session_id": "auto_1",
                        "task_id": "task-9",
                        "agent": "research",
                        "source": "autonomous_runner",
                        "incident_key": "m3_mcp_health_unavailable",
                        "error_class": "task_exception",
                        "error": "timeout",
                        "query_preview": "incident followup",
                    }
                ],
            }
        },
    )
    monkeypatch.setattr(
        status_snapshot,
        "build_ops_observability_summary",
        lambda **kwargs: {
            "state": "warn",
            "critical_alerts": 0,
            "warnings": 2,
            "failing_services": 0,
            "unhealthy_providers": 1,
            "alerts": [
                {"severity": "warn", "message": "Provider openrouter: error"},
                {"severity": "warn", "message": "Routing meta: conf 0.55"},
            ],
            "top_tool_failures": [],
            "top_routing_risks": [],
            "llm_success_rate": 0.98,
        },
    )
    monkeypatch.setattr(
        status_snapshot,
        "get_public_budget_status",
        lambda: {
            "state": "soft_limit",
            "message": "global=soft_limit ($0.034500)",
            "scopes": [
                {
                    "scope": "global",
                    "current_cost_usd": 0.0345,
                    "warn_usd": 0.02,
                    "soft_limit_usd": 0.03,
                    "hard_limit_usd": 0.05,
                    "state": "soft_limit",
                }
            ],
            "soft_max_tokens": 600,
            "window_days": 1,
        },
    )
    monkeypatch.setattr(status_snapshot.httpx, "AsyncClient", lambda **kwargs: _DummyAsyncClient())

    snapshot = await status_snapshot.collect_status_snapshot("http://127.0.0.1:5000")

    assert snapshot["thinking"] is True
    assert snapshot["services"]["mcp"]["active"] == "active"
    assert snapshot["services"]["qdrant"]["active"] == "active"
    assert snapshot["local"]["qdrant_ready"]["status_code"] == 200
    assert snapshot["restart"]["status"] in {"missing", "completed", "running", "error", "unknown"}
    assert snapshot["providers"]["openrouter"]["state"] == "ok"
    assert snapshot["usage"]["total_requests"] == 6
    assert snapshot["budget"]["state"] == "soft_limit"
    assert snapshot["ops"]["state"] == "warn"
    assert snapshot["self_healing"]["open_incidents"] == 1
    assert snapshot["self_hardening"]["last_event"] == "self_modify_finished"
    assert snapshot["self_hardening"]["metrics"]["self_modify_successes_total"] == 1
    assert snapshot["location"]["active_device_id"] == "pixel8"
    assert snapshot["location"]["location"]["presence_status"] == "live"
    assert snapshot["location"]["controls"]["sharing_enabled"] is True
    assert snapshot["self_healing"]["circuit_breakers_open"] == 1
    assert snapshot["self_healing"]["open_breakers"][0]["component"] == "mcp"
    assert snapshot["self_healing"]["incidents"][0]["notification_state"] == "cooldown_active"
    assert snapshot["self_healing"]["incidents"][0]["recovery_phase"] == "recovering"
    assert snapshot["self_healing"]["incidents"][0]["memory_state"] == "known_bad_pattern"
    assert snapshot["self_healing"]["incidents"][0]["memory_seen_count"] == 3
    assert snapshot["self_healing"]["incidents"][0]["memory_last_outcome"] == "escalated"
    assert snapshot["self_healing"]["incidents"][0]["quarantine_state"] == "active"
    assert snapshot["self_healing"]["resource_guard_state"] == "active"
    assert snapshot["stability_gate"]["state"] == "blocked"
    assert snapshot["mcp_runtime"]["state"] == "recovering"
    assert snapshot["mcp_runtime"]["incident_open"] is True
    assert snapshot["mcp_runtime"]["breaker_open"] is True
    assert snapshot["mcp_runtime"]["stability_gate_state"] == "blocked"
    assert snapshot["request_runtime"]["state"] == "healthy"
    assert snapshot["request_runtime"]["last_request"]["request_id"] == "req-4"
    assert snapshot["request_runtime"]["last_route"]["agent"] == "meta"
    assert snapshot["request_runtime"]["last_correlated_failure"]["task_id"] == "task-9"
    assert snapshot["api_control"]["active_provider_count"] >= 1
    assert snapshot["api_control"]["providers"][0]["api_env"] == "X"

    rows = {row["agent"]: row for row in snapshot["agents"]}
    assert rows["meta"]["runtime_status"] == "thinking"
    assert rows["research"]["runtime_status"] == "completed"
    assert rows["research"]["provider"] == "openrouter"
    assert rows["development"]["provider"] == "inception"
    assert rows["development"]["provider_state"] == "missing"


def test_format_status_message_contains_core_provider_and_agent_sections():
    snapshot = {
        "services": {
            "mcp": {"ok": True, "active": "active"},
            "dispatcher": {"ok": True, "active": "active"},
        },
        "local": {
            "mcp_health": {
                "latency_ms": 31,
                "data": {"status": "healthy", "total_rpc_methods": 150},
            },
            "autonomy_health": {
                "data": {
                    "health": {
                        "goals": {"open_alignment_rate": 92.0},
                        "planning": {"active_plans": 4},
                        "healing": {"degrade_mode": "normal"},
                    }
                }
            },
        },
        "providers": {
            "openrouter": {"state": "ok", "status_code": 200, "latency_ms": 180},
            "openai": {"state": "missing", "status_code": None, "latency_ms": None},
        },
        "agents": [
            {"agent": "meta", "runtime_status": "thinking", "provider": "openrouter", "model": "z-ai/glm-5"},
            {"agent": "development", "runtime_status": "idle", "provider": "inception", "model": "mercury-2"},
        ],
        "usage": {
            "total_requests": 9,
            "input_tokens": 4200,
            "output_tokens": 910,
            "cached_tokens": 200,
            "total_cost_usd": 0.056789,
            "avg_latency_ms": 188.0,
            "top_agents": [{"agent": "meta", "total_cost_usd": 0.031, "total_requests": 4}],
        },
        "budget": {
            "state": "warn",
            "message": "global=warn ($0.056789)",
            "window_days": 1,
            "soft_max_tokens": 600,
            "scopes": [
                {
                    "scope": "global",
                    "current_cost_usd": 0.056789,
                    "warn_usd": 0.040000,
                    "soft_limit_usd": 0.080000,
                    "hard_limit_usd": 0.100000,
                    "state": "warn",
                }
            ],
        },
        "api_control": {
            "active_provider_count": 1,
            "total_requests": 9,
            "total_cost_usd": 0.056789,
            "budget_state": "warn",
            "providers": [
                {
                    "provider": "openrouter",
                    "api_env": "OPENROUTER_API_KEY",
                    "api_configured": True,
                    "state": "ok",
                    "base_url": "https://openrouter.ai/api/v1",
                    "latency_ms": 180,
                    "status_code": 200,
                    "detail": "api ok",
                    "total_requests": 4,
                    "total_cost_usd": 0.031,
                    "input_tokens": 3000,
                    "output_tokens": 700,
                }
            ],
        },
        "ops": {
            "state": "warn",
            "critical_alerts": 0,
            "warnings": 2,
            "failing_services": 0,
            "unhealthy_providers": 1,
            "error_classes": {
                "availability": 1,
                "latency": 0,
                "reliability": 0,
                "routing": 1,
                "budget": 0,
                "orchestration": 0,
            },
            "slo": {
                "breached": 2,
                "healthy": 6,
                "items": [],
            },
            "alerts": [
                {"severity": "warn", "error_class": "availability", "message": "Provider openrouter: error"},
                {"severity": "warn", "error_class": "routing", "message": "Routing meta: conf 0.55"},
            ],
            "top_outliers": [
                {"target": "openrouter", "message": "Provider openrouter: error"},
            ],
        },
        "self_healing": {
            "open_incidents": 1,
            "degrade_mode": "degraded",
            "circuit_breakers_open": 1,
            "open_breakers": [
                {
                    "component": "mcp",
                    "signal": "mcp_health",
                    "opened_until": "2026-03-10T15:18:00",
                }
            ],
            "resource_guard_state": "active",
            "resource_guard_reason": "degrade_mode=degraded,m3_system_pressure",
            "resource_guard_until": "2026-03-10T15:22:00",
            "incidents": [
                {
                    "component": "mcp",
                    "signal": "mcp_health",
                    "severity": "high",
                    "recovery_phase": "recovering",
                    "recovery_stage": "diagnose",
                    "memory_state": "known_bad_pattern",
                    "memory_seen_count": 3,
                    "memory_last_outcome": "escalated",
                    "quarantine_state": "active",
                    "quarantine_until": "2026-03-10T15:15:00",
                    "notification_state": "cooldown_active",
                    "cooldown_until": "2026-03-10T17:02:39",
                }
            ],
        },
        "stability_gate": {
            "state": "blocked",
            "circuit_breakers_open": 1,
            "quarantined_incidents": 1,
            "cooldown_incidents": 1,
            "known_bad_patterns": 1,
        },
        "mcp_runtime": {
            "state": "recovering",
            "ready": True,
            "warmup_pending": False,
            "lifecycle_phase": "ready",
            "restart_status": "completed",
            "restart_phase": "post_check",
            "incident_open": True,
            "incident_severity": "high",
            "stability_gate_state": "blocked",
        },
        "request_runtime": {
            "state": "warn",
            "chat_requests_total": 4,
            "chat_completed_total": 3,
            "chat_failed_total": 1,
            "task_failed_total": 1,
            "last_request": {
                "request_id": "req-4",
                "source": "canvas_chat",
                "query_preview": "zeige mir den letzten fehler",
            },
            "last_route": {
                "event_type": "request_route_selected",
                "agent": "meta",
                "source": "canvas_chat",
                "task_id": "",
            },
            "last_correlated_failure": {
                "event_type": "task_execution_failed",
                "error_class": "task_exception",
                "query_preview": "incident followup",
            },
        },
        "thinking": True,
    }

    msg = status_snapshot.format_status_message(snapshot, ["🟢 Scheduler | 12 Beats | alle 15.0 min", "📋 Queue: ⏳1 🔄0 ✅5 ❌0"])

    assert "🤖 Timus Status" in msg
    assert "Core" in msg
    assert "MCP Runtime: recovering | lifecycle ready | ready yes | restart completed/post_check | incident open high | gate blocked" in msg
    assert "Request Runtime: State warn | Req 4 | Done 3 | Fail 1 | TaskFail 1" in msg
    assert "Letzte Anfrage canvas_chat | req req-4 | zeige mir den letzten fehler" in msg
    assert "Letzte Route request_route_selected -> meta | source canvas_chat | task -" in msg
    assert "Letzter Fehler task_execution_failed | task_exception | incident followup" in msg
    assert "Self-Healing" in msg
    assert "Ops" in msg
    assert "LLM/API Health" in msg
    assert "Kosten / Usage" in msg
    assert "Agenten" in msg
    assert "MCP Service: active" in msg
    assert "🟠 State warn | Critical 0 | Warnings 2 | Services 0 | Providers 1" in msg
    assert "SLO: breached 2 | healthy 6" in msg
    assert "Classes: avail 1 | latency 0 | reliability 0 | routing 1 | budget 0 | orchestration 0" in msg
    assert "Open 1 | Degrade degraded" in msg
    assert "Gate blocked | Breakers 1 | Quarantine 1 | Cooldown 1 | Patterns 1" in msg
    assert "Resource-Guard active | degrade_mode=degraded,m3_system_pressure | bis 2026-03-10T15:22" in msg
    assert "Breaker mcp/mcp_health | offen bis 2026-03-10T15:18" in msg
    assert "mcp/mcp_health [high] | recovering/diagnose | memory known_bad_pattern (3x/escalated) | quarantine active | notify cooldown_active | cooldown bis 2026-03-10T17:02 | quarantine bis 2026-03-10T15:15" in msg
    assert "warn [availability]: Provider openrouter: error" in msg
    assert "Outlier openrouter: Provider openrouter: error" in msg
    assert "openrouter: ok | HTTP 200 | 180 ms" in msg
    assert "Cost $0.056789" in msg
    assert "🟠 Budget warn | Window 1d | Soft MaxTokens 600" in msg
    assert "Alert: global=warn ($0.056789)" in msg
    assert "global: $0.056789 | warn $0.040000 | soft $0.080000 | hard $0.100000 | warn" in msg
    assert "Agent meta: $0.031000 | 4 req" in msg
    assert "meta" in msg
    assert "z-ai/glm-5" in msg


def test_build_mcp_runtime_correlation_prioritizes_restart_over_other_states():
    result = status_snapshot._build_mcp_runtime_correlation(
        services={
            "mcp": {
                "active": "active",
                "ok": True,
                "uptime_seconds": 180.0,
            }
        },
        local={
            "mcp_health": {
                "ok": True,
                "status_code": 200,
                "latency_ms": 24,
                "data": {
                    "status": "healthy",
                    "ready": True,
                    "warmup_pending": False,
                    "transient": False,
                    "lifecycle": {"phase": "ready"},
                },
            }
        },
        restart={
            "exists": True,
            "status": "running",
            "phase": "drain",
            "request_id": "r-1",
            "age_seconds": 2.5,
        },
        self_healing={"incidents": [], "open_breakers": []},
        stability_gate={"state": "pass"},
    )

    assert result["state"] == "restart_in_progress"
    assert result["restart_status"] == "running"
    assert result["restart_phase"] == "drain"
    assert result["restart_request_id"] == "r-1"
    assert result["restart_stale"] is False


def test_build_mcp_runtime_correlation_missing_uptime_does_not_fake_startup_grace():
    result = status_snapshot._build_mcp_runtime_correlation(
        services={
            "mcp": {
                "active": "active",
                "ok": True,
            }
        },
        local={
            "mcp_health": {
                "ok": True,
                "status_code": 200,
                "latency_ms": 18,
                "data": {
                    "status": "healthy",
                    "ready": True,
                    "warmup_pending": False,
                    "transient": False,
                    "lifecycle": {"phase": "ready"},
                },
            }
        },
        restart={"exists": False, "status": "missing", "phase": ""},
        self_healing={
            "incidents": [
                {
                    "incident_key": "m3_mcp_health_unavailable",
                    "component": "mcp",
                    "signal": "mcp_health",
                    "severity": "high",
                    "recovery_phase": "recovering",
                }
            ],
            "open_breakers": [],
        },
        stability_gate={"state": "warn"},
    )

    assert result["startup_grace"] is False
    assert result["state"] == "recovering"


def test_build_mcp_runtime_correlation_ignores_stale_restart_artifact():
    result = status_snapshot._build_mcp_runtime_correlation(
        services={
            "mcp": {
                "active": "active",
                "ok": True,
                "uptime_seconds": 180.0,
            }
        },
        local={
            "mcp_health": {
                "ok": True,
                "status_code": 200,
                "latency_ms": 14,
                "data": {
                    "status": "healthy",
                    "ready": True,
                    "warmup_pending": False,
                    "transient": False,
                    "lifecycle": {"phase": "ready"},
                },
            }
        },
        restart={
            "exists": True,
            "status": "running",
            "phase": "preflight",
            "request_id": "old-r",
            "age_seconds": 7200.0,
            "stale": True,
        },
        self_healing={"incidents": [], "open_breakers": []},
        stability_gate={"state": "pass"},
    )

    assert result["restart_stale"] is True
    assert result["state"] == "healthy"


def test_read_restart_status_marks_old_running_preflight_as_stale(monkeypatch, tmp_path):
    restart_file = tmp_path / "timus_restart_status.json"
    restart_file.write_text(
        json.dumps(
            {
                "status": "running",
                "phase": "preflight",
                "request_id": "stale-r",
            }
        ),
        encoding="utf-8",
    )
    old_mtime = restart_file.stat().st_mtime - (status_snapshot.E2E_WARN_STALE_RESTART_STATUS_SECONDS + 10)
    os.utime(restart_file, (old_mtime, old_mtime))
    monkeypatch.setattr(status_snapshot, "_RESTART_STATUS_PATH", restart_file)

    result = status_snapshot._read_restart_status()

    assert result["exists"] is True
    assert result["status"] == "running"
    assert result["phase"] == "preflight"
    assert result["stale"] is True
