"""
M2 Gate-Tests — Delegation Resilience: Timeout + Retry.
"""

import asyncio
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def _base_registry():
    from agent.agent_registry import AgentRegistry

    registry = AgentRegistry()

    async def _fake_tools():
        return "tools"

    registry._get_tools_description = _fake_tools
    return registry


@pytest.mark.asyncio
async def test_timeout_bei_langsamem_agent(monkeypatch):
    """T2.1 — TimeoutError wenn Agent zu lange braucht."""
    monkeypatch.setenv("DELEGATION_TIMEOUT", "0.05")
    monkeypatch.setenv("DELEGATION_MAX_RETRIES", "1")

    registry = _base_registry()

    class _SlowAgent:
        async def run(self, task: str) -> str:
            await asyncio.sleep(10)  # Weit ueber dem Timeout
            return "never"

    registry.register_spec(
        "slow", "slow", ["slow"],
        lambda tools_description_string: _SlowAgent(),
    )

    result = await registry.delegate(from_agent="executor", to_agent="slow", task="wait")
    assert result["status"] == "error", f"Erwartet error, bekam: {result}"
    assert "fehlgeschlagen" in result["error"].lower() or "timeout" in result["error"].lower() or "FEHLER" in result["error"]


@pytest.mark.asyncio
async def test_retry_bei_voruebergehendem_fehler(monkeypatch):
    """T2.2 — Retry: 1. Versuch schlaegt fehl, 2. Versuch erfolgreich."""
    monkeypatch.setenv("DELEGATION_TIMEOUT", "5")
    monkeypatch.setenv("DELEGATION_MAX_RETRIES", "2")

    registry = _base_registry()
    call_count = [0]

    class _FlakyAgent:
        async def run(self, task: str) -> str:
            call_count[0] += 1
            if call_count[0] == 1:
                raise RuntimeError("Voruebergehender Fehler")
            return "recovered"

    registry.register_spec(
        "flaky", "flaky", ["flaky"],
        lambda tools_description_string: _FlakyAgent(),
    )

    result = await registry.delegate(
        from_agent="executor",
        to_agent="flaky",
        task="retry test",
    )
    assert result["status"] == "success", f"Erwartet success nach Retry, bekam: {result}"
    assert result["result"] == "recovered"
    assert call_count[0] == 2, f"Erwartet 2 Aufrufe, hatte: {call_count[0]}"


@pytest.mark.asyncio
async def test_kein_retry_bei_nicht_registriert(monkeypatch):
    """T2.3 — Kein Retry bei 'Agent nicht registriert' — sofort Fehler."""
    monkeypatch.setenv("DELEGATION_MAX_RETRIES", "3")

    registry = _base_registry()
    # Kein Agent registriert

    result = await registry.delegate(
        from_agent="executor",
        to_agent="ghost",
        task="does not exist",
    )
    assert result["status"] == "error"
    assert "nicht registriert" in result["error"]


@pytest.mark.asyncio
async def test_stack_reset_nach_timeout(monkeypatch):
    """T2.4 — Nach Timeout ist der Delegation-Stack wieder leer."""
    monkeypatch.setenv("DELEGATION_TIMEOUT", "0.05")
    monkeypatch.setenv("DELEGATION_MAX_RETRIES", "1")

    registry = _base_registry()

    class _SlowAgent:
        async def run(self, task: str) -> str:
            await asyncio.sleep(10)
            return "never"

    class _FastAgent:
        async def run(self, task: str) -> str:
            return "fast"

    registry.register_spec(
        "slow", "slow", ["slow"],
        lambda tools_description_string: _SlowAgent(),
    )
    registry.register_spec(
        "fast", "fast", ["fast"],
        lambda tools_description_string: _FastAgent(),
    )

    # Erst Timeout provozieren
    await registry.delegate(from_agent="executor", to_agent="slow", task="timeout")

    # Stack muss danach leer sein
    stack = registry._delegation_stack_var.get()
    assert stack == (), f"Stack nach Timeout nicht leer: {stack}"

    # Neue Delegation muss funktionieren
    result = await registry.delegate(
        from_agent="executor",
        to_agent="fast",
        task="after timeout",
    )
    assert result["status"] == "success"


@pytest.mark.asyncio
async def test_timeout_konfigurierbar(monkeypatch):
    """T2.5 — DELEGATION_TIMEOUT ist via ENV konfigurierbar."""
    monkeypatch.setenv("DELEGATION_TIMEOUT", "0.1")
    monkeypatch.setenv("DELEGATION_MAX_RETRIES", "1")

    registry = _base_registry()
    started_at = [None]
    finished_at = [None]

    class _SleepAgent:
        async def run(self, task: str) -> str:
            import time
            started_at[0] = time.monotonic()
            await asyncio.sleep(5)
            finished_at[0] = time.monotonic()
            return "done"

    registry.register_spec(
        "sleeper", "sleeper", ["sleeper"],
        lambda tools_description_string: _SleepAgent(),
    )

    import time
    t0 = time.monotonic()
    result = await registry.delegate(from_agent="executor", to_agent="sleeper", task="sleep")
    elapsed = time.monotonic() - t0

    assert result["status"] == "error"
    # Muss deutlich kuerzer als 5s gewesen sein (Timeout bei 0.1s)
    assert elapsed < 2.0, f"Timeout hat nicht funktioniert, elapsed={elapsed:.2f}s"
