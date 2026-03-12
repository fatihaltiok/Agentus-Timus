import sys
from pathlib import Path

import pytest


project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))


class _DummyAuditLogger:
    def log_start(self, *_args, **_kwargs):
        return None

    def log_end(self, *_args, **_kwargs):
        return None


class _DummyMetaAgent:
    def __init__(self, tools_description_string: str, **_kwargs):
        self.tools_description_string = tools_description_string

    async def run(self, query: str):
        return f"dummy:{query}"

    def get_runtime_telemetry(self):
        return {"agent_type": "meta_test"}


def _patch_dispatcher_dependencies(monkeypatch):
    monkeypatch.setattr("utils.audit_logger.AuditLogger", _DummyAuditLogger)
    monkeypatch.setattr("utils.policy_gate.audit_tool_call", lambda *_a, **_k: None)
    monkeypatch.setattr("utils.policy_gate.check_query_policy", lambda _q: (True, None))


@pytest.mark.asyncio
async def test_run_agent_injects_structured_meta_handoff(monkeypatch):
    import main_dispatcher

    _patch_dispatcher_dependencies(monkeypatch)
    monkeypatch.setitem(main_dispatcher.AGENT_CLASS_MAP, "meta", _DummyMetaAgent)

    calls = []
    monkeypatch.setattr(
        main_dispatcher,
        "_log_interaction_deterministic",
        lambda **kwargs: calls.append(kwargs),
    )

    result = await main_dispatcher.run_agent(
        agent_name="meta",
        query="Hole aus einem YouTube-Video maximal viel Inhalt raus und schreibe einen Bericht dazu",
        tools_description="tools",
        session_id="sess_meta_handoff",
    )

    assert result.startswith("dummy:# META ORCHESTRATION HANDOFF")
    assert "task_type: youtube_content_extraction" in result
    assert "site_kind: youtube" in result
    assert "recommended_agent_chain: meta -> visual -> research -> document" in result
    assert "recommended_recipe_id: youtube_content_extraction" in result
    assert "recipe_stages:" in result
    assert "- visual_access: visual" in result
    assert "- research_synthesis: research" in result
    assert "# ORIGINAL USER TASK" in result
    assert "Hole aus einem YouTube-Video maximal viel Inhalt raus" in result

    assert len(calls) == 1
    meta = calls[0]["metadata"]["meta_orchestration"]
    assert meta["task_type"] == "youtube_content_extraction"
    assert meta["recommended_agent_chain"] == ["meta", "visual", "research", "document"]
    assert meta["needs_structured_handoff"] is True
    assert meta["recommended_recipe_id"] == "youtube_content_extraction"
    assert len(meta["recipe_stages"]) == 3


def test_build_meta_handoff_payload_exposes_learning_snapshot(monkeypatch):
    import main_dispatcher

    class _FakeFeedbackEngine:
        def get_target_stats(self, namespace, target_key, default=1.0):
            mapping = {
                ("meta_recipe", "youtube_content_extraction"): {"evidence_count": 6},
                ("meta_agent_chain", "meta__visual__research__document"): {"evidence_count": 4},
                ("meta_task_type", "youtube_content_extraction"): {"evidence_count": 5},
            }
            return mapping.get((namespace, target_key), {"evidence_count": 0})

        def get_effective_target_score(self, namespace, target_key, default=1.0):
            mapping = {
                ("meta_recipe", "youtube_content_extraction"): 0.82,
                ("meta_agent_chain", "meta__visual__research__document"): 0.91,
                ("meta_task_type", "youtube_content_extraction"): 0.95,
            }
            return mapping.get((namespace, target_key), default)

    monkeypatch.setattr(
        "orchestration.feedback_engine.get_feedback_engine",
        lambda: _FakeFeedbackEngine(),
    )

    payload = main_dispatcher._build_meta_handoff_payload(
        "Hole aus einem YouTube-Video maximal viel Inhalt raus und schreibe einen Bericht dazu"
    )

    learning = payload["learning_snapshot"]
    assert learning["posture"] == "conservative"
    assert learning["recipe_score"] == 0.82
    assert learning["recipe_evidence"] == 6
    assert learning["chain_key"] == "meta__visual__research__document"
    rendered = main_dispatcher._render_meta_handoff_block(payload)
    assert "meta_learning_posture: conservative" in rendered
    assert "recipe_feedback_score: 0.82 (evidence=6)" in rendered
    assert "recommended_agent_chain_key: meta__visual__research__document" in rendered


def test_record_runtime_feedback_adds_meta_recipe_targets(monkeypatch):
    import main_dispatcher

    captured = {}

    class _FakeFeedbackEngine:
        def record_runtime_outcome(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr(
        "orchestration.feedback_engine.get_feedback_engine",
        lambda: _FakeFeedbackEngine(),
    )

    main_dispatcher._record_runtime_feedback(
        session_id="sess_meta_outcome",
        agent_name="meta",
        query="Hole aus einem YouTube-Video maximal viel Inhalt raus",
        final_output="Erfolgreich abgeschlossen",
        runtime_metadata={
            "execution_path": "standard",
            "meta_orchestration": {
                "task_type": "youtube_content_extraction",
                "recommended_recipe_id": "youtube_content_extraction",
                "recommended_agent_chain": ["meta", "visual", "research", "document"],
            },
        },
    )

    assert captured["success"] is True
    assert captured["context"]["meta_task_type"] == "youtube_content_extraction"
    assert captured["context"]["meta_recipe_id"] == "youtube_content_extraction"
    assert captured["context"]["meta_agent_chain"] == "meta__visual__research__document"
    assert {"namespace": "dispatcher_agent", "key": "meta"} in captured["feedback_targets"]
    assert {"namespace": "meta_recipe", "key": "youtube_content_extraction"} in captured["feedback_targets"]
    assert {
        "namespace": "meta_agent_chain",
        "key": "meta__visual__research__document",
    } in captured["feedback_targets"]
