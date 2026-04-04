"""CrossHair + Hypothesis contracts for MCP health transient lifecycle states."""

import deal
from hypothesis import given, settings
from hypothesis import strategies as st

from gateway import status_snapshot
from orchestration.self_healing_engine import SelfHealingEngine


@deal.post(lambda r: isinstance(r, bool))
def _contract_verified_outage_for_mcp_health(
    ok_flag: bool,
    status: str,
    transient: bool,
    lifecycle_phase: str,
    has_error: bool,
) -> bool:
    engine = SelfHealingEngine.__new__(SelfHealingEngine)
    details = {
        "ok": ok_flag,
        "status": status,
        "transient": transient,
        "lifecycle_phase": lifecycle_phase,
    }
    if has_error:
        details["error"] = "runtime_error"
    return engine._is_verified_outage(component="mcp", signal="mcp_health", details=details)


@given(
    st.sampled_from(["starting", "shutting_down"]),
    st.sampled_from(["startup", "warmup", "shutdown"]),
)
@settings(max_examples=24)
def test_hypothesis_transient_mcp_lifecycle_states_are_not_verified_outages(
    status: str,
    lifecycle_phase: str,
) -> None:
    result = _contract_verified_outage_for_mcp_health(
        False,
        status,
        True,
        lifecycle_phase,
        False,
    )
    assert result is False


def test_mcp_health_verified_outage_still_triggers_for_real_down_state() -> None:
    result = _contract_verified_outage_for_mcp_health(
        False,
        "down",
        False,
        "ready",
        False,
    )
    assert result is True


@deal.post(
    lambda r: r["state"]
    in {"healthy", "restart_in_progress", "transient_lifecycle", "startup_grace", "outage", "recovering"}
)
@deal.post(lambda r: isinstance(r["startup_grace"], bool))
@deal.post(lambda r: isinstance(r["service_ok"], bool) and isinstance(r["http_ok"], bool))
def _contract_mcp_runtime_correlation(
    status: str,
    lifecycle_phase: str,
    transient: bool,
    warmup_pending: bool,
    restart_running: bool,
) -> dict:
    return status_snapshot._build_mcp_runtime_correlation(
        services={
            "mcp": {
                "active": "active",
                "ok": True,
                "uptime_seconds": 120.0,
            }
        },
        local={
            "mcp_health": {
                "ok": True,
                "status_code": 200,
                "latency_ms": 25,
                "data": {
                    "status": status,
                    "ready": status not in {"starting", "shutting_down"},
                    "warmup_pending": warmup_pending,
                    "transient": transient,
                    "lifecycle": {"phase": lifecycle_phase},
                },
            }
        },
        restart={
            "exists": restart_running,
            "status": "running" if restart_running else "completed",
            "phase": "drain" if restart_running else "steady",
            "age_seconds": 2.0,
        },
        self_healing={"incidents": [], "open_breakers": []},
        stability_gate={"state": "pass"},
    )


@given(
    st.sampled_from(["starting", "shutting_down"]),
    st.sampled_from(["startup", "warmup", "shutdown"]),
)
@settings(max_examples=24)
def test_hypothesis_transient_mcp_runtime_maps_to_transient_lifecycle(
    status: str,
    lifecycle_phase: str,
) -> None:
    result = _contract_mcp_runtime_correlation(
        status=status,
        lifecycle_phase=lifecycle_phase,
        transient=True,
        warmup_pending=False,
        restart_running=False,
    )
    assert result["state"] == "transient_lifecycle"


@given(st.sampled_from(["startup", "warmup", "ready", "shutdown"]))
@settings(max_examples=16)
def test_hypothesis_restart_running_dominates_runtime_state(lifecycle_phase: str) -> None:
    result = _contract_mcp_runtime_correlation(
        status="healthy",
        lifecycle_phase=lifecycle_phase,
        transient=False,
        warmup_pending=False,
        restart_running=True,
    )
    assert result["state"] == "restart_in_progress"
