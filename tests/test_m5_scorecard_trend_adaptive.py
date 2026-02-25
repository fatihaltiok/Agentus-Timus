"""M5.3 Scorecard-Trends + adaptive Thresholds."""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

from orchestration.autonomy_scorecard import (
    build_autonomy_scorecard,
    evaluate_and_apply_scorecard_control,
)
from orchestration.task_queue import TaskQueue


def _snapshot(score: float) -> dict:
    return {
        "overall_score": float(score),
        "overall_score_10": round(float(score) / 10.0, 2),
        "autonomy_level": "very_high" if score >= 85 else ("high" if score >= 75 else "medium"),
        "ready_for_very_high_autonomy": bool(score >= 85),
        "pillars": {},
        "control": {},
        "window_hours": 24,
    }


def _control_card(score: float, mode: str = "normal") -> dict:
    return {
        "overall_score": float(score),
        "pillars": {
            "self_healing": {"degrade_mode": mode},
        },
    }


def test_m5_trend_metrics_from_snapshots(tmp_path: Path) -> None:
    queue = TaskQueue(db_path=tmp_path / "task_queue.db")
    now = datetime.now()

    for i, score in enumerate([58, 60, 62, 63, 64]):
        queue.record_autonomy_scorecard_snapshot(
            _snapshot(float(score)),
            observed_at=(now - timedelta(days=10 - i)).isoformat(),
        )
    for i, score in enumerate([72, 76, 80]):
        queue.record_autonomy_scorecard_snapshot(
            _snapshot(float(score)),
            observed_at=(now - timedelta(hours=10 - (i * 3))).isoformat(),
        )

    trends = queue.get_autonomy_scorecard_trends(window_hours=24, baseline_days=30)
    assert trends["samples_window"] >= 3
    assert trends["samples_baseline"] >= 8
    assert trends["trend_direction"] == "improving"
    assert float(trends["trend_delta"]) > 0.0
    assert float(trends["avg_score_window"]) > float(trends["avg_score_baseline"])


def test_m5_adaptive_thresholds_tighten(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("AUTONOMY_COMPAT_MODE", "false")
    monkeypatch.setenv("AUTONOMY_SCORECARD_CONTROL_ENABLED", "true")
    monkeypatch.setenv("AUTONOMY_SCORECARD_ADAPTIVE_THRESHOLDS_ENABLED", "true")
    monkeypatch.setenv("AUTONOMY_SCORECARD_PROMOTE_THRESHOLD", "80")
    monkeypatch.setenv("AUTONOMY_SCORECARD_ROLLBACK_THRESHOLD", "55")
    monkeypatch.setenv("AUTONOMY_SCORECARD_CONTROL_COOLDOWN_MIN", "60")
    monkeypatch.setenv("AUTONOMY_SCORECARD_TREND_BASELINE_DAYS", "30")

    queue = TaskQueue(db_path=tmp_path / "task_queue.db")
    queue.set_policy_runtime_state("canary_percent_override", "40")
    now = datetime.now()
    for i, score in enumerate([88, 86, 84, 82]):
        queue.record_autonomy_scorecard_snapshot(
            _snapshot(float(score)),
            observed_at=(now - timedelta(days=12 - i)).isoformat(),
        )
    for i, score in enumerate([44, 67, 46]):
        queue.record_autonomy_scorecard_snapshot(
            _snapshot(float(score)),
            observed_at=(now - timedelta(hours=8 - (i * 2))).isoformat(),
        )

    result = evaluate_and_apply_scorecard_control(
        queue=queue,
        scorecard=_control_card(79.0, mode="normal"),
    )
    assert result["action"] == "hold"
    assert result["adaptive_mode"] == "tighten"
    assert float(result["promote_threshold"]) > 80.0
    assert float(result["rollback_threshold"]) > 55.0


def test_m5_adaptive_thresholds_relax_and_promote(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("AUTONOMY_COMPAT_MODE", "false")
    monkeypatch.setenv("AUTONOMY_SCORECARD_CONTROL_ENABLED", "true")
    monkeypatch.setenv("AUTONOMY_SCORECARD_ADAPTIVE_THRESHOLDS_ENABLED", "true")
    monkeypatch.setenv("AUTONOMY_SCORECARD_PROMOTE_THRESHOLD", "80")
    monkeypatch.setenv("AUTONOMY_SCORECARD_ROLLBACK_THRESHOLD", "55")
    monkeypatch.setenv("AUTONOMY_SCORECARD_PROMOTE_STEP", "10")
    monkeypatch.setenv("AUTONOMY_SCORECARD_MAX_CANARY", "100")
    monkeypatch.setenv("AUTONOMY_SCORECARD_CONTROL_COOLDOWN_MIN", "60")
    monkeypatch.setenv("AUTONOMY_SCORECARD_TREND_BASELINE_DAYS", "30")

    queue = TaskQueue(db_path=tmp_path / "task_queue.db")
    queue.set_policy_runtime_state("canary_percent_override", "20")
    queue.set_policy_runtime_state("strict_force_off", "true")
    now = datetime.now()
    for i, score in enumerate([61, 62, 63, 64, 65]):
        queue.record_autonomy_scorecard_snapshot(
            _snapshot(float(score)),
            observed_at=(now - timedelta(days=9 - i)).isoformat(),
        )
    for i, score in enumerate([78, 79, 80, 81]):
        queue.record_autonomy_scorecard_snapshot(
            _snapshot(float(score)),
            observed_at=(now - timedelta(hours=12 - (i * 3))).isoformat(),
        )

    result = evaluate_and_apply_scorecard_control(
        queue=queue,
        scorecard=_control_card(76.0, mode="normal"),
    )
    assert result["adaptive_mode"] == "relax"
    assert float(result["promote_threshold"]) < 80.0
    assert result["action"] == "promote_canary"
    assert result["next_canary_percent"] == 30


def test_m5_build_scorecard_includes_trends(monkeypatch, tmp_path: Path) -> None:
    queue = TaskQueue(db_path=tmp_path / "task_queue.db")
    now = datetime.now()
    queue.record_autonomy_scorecard_snapshot(_snapshot(70.0), observed_at=(now - timedelta(hours=20)).isoformat())
    queue.record_autonomy_scorecard_snapshot(_snapshot(74.0), observed_at=(now - timedelta(hours=2)).isoformat())

    monkeypatch.setattr(
        "orchestration.autonomy_scorecard.get_policy_decision_metrics",
        lambda window_hours=24: {
            "window_hours": window_hours,
            "decisions_total": 0,
            "blocked_total": 0,
            "observed_total": 0,
            "canary_deferred_total": 0,
            "by_gate": {},
            "strict_force_off": False,
        },
    )
    scorecard = build_autonomy_scorecard(queue=queue, window_hours=24)
    assert "trends" in scorecard
    assert scorecard["trends"]["samples_window"] >= 1
    assert "trend_direction" in scorecard["trends"]


def test_m5_trend_hooks_present() -> None:
    queue_src = Path("orchestration/task_queue.py").read_text(encoding="utf-8")
    score_src = Path("orchestration/autonomy_scorecard.py").read_text(encoding="utf-8")
    runner_src = Path("orchestration/autonomous_runner.py").read_text(encoding="utf-8")
    tg_src = Path("gateway/telegram_gateway.py").read_text(encoding="utf-8")
    cli_src = Path("main_dispatcher.py").read_text(encoding="utf-8")

    assert "record_autonomy_scorecard_snapshot" in queue_src
    assert "get_autonomy_scorecard_trends" in queue_src
    assert "_adaptive_control_thresholds" in score_src
    assert "AUTONOMY_SCORECARD_ADAPTIVE_THRESHOLDS_ENABLED" in score_src
    assert "record_autonomy_scorecard_snapshot" in runner_src
    assert "Scorecard-Trend" in cli_src
    assert "🧭 Trend:" in tg_src

