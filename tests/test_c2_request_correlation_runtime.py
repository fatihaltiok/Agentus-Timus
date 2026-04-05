from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from orchestration.request_correlation import (
    bind_request_correlation,
    get_current_request_correlation,
)
from orchestration.task_queue import TaskQueue


def _read_task_metadata(db_path: Path, task_id: str) -> str:
    with sqlite3.connect(db_path) as conn:
        row = conn.execute("SELECT metadata FROM tasks WHERE id=?", (task_id,)).fetchone()
    assert row is not None
    return str(row[0] or "")


def test_bind_request_correlation_resets_after_context():
    assert get_current_request_correlation()["request_id"] == ""
    with bind_request_correlation(request_id="req-c2", session_id="sess-c2"):
        current = get_current_request_correlation()
        assert current["request_id"] == "req-c2"
        assert current["session_id"] == "sess-c2"
    current = get_current_request_correlation()
    assert current["request_id"] == ""
    assert current["session_id"] == ""


def test_task_queue_injects_request_id_into_empty_metadata(tmp_path: Path):
    queue = TaskQueue(db_path=tmp_path / "task_queue.db")
    with bind_request_correlation(request_id="req-123"):
        task_id = queue.add(description="C2 metadata injection smoke test")
    payload = json.loads(_read_task_metadata(queue.db_path, task_id))
    assert payload["request_id"] == "req-123"


def test_task_queue_preserves_explicit_request_id(tmp_path: Path):
    queue = TaskQueue(db_path=tmp_path / "task_queue.db")
    explicit = json.dumps({"request_id": "req-explicit", "source": "manual"}, ensure_ascii=True)
    with bind_request_correlation(request_id="req-context"):
        task_id = queue.add(
            description="C2 explicit request id wins",
            metadata=explicit,
        )
    payload = json.loads(_read_task_metadata(queue.db_path, task_id))
    assert payload["request_id"] == "req-explicit"
    assert payload["source"] == "manual"


def test_task_queue_leaves_non_json_metadata_untouched(tmp_path: Path):
    queue = TaskQueue(db_path=tmp_path / "task_queue.db")
    with bind_request_correlation(request_id="req-context"):
        task_id = queue.add(
            description="C2 legacy metadata passthrough",
            metadata="legacy:opaque:payload",
        )
    assert _read_task_metadata(queue.db_path, task_id) == "legacy:opaque:payload"
