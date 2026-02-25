"""M6.1 Autonomy Audit Report Export."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from orchestration.autonomy_audit_report import (
    build_autonomy_audit_report,
    export_autonomy_audit_report,
    should_export_audit_report,
)
from orchestration.task_queue import TaskQueue


def test_m6_build_audit_report_rollback_recommendation(monkeypatch, tmp_path: Path) -> None:
    queue = TaskQueue(db_path=tmp_path / "task_queue.db")
    queue.set_policy_runtime_state("strict_force_off", "true")
    queue.set_policy_runtime_state("scorecard_governance_state", "force_rollback")

    monkeypatch.setattr(
        "orchestration.autonomy_audit_report.build_autonomy_scorecard",
        lambda queue=None, window_hours=168: {
            "overall_score": 62.0,
            "overall_score_10": 6.2,
            "autonomy_level": "medium",
            "ready_for_very_high_autonomy": False,
            "control": {
                "strict_force_off": True,
                "scorecard_governance_state": "force_rollback",
                "scorecard_last_action": "governance_force_rollback",
            },
            "pillars": {},
        },
    )
    monkeypatch.setattr(
        "orchestration.autonomy_audit_report.get_policy_decision_metrics",
        lambda window_hours=168: {
            "decisions_total": 100,
            "blocked_total": 50,
            "observed_total": 30,
            "strict_decisions": 80,
            "canary_deferred_total": 10,
            "scorecard_governance_state": "force_rollback",
        },
    )
    monkeypatch.setattr(
        queue,
        "get_autonomy_scorecard_trends",
        lambda window_hours=168, baseline_days=30: {
            "trend_direction": "declining",
            "trend_delta": -8.5,
            "volatility_window": 14.2,
            "samples_window": 10,
            "samples_baseline": 25,
        },
    )

    report = build_autonomy_audit_report(queue=queue, window_days=7, baseline_days=30)
    assert report["rollout_policy"]["recommendation"] == "rollback"
    assert "strict_force_off" in report["rollout_policy"]["risk_flags"]
    assert report["rollout_policy"]["governance_state"] == "force_rollback"


def test_m6_export_audit_report_writes_file_and_runtime(monkeypatch, tmp_path: Path) -> None:
    queue = TaskQueue(db_path=tmp_path / "task_queue.db")
    output_dir = tmp_path / "audit_reports"
    monkeypatch.setattr("orchestration.autonomy_audit_report.AUDIT_REPORT_DIR", output_dir)

    report = {
        "timestamp": datetime.now().isoformat(),
        "window_days": 7,
        "window_hours": 168,
        "baseline_days": 30,
        "scorecard": {"overall_score": 83.0},
        "trends": {"trend_direction": "stable"},
        "policy_metrics": {"decisions_total": 10, "blocked_total": 1},
        "rollout_policy": {"recommendation": "hold", "reason": "stability_guard", "risk_flags": []},
    }
    result = export_autonomy_audit_report(queue=queue, report=report)
    path = Path(result["path"])
    assert result["status"] == "ok"
    assert path.exists()
    assert path.parent == output_dir

    rec_state = queue.get_policy_runtime_state("audit_report_last_recommendation")
    path_state = queue.get_policy_runtime_state("audit_report_last_path")
    exported_state = queue.get_policy_runtime_state("audit_report_last_exported_at")
    assert rec_state is not None and rec_state["state_value"] == "hold"
    assert path_state is not None and path_state["state_value"] == str(path)
    assert exported_state is not None and exported_state["state_value"]


def test_m6_should_export_audit_report_cadence(monkeypatch, tmp_path: Path) -> None:
    queue = TaskQueue(db_path=tmp_path / "task_queue.db")
    queue.set_policy_runtime_state("audit_report_last_exported_at", datetime.now().isoformat())

    check = should_export_audit_report(queue=queue, cadence_hours=6)
    assert check["should_export"] is False
    assert check["reason"] == "cadence_not_elapsed"


def test_m6_audit_report_hooks_present() -> None:
    module_src = Path("orchestration/autonomy_audit_report.py").read_text(encoding="utf-8")
    runner_src = Path("orchestration/autonomous_runner.py").read_text(encoding="utf-8")
    tg_src = Path("gateway/telegram_gateway.py").read_text(encoding="utf-8")
    cli_src = Path("main_dispatcher.py").read_text(encoding="utf-8")

    assert "build_autonomy_audit_report" in module_src
    assert "export_autonomy_audit_report" in module_src
    assert "should_export_audit_report" in module_src
    assert "_audit_report_feature_enabled" in runner_src
    assert "_export_autonomy_audit_report" in runner_src
    assert "Autonomy-Audit" in cli_src
    assert "🧾 Audit:" in tg_src

