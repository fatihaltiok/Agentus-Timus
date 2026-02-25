"""M7.1 Hardening + Rollout Gate."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from orchestration.autonomy_change_control import evaluate_and_apply_audit_change_request
from orchestration.autonomy_hardening_engine import evaluate_and_apply_rollout_hardening
from orchestration.task_queue import TaskQueue


def _report(*, recommendation: str, score: float = 80.0, ts: str | None = None) -> dict:
    return {
        "timestamp": ts or datetime.now().isoformat(),
        "window_days": 7,
        "baseline_days": 30,
        "rollout_policy": {
            "recommendation": recommendation,
            "reason": "test_recommendation",
            "risk_flags": [],
        },
        "scorecard": {
            "overall_score": score,
            "autonomy_level": "high",
        },
    }


def test_m7_hardening_green_state(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("AUTONOMY_COMPAT_MODE", "false")
    monkeypatch.setenv("AUTONOMY_HARDENING_ENABLED", "true")
    monkeypatch.setenv("AUTONOMY_HARDENING_ENFORCE", "true")
    monkeypatch.setenv("AUTONOMY_HARDENING_MIN_RECOVERY_RATE_24H", "0")
    monkeypatch.setenv("AUTONOMY_HARDENING_MAX_OPEN_INCIDENTS", "2")
    monkeypatch.setenv("AUTONOMY_HARDENING_MAX_POLICY_BLOCK_RATE_24H", "35")
    monkeypatch.setenv("AUTONOMY_HARDENING_MAX_PENDING_APPROVALS", "5")
    monkeypatch.setenv("AUTONOMY_HARDENING_MIN_AUTONOMY_SCORE", "70")

    queue = TaskQueue(db_path=tmp_path / "task_queue.db")
    queue.set_policy_runtime_state("audit_change_pending_approval_count", "0")
    monkeypatch.setattr(
        queue,
        "get_self_healing_metrics",
        lambda: {
            "open_incidents": 0,
            "recovery_rate_24h": 100.0,
        },
    )
    monkeypatch.setattr(
        "utils.policy_gate.get_policy_decision_metrics",
        lambda window_hours=24: {"decisions_total": 100, "blocked_total": 10},
    )

    result = evaluate_and_apply_rollout_hardening(
        queue=queue,
        scorecard={"overall_score": 85.0},
    )
    assert result["status"] == "ok"
    assert result["state"] == "green"
    assert result["action"] == "normal"

    hardening_state = queue.get_policy_runtime_state("hardening_last_state")
    freeze_state = queue.get_policy_runtime_state("hardening_rollout_freeze")
    assert hardening_state is not None and hardening_state["state_value"] == "green"
    assert freeze_state is not None and freeze_state["state_value"] == "false"


def test_m7_hardening_yellow_freeze(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("AUTONOMY_COMPAT_MODE", "false")
    monkeypatch.setenv("AUTONOMY_HARDENING_ENABLED", "true")
    monkeypatch.setenv("AUTONOMY_HARDENING_ENFORCE", "true")
    monkeypatch.setenv("AUTONOMY_HARDENING_MIN_RECOVERY_RATE_24H", "0")
    monkeypatch.setenv("AUTONOMY_HARDENING_MAX_PENDING_APPROVALS", "0")
    monkeypatch.setenv("AUTONOMY_HARDENING_FREEZE_ON_YELLOW", "true")

    queue = TaskQueue(db_path=tmp_path / "task_queue.db")
    queue.set_policy_runtime_state("audit_change_pending_approval_count", "2")
    monkeypatch.setattr(
        queue,
        "get_self_healing_metrics",
        lambda: {
            "open_incidents": 0,
            "recovery_rate_24h": 100.0,
        },
    )
    monkeypatch.setattr(
        "utils.policy_gate.get_policy_decision_metrics",
        lambda window_hours=24: {"decisions_total": 100, "blocked_total": 0},
    )

    result = evaluate_and_apply_rollout_hardening(
        queue=queue,
        scorecard={"overall_score": 90.0},
    )
    assert result["state"] == "yellow"
    assert result["action"] == "freeze_applied"

    freeze_state = queue.get_policy_runtime_state("hardening_rollout_freeze")
    assert freeze_state is not None and freeze_state["state_value"] == "true"


def test_m7_hardening_red_rollback(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("AUTONOMY_COMPAT_MODE", "false")
    monkeypatch.setenv("AUTONOMY_HARDENING_ENABLED", "true")
    monkeypatch.setenv("AUTONOMY_HARDENING_ENFORCE", "true")
    monkeypatch.setenv("AUTONOMY_HARDENING_MAX_OPEN_INCIDENTS", "1")
    monkeypatch.setenv("AUTONOMY_HARDENING_ROLLBACK_ON_RED", "true")
    monkeypatch.setenv("AUTONOMY_HARDENING_MIN_RECOVERY_RATE_24H", "70")
    monkeypatch.setenv("AUTONOMY_HARDENING_MIN_AUTONOMY_SCORE", "80")

    queue = TaskQueue(db_path=tmp_path / "task_queue.db")
    queue.set_policy_runtime_state("canary_percent_override", "60")
    queue.set_policy_runtime_state("strict_force_off", "false")
    queue.set_policy_runtime_state("audit_change_pending_approval_count", "0")
    monkeypatch.setattr(
        queue,
        "get_self_healing_metrics",
        lambda: {
            "open_incidents": 4,
            "recovery_rate_24h": 20.0,
        },
    )
    monkeypatch.setattr(
        "utils.policy_gate.get_policy_decision_metrics",
        lambda window_hours=24: {"decisions_total": 100, "blocked_total": 80},
    )

    result = evaluate_and_apply_rollout_hardening(
        queue=queue,
        scorecard={"overall_score": 50.0},
    )
    assert result["state"] == "red"
    assert result["action"] == "rollback_applied"

    strict_state = queue.get_policy_runtime_state("strict_force_off")
    canary_state = queue.get_policy_runtime_state("canary_percent_override")
    assert strict_state is not None and strict_state["state_value"] == "true"
    assert canary_state is not None and canary_state["state_value"] == "0"


def test_m7_hardening_freeze_blocks_promote(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("AUTONOMY_COMPAT_MODE", "false")
    monkeypatch.setenv("AUTONOMY_AUDIT_CHANGE_REQUESTS_ENABLED", "true")
    monkeypatch.setenv("AUTONOMY_AUDIT_CHANGE_REQUEST_MIN_INTERVAL_MIN", "1")
    monkeypatch.setenv("AUTONOMY_AUDIT_CHANGE_APPROVAL_ENABLED", "false")
    monkeypatch.setenv("AUTONOMY_AUDIT_CHANGE_PROMOTE_STEP", "10")
    monkeypatch.setenv("AUTONOMY_AUDIT_CHANGE_MAX_CANARY", "100")

    queue = TaskQueue(db_path=tmp_path / "task_queue.db")
    queue.set_policy_runtime_state("canary_percent_override", "20")
    queue.set_policy_runtime_state("hardening_rollout_freeze", "true")

    result = evaluate_and_apply_audit_change_request(
        queue=queue,
        report=_report(recommendation="promote", score=88.0),
        report_path=str(tmp_path / "audit_promote_freeze.json"),
    )
    assert result["action"] == "hold"
    assert result["reason"] == "hardening_freeze_active"


def test_m7_hardening_hooks_present() -> None:
    hardening_src = Path("orchestration/autonomy_hardening_engine.py").read_text(encoding="utf-8")
    runner_src = Path("orchestration/autonomous_runner.py").read_text(encoding="utf-8")
    control_src = Path("orchestration/autonomy_change_control.py").read_text(encoding="utf-8")
    tg_src = Path("gateway/telegram_gateway.py").read_text(encoding="utf-8")
    cli_src = Path("main_dispatcher.py").read_text(encoding="utf-8")
    exports_src = Path("orchestration/__init__.py").read_text(encoding="utf-8")

    assert "build_rollout_hardening_snapshot" in hardening_src
    assert "evaluate_and_apply_rollout_hardening" in hardening_src
    assert "_hardening_feature_enabled" in runner_src
    assert "_evaluate_rollout_hardening" in runner_src
    assert "hardening_rollout_freeze" in control_src
    assert "Hardening" in tg_src
    assert "Hardening" in cli_src
    assert "evaluate_and_apply_rollout_hardening" in exports_src
