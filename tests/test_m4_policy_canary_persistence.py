"""M4.3 Canary-Rollout + persistente Policy-Entscheidungen."""

from __future__ import annotations

from pathlib import Path

from orchestration.task_queue import TaskQueue
from utils import policy_gate


def test_m4_canary_defer_in_strict_mode(monkeypatch) -> None:
    monkeypatch.setenv("AUTONOMY_COMPAT_MODE", "false")
    monkeypatch.setenv("AUTONOMY_POLICY_GATES_STRICT", "true")
    monkeypatch.setenv("AUTONOMY_CANARY_PERCENT", "10")
    monkeypatch.setattr(policy_gate, "_canary_bucket_for_key", lambda _key: 99)

    decision = policy_gate.evaluate_policy_gate(
        gate="query",
        subject="lösche die datei test.txt",
        payload={"query": "lösche die datei test.txt"},
        source="unit_test",
    )
    assert decision["strict_mode"] is True
    assert decision["blocked"] is False
    assert decision["action"] == "observe"
    assert decision["canary_enforced"] is False
    assert "canary_deferred" in decision["violations"]


def test_m4_canary_enforce_in_strict_mode(monkeypatch) -> None:
    monkeypatch.setenv("AUTONOMY_COMPAT_MODE", "false")
    monkeypatch.setenv("AUTONOMY_POLICY_GATES_STRICT", "true")
    monkeypatch.setenv("AUTONOMY_CANARY_PERCENT", "10")
    monkeypatch.setattr(policy_gate, "_canary_bucket_for_key", lambda _key: 5)

    decision = policy_gate.evaluate_policy_gate(
        gate="query",
        subject="lösche die datei test.txt",
        payload={"query": "lösche die datei test.txt"},
        source="unit_test",
    )
    assert decision["blocked"] is True
    assert decision["action"] == "block"
    assert decision["canary_enforced"] is True


def test_m4_hard_block_not_deferred_by_canary(monkeypatch) -> None:
    monkeypatch.setenv("AUTONOMY_COMPAT_MODE", "false")
    monkeypatch.setenv("AUTONOMY_POLICY_GATES_STRICT", "true")
    monkeypatch.setenv("AUTONOMY_CANARY_PERCENT", "1")
    monkeypatch.setattr(policy_gate, "_canary_bucket_for_key", lambda _key: 99)

    decision = policy_gate.evaluate_policy_gate(
        gate="tool",
        subject="delete_file",
        payload={"params": {"path": "/tmp/x"}},
        source="unit_test",
    )
    assert decision["blocked"] is True
    assert decision["action"] == "block"
    assert decision.get("hard_block") is True
    assert decision["canary_enforced"] is True


def test_m4_policy_decisions_persist_in_task_queue(tmp_path: Path) -> None:
    queue = TaskQueue(db_path=tmp_path / "task_queue.db")

    queue.record_policy_decision(
        {
            "timestamp": "2026-02-25T23:20:00",
            "gate": "query",
            "source": "unit_test",
            "subject": "s1",
            "action": "allow",
            "blocked": False,
            "strict_mode": False,
            "violations": [],
            "payload": {"query": "ok"},
            "canary_percent": 0,
            "canary_enforced": True,
        }
    )
    queue.record_policy_decision(
        {
            "timestamp": "2026-02-25T23:21:00",
            "gate": "autonomous_task",
            "source": "unit_test",
            "subject": "s2",
            "action": "observe",
            "blocked": False,
            "strict_mode": True,
            "violations": ["canary_deferred"],
            "payload": {"task": "danger"},
            "canary_percent": 10,
            "canary_bucket": 88,
            "canary_enforced": False,
        }
    )

    metrics = queue.get_policy_decision_metrics(window_hours=99999)
    assert metrics["decisions_total"] >= 2
    assert metrics["strict_decisions"] >= 1
    assert metrics["canary_deferred_total"] >= 1
    assert metrics["by_gate"].get("query", 0) >= 1
    assert metrics["by_gate"].get("autonomous_task", 0) >= 1


def test_m4_list_policy_decisions_filters_by_gate_and_source(tmp_path: Path) -> None:
    queue = TaskQueue(db_path=tmp_path / "task_queue.db")

    queue.record_policy_decision(
        {
            "timestamp": "2026-02-25T23:20:00",
            "gate": "query",
            "source": "telegram",
            "subject": "s1",
            "action": "allow",
            "blocked": False,
            "strict_mode": False,
            "violations": [],
            "payload": {"query": "ok"},
            "canary_percent": 0,
            "canary_enforced": True,
        }
    )
    queue.record_policy_decision(
        {
            "timestamp": "2026-02-25T23:21:00",
            "gate": "autonomous_task",
            "source": "scheduler",
            "subject": "s2",
            "action": "observe",
            "blocked": False,
            "strict_mode": True,
            "violations": ["canary_deferred"],
            "payload": {"task": "danger"},
            "canary_percent": 10,
            "canary_bucket": 88,
            "canary_enforced": False,
        }
    )

    filtered = queue.list_policy_decisions(window_hours=99999, gate="query", source="telegram")

    assert len(filtered) == 1
    assert filtered[0]["gate"] == "query"
    assert filtered[0]["source"] == "telegram"


def test_m4_audit_policy_decision_writes_to_queue_store(monkeypatch, tmp_path: Path) -> None:
    import orchestration.task_queue as task_queue_module

    queue = TaskQueue(db_path=tmp_path / "task_queue.db")
    monkeypatch.setattr(task_queue_module, "get_queue", lambda: queue)
    monkeypatch.setenv("AUTONOMY_COMPAT_MODE", "false")
    monkeypatch.setenv("AUTONOMY_AUDIT_DECISIONS_ENABLED", "false")

    decision = policy_gate.evaluate_policy_gate(
        gate="query",
        subject="wie spät ist es?",
        payload={"query": "wie spät ist es?"},
        source="unit_test",
    )
    policy_gate.audit_policy_decision(decision)

    metrics = queue.get_policy_decision_metrics(window_hours=24)
    assert metrics["decisions_total"] >= 1


def test_m4_canary_and_persistence_hooks_present() -> None:
    policy_src = Path("utils/policy_gate.py").read_text(encoding="utf-8")
    queue_src = Path("orchestration/task_queue.py").read_text(encoding="utf-8")

    assert "_policy_canary_percent" in policy_src
    assert "_canary_bucket_for_key" in policy_src
    assert "record_policy_decision" in queue_src
    assert "get_policy_decision_metrics" in queue_src
