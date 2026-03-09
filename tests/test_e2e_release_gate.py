from __future__ import annotations

import pytest

from orchestration.e2e_release_gate import (
    build_e2e_gate_alert_message,
    evaluate_e2e_release_gate,
)
from tools.self_improvement_tool.tool import get_e2e_release_gate_status


def test_e2e_release_gate_blocks_on_blocking_failures():
    decision = evaluate_e2e_release_gate(
        {
            "summary": {"total": 4, "passed": 2, "warned": 0, "failed": 2, "blocking_failed": 1},
            "flows": [
                {"flow": "telegram_status", "status": "fail", "blocking": True},
                {"flow": "email_backend", "status": "pass", "blocking": True},
            ],
        },
        current_canary_percent=30,
    )

    assert decision["state"] == "blocked"
    assert decision["release_blocked"] is True
    assert decision["canary_blocked"] is True
    assert decision["recommended_canary_percent"] == 0
    assert "telegram_status" in decision["blocking_flows"]


def test_e2e_release_gate_warns_without_full_block():
    decision = evaluate_e2e_release_gate(
        {
            "summary": {"total": 4, "passed": 3, "warned": 1, "failed": 0, "blocking_failed": 0},
            "flows": [
                {"flow": "meta_visual_browser", "status": "warn", "blocking": True},
            ],
        },
        current_canary_percent=20,
    )

    assert decision["state"] == "warn"
    assert decision["release_blocked"] is False
    assert decision["canary_deferred"] is True
    assert decision["recommended_canary_percent"] == 20


def test_e2e_release_gate_warns_on_startup_grace_only():
    decision = evaluate_e2e_release_gate(
        {
            "summary": {"total": 4, "passed": 3, "warned": 1, "failed": 0, "blocking_failed": 0},
            "flows": [
                {"flow": "telegram_status", "status": "warn", "blocking": True},
            ],
        },
        current_canary_percent=15,
    )

    assert decision["state"] == "warn"
    assert decision["release_blocked"] is False
    assert decision["canary_deferred"] is True
    assert decision["recommended_canary_percent"] == 15


def test_build_e2e_gate_alert_message_contains_summary():
    matrix = {
        "summary": {"total": 4, "passed": 2, "warned": 1, "failed": 1, "blocking_failed": 1},
        "flows": [],
    }
    decision = {
        "state": "blocked",
        "release_blocked": True,
        "canary_deferred": True,
        "recommended_canary_percent": 0,
        "blocking_flows": ["telegram_status"],
        "failed_flows": ["telegram_status"],
        "warning_flows": ["meta_visual_browser"],
    }

    msg = build_e2e_gate_alert_message(matrix, decision)

    assert "E2E Release Gate" in msg
    assert "State blocked" in msg
    assert "blocking_failed=1" in msg
    assert "Blocking: telegram_status" in msg


@pytest.mark.asyncio
async def test_get_e2e_release_gate_status_can_send_alert(monkeypatch):
    async def _fake_matrix():
        return {
            "status": "ok",
            "summary": {"total": 4, "passed": 2, "warned": 1, "failed": 1, "blocking_failed": 1},
            "flows": [
                {"flow": "telegram_status", "status": "fail", "blocking": True},
            ],
        }

    sent = []

    async def _fake_send_telegram(msg, parse_mode="Markdown"):
        sent.append((msg, parse_mode))
        return True

    monkeypatch.setattr(
        "tools.self_improvement_tool.tool.get_e2e_regression_matrix",
        _fake_matrix,
    )
    monkeypatch.setattr(
        "utils.telegram_notify.send_telegram",
        _fake_send_telegram,
    )

    result = await get_e2e_release_gate_status(current_canary_percent=40, notify=True)

    assert result["status"] == "ok"
    assert result["decision"]["state"] == "blocked"
    assert result["alert_sent"] is True
    assert sent
