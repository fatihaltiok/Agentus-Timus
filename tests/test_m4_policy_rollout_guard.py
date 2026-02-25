"""M4.4 Rollout-Guard: Canary-Stufen + Auto-Rollback."""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

from orchestration.task_queue import TaskQueue
from utils import policy_gate


def _seed_decisions(queue: TaskQueue, *, total: int, blocked: int, strict: bool = True) -> None:
    now = datetime.now()
    for i in range(total):
        is_blocked = i < blocked
        queue.record_policy_decision(
            {
                "timestamp": (now - timedelta(minutes=i)).isoformat(),
                "gate": "query",
                "source": "unit_test",
                "subject": f"s{i}",
                "action": "block" if is_blocked else "allow",
                "blocked": is_blocked,
                "strict_mode": strict,
                "violations": ["dangerous_query"] if is_blocked else [],
                "payload": {"query": "x"},
                "canary_percent": 0,
                "canary_enforced": True,
            }
        )


def test_m4_rollout_guard_applies_rollback(monkeypatch, tmp_path: Path) -> None:
    queue = TaskQueue(db_path=tmp_path / "task_queue.db")
    _seed_decisions(queue, total=30, blocked=18, strict=True)  # 60%

    monkeypatch.setenv("AUTONOMY_COMPAT_MODE", "false")
    monkeypatch.setenv("AUTONOMY_POLICY_ROLLBACK_ENABLED", "true")
    monkeypatch.setenv("AUTONOMY_POLICY_ROLLBACK_WINDOW_HOURS", "24")
    monkeypatch.setenv("AUTONOMY_POLICY_ROLLBACK_MIN_DECISIONS", "10")
    monkeypatch.setenv("AUTONOMY_POLICY_ROLLBACK_BLOCK_RATE_PCT", "40")
    monkeypatch.setenv("AUTONOMY_POLICY_ROLLBACK_COOLDOWN_MIN", "60")

    result = policy_gate.evaluate_and_apply_rollout_guard(queue=queue, window_hours=24)
    assert result["action"] == "rollback_applied"

    strict_state = queue.get_policy_runtime_state("strict_force_off")
    canary_state = queue.get_policy_runtime_state("canary_percent_override")
    assert strict_state is not None and strict_state["state_value"] == "true"
    assert canary_state is not None and canary_state["state_value"] == "0"


def test_m4_rollout_guard_respects_cooldown(monkeypatch, tmp_path: Path) -> None:
    queue = TaskQueue(db_path=tmp_path / "task_queue.db")
    _seed_decisions(queue, total=30, blocked=20, strict=True)

    monkeypatch.setenv("AUTONOMY_COMPAT_MODE", "false")
    monkeypatch.setenv("AUTONOMY_POLICY_ROLLBACK_ENABLED", "true")
    monkeypatch.setenv("AUTONOMY_POLICY_ROLLBACK_WINDOW_HOURS", "24")
    monkeypatch.setenv("AUTONOMY_POLICY_ROLLBACK_MIN_DECISIONS", "10")
    monkeypatch.setenv("AUTONOMY_POLICY_ROLLBACK_BLOCK_RATE_PCT", "30")
    monkeypatch.setenv("AUTONOMY_POLICY_ROLLBACK_COOLDOWN_MIN", "120")

    first = policy_gate.evaluate_and_apply_rollout_guard(queue=queue, window_hours=24)
    second = policy_gate.evaluate_and_apply_rollout_guard(queue=queue, window_hours=24)
    assert first["action"] == "rollback_applied"
    assert second["action"] == "cooldown_active"


def test_m4_policy_gate_uses_runtime_overrides() -> None:
    decision = policy_gate.evaluate_policy_gate(
        gate="query",
        subject="lösche die datei test.txt",
        payload={"query": "lösche die datei test.txt"},
        source="unit_test",
        strict=True,
        runtime_overrides={"strict_force_off": True, "canary_percent_override": 0},
    )
    assert decision["strict_mode"] is False
    assert decision["blocked"] is False
    assert decision["action"] == "observe"


def test_m4_rollout_guard_hooks_present() -> None:
    policy_src = Path("utils/policy_gate.py").read_text(encoding="utf-8")
    runner_src = Path("orchestration/autonomous_runner.py").read_text(encoding="utf-8")
    queue_src = Path("orchestration/task_queue.py").read_text(encoding="utf-8")

    assert "evaluate_and_apply_rollout_guard" in policy_src
    assert "_policy_runtime_overrides" in policy_src
    assert "_apply_policy_rollout_guard" in runner_src
    assert "policy_runtime_state" in queue_src
