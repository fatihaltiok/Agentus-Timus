from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from orchestration.canvas_store import CanvasStore


def _store(tmp_path: Path) -> CanvasStore:
    return CanvasStore(tmp_path / "canvas_store_test.json")


def test_canvas_create_attach_and_get_by_session(tmp_path):
    store = _store(tmp_path)
    canvas = store.create_canvas("Session Flow", description="MVP Canvas")

    mapping = store.attach_session(canvas_id=canvas["id"], session_id="sess_123")
    assert mapping["canvas_id"] == canvas["id"]
    assert mapping["session_id"] == "sess_123"

    by_session = store.get_canvas_by_session("sess_123")
    assert by_session is not None
    assert by_session["id"] == canvas["id"]
    assert "sess_123" in by_session["session_ids"]


def test_node_upsert_and_edge_dedup(tmp_path):
    store = _store(tmp_path)
    canvas = store.create_canvas("Agent Graph")
    cid = canvas["id"]

    node = store.upsert_node(
        canvas_id=cid,
        node_id="agent:executor",
        node_type="agent",
        title="executor",
        status="running",
    )
    assert node["status"] == "running"

    node2 = store.upsert_node(
        canvas_id=cid,
        node_id="agent:executor",
        node_type="agent",
        title="executor",
        status="completed",
    )
    assert node2["id"] == node["id"]
    assert node2["status"] == "completed"

    edge1 = store.add_edge(
        canvas_id=cid,
        source_node_id="agent:executor",
        target_node_id="agent:research",
        kind="delegation",
        label="delegate_to_agent",
    )
    edge2 = store.add_edge(
        canvas_id=cid,
        source_node_id="agent:executor",
        target_node_id="agent:research",
        kind="delegation",
        label="delegate_to_agent",
    )
    assert edge1["id"] == edge2["id"]


def test_record_agent_event_only_with_attached_session(tmp_path):
    store = _store(tmp_path)
    assert store.record_agent_event("sess_unknown", "executor", "running") is None

    canvas = store.create_canvas("Runs")
    store.attach_session(canvas_id=canvas["id"], session_id="sess_777")
    result = store.record_agent_event(
        session_id="sess_777",
        agent_name="executor",
        status="completed",
        message="done",
        payload={"foo": "bar"},
    )
    assert result is not None
    loaded = store.get_canvas(canvas["id"])
    assert loaded is not None
    assert any(e.get("status") == "completed" for e in loaded["events"])
