from __future__ import annotations

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
    monkeypatch.setattr(status_snapshot, "_service_state", lambda svc: {"service": svc, "active": "active", "ok": True})
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
        "thinking": True,
    }

    msg = status_snapshot.format_status_message(snapshot, ["🟢 Scheduler | 12 Beats | alle 15.0 min", "📋 Queue: ⏳1 🔄0 ✅5 ❌0"])

    assert "🤖 Timus Status" in msg
    assert "Core" in msg
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
