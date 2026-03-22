from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

from orchestration.task_queue import TaskQueue


def _age_task_started_at(db_path: Path, task_id: str, *, minutes_ago: int) -> None:
    started_at = (datetime.now() - timedelta(minutes=minutes_ago)).isoformat()
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "UPDATE tasks SET started_at=? WHERE id=?",
            (started_at, task_id),
        )
        conn.commit()


def test_task_queue_startup_recovers_stale_in_progress_task_to_pending(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("TASK_QUEUE_STALE_IN_PROGRESS_MINUTES", "60")
    db_path = tmp_path / "task_queue.db"

    queue = TaskQueue(db_path=db_path)
    task_id = queue.add(
        description="System-Alert: CPU=7% RAM=46% Disk=81%",
        task_type="ambient",
        target_agent="system",
        max_retries=3,
    )
    claimed = queue.claim_next()
    assert claimed is not None and claimed["id"] == task_id

    _age_task_started_at(db_path, task_id, minutes_ago=180)

    recovered_queue = TaskQueue(db_path=db_path)
    recovered = recovered_queue.get_by_id(task_id)

    assert recovered is not None
    assert recovered["status"] == "pending"
    assert recovered["retry_count"] == 1
    assert recovered["started_at"] is None
    assert "stale_in_progress_recovered_after_60m" in str(recovered["error"] or "")


def test_task_queue_startup_marks_stale_in_progress_task_failed_when_retries_exhausted(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("TASK_QUEUE_STALE_IN_PROGRESS_MINUTES", "60")
    db_path = tmp_path / "task_queue.db"

    queue = TaskQueue(db_path=db_path)
    task_id = queue.add(
        description="System-Alert: CPU=3% RAM=40% Disk=81%",
        task_type="ambient",
        target_agent="system",
        max_retries=1,
    )
    claimed = queue.claim_next()
    assert claimed is not None and claimed["id"] == task_id

    _age_task_started_at(db_path, task_id, minutes_ago=180)

    recovered_queue = TaskQueue(db_path=db_path)
    recovered = recovered_queue.get_by_id(task_id)

    assert recovered is not None
    assert recovered["status"] == "failed"
    assert recovered["retry_count"] == 1
    assert recovered["completed_at"] is not None
    assert "stale_in_progress_recovered_after_60m" in str(recovered["error"] or "")
