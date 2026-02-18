from pathlib import Path
import inspect
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from orchestration.canvas_store import CanvasStore
from server.mcp_server import get_canvas, get_canvas_by_session
from server.canvas_ui import build_canvas_ui_html


def _store(tmp_path: Path) -> CanvasStore:
    return CanvasStore(tmp_path / "canvas_store_filters.json")


def test_canvas_store_filters_session_agent_and_errors(tmp_path):
    store = _store(tmp_path)
    canvas = store.create_canvas("Filters")
    cid = canvas["id"]
    store.attach_session(canvas_id=cid, session_id="s1")
    store.attach_session(canvas_id=cid, session_id="s2")

    store.upsert_node(
        canvas_id=cid,
        node_id="agent:executor",
        node_type="agent",
        title="executor",
        status="completed",
        metadata={"last_session_id": "s1"},
    )
    store.upsert_node(
        canvas_id=cid,
        node_id="agent:research",
        node_type="agent",
        title="research",
        status="error",
        metadata={"last_session_id": "s2"},
    )
    store.add_edge(
        canvas_id=cid,
        source_node_id="agent:executor",
        target_node_id="agent:research",
        label="delegate_to_agent",
        kind="delegation",
        metadata={"session_id": "s1"},
    )

    store.add_event(
        canvas_id=cid,
        event_type="agent_run",
        status="completed",
        agent="executor",
        node_id="agent:executor",
        session_id="s1",
        message="ok",
    )
    store.add_event(
        canvas_id=cid,
        event_type="delegation",
        status="error",
        agent="research",
        node_id="agent:research",
        session_id="s1",
        message="error on source",
    )
    store.add_event(
        canvas_id=cid,
        event_type="agent_run",
        status="error",
        agent="executor",
        node_id="agent:executor",
        session_id="s2",
        message="error on target",
    )

    by_session = store.get_canvas_view(cid, session_id="s1")
    assert by_session is not None
    assert all(ev.get("session_id") == "s1" for ev in by_session["events"])
    assert by_session["session_ids"] == ["s1"]

    by_agent = store.get_canvas_view(cid, agent="research")
    assert by_agent is not None
    assert all("research" in (ev.get("agent") or "") for ev in by_agent["events"])
    assert set(by_agent["nodes"].keys()) == {"agent:research"}

    only_errors = store.get_canvas_view(cid, only_errors=True)
    assert only_errors is not None
    assert len(only_errors["events"]) == 2
    assert all("error" in (ev.get("status") or "").lower() for ev in only_errors["events"])

    status_completed = store.get_canvas_view(cid, status="completed")
    assert status_completed is not None
    assert len(status_completed["events"]) == 1
    assert status_completed["events"][0]["status"] == "completed"


def test_canvas_by_session_view_filters(tmp_path):
    store = _store(tmp_path)
    canvas = store.create_canvas("Session View")
    cid = canvas["id"]
    store.attach_session(canvas_id=cid, session_id="sx")
    store.add_event(
        canvas_id=cid,
        event_type="delegation",
        status="error",
        agent="research",
        node_id="agent:research",
        session_id="sx",
        message="bad",
    )
    view = store.get_canvas_by_session_view("sx", agent="research", only_errors=True)
    assert view is not None
    assert view["view_filters"]["session_id"] == "sx"
    assert view["view_filters"]["agent"] == "research"
    assert view["view_filters"]["only_errors"] is True


def test_api_filter_params_and_ui_controls_exist():
    get_canvas_params = inspect.signature(get_canvas).parameters
    assert "session_id" in get_canvas_params
    assert "agent" in get_canvas_params
    assert "status" in get_canvas_params
    assert "only_errors" in get_canvas_params
    assert "event_limit" in get_canvas_params

    get_canvas_by_session_params = inspect.signature(get_canvas_by_session).parameters
    assert "agent" in get_canvas_by_session_params
    assert "status" in get_canvas_by_session_params
    assert "only_errors" in get_canvas_by_session_params
    assert "event_limit" in get_canvas_by_session_params

    html = build_canvas_ui_html(1234)
    assert "filterSession" in html
    assert "filterAgent" in html
    assert "filterOnlyErrors" in html
    assert "applyFilterBtn" in html
