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


class _CapturingMetaAgent:
    last_init_kwargs = None

    def __init__(self, tools_description_string: str, **kwargs):
        self.tools_description_string = tools_description_string
        type(self).last_init_kwargs = dict(kwargs)

    async def run(self, query: str):
        return f"captured:{query}"

    def get_runtime_telemetry(self):
        return {"agent_type": "meta_capture_test"}


def _stable_runtime_constraints():
    return {
        "budget_state": "soft_limit",
        "stability_gate_state": "warn",
        "degrade_mode": "degraded",
        "open_incidents": 2,
        "circuit_breakers_open": 1,
        "resource_guard_state": "active",
        "resource_guard_reason": "queue_backlog",
        "quarantined_incidents": 1,
        "cooldown_incidents": 1,
        "known_bad_patterns": 1,
        "release_blocked": False,
        "autonomy_hold": True,
    }


def _patch_dispatcher_dependencies(monkeypatch):
    monkeypatch.setattr("utils.audit_logger.AuditLogger", _DummyAuditLogger)
    monkeypatch.setattr("utils.policy_gate.audit_tool_call", lambda *_a, **_k: None)
    monkeypatch.setattr("utils.policy_gate.check_query_policy", lambda _q: (True, None))


@pytest.mark.asyncio
async def test_run_agent_injects_structured_meta_handoff(monkeypatch):
    import main_dispatcher
    from agent.agents.meta import MetaAgent
    from orchestration.meta_self_state import build_meta_self_state as _build_meta_self_state

    _patch_dispatcher_dependencies(monkeypatch)
    monkeypatch.setitem(main_dispatcher.AGENT_CLASS_MAP, "meta", _DummyMetaAgent)
    monkeypatch.setattr(
        main_dispatcher,
        "build_meta_self_state",
        lambda payload, learning: _build_meta_self_state(
            payload,
            learning,
            _stable_runtime_constraints(),
        ),
    )

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
    assert "goal_spec_json:" in result
    assert "capability_graph_json:" in result
    assert "adaptive_plan_json:" in result
    assert "planner_resolution_json:" in result
    assert "task_profile_json:" in result
    assert "selected_strategy_json:" in result
    assert "meta_self_state_json:" in result
    assert "meta_policy_decision_json:" in result
    assert "alternative_recipes_json:" in result
    assert "recipe_stages:" in result
    assert "- visual_access: visual" in result
    assert "- research_synthesis: research" in result
    assert "recipe_recoveries:" in result
    assert "- visual_access => research_context_recovery: research" in result
    assert "# ORIGINAL USER TASK" in result
    assert "Hole aus einem YouTube-Video maximal viel Inhalt raus" in result

    assert len(calls) == 1
    meta = calls[0]["metadata"]["meta_orchestration"]
    assert meta["task_type"] == "youtube_content_extraction"
    assert meta["recommended_agent_chain"] == ["meta", "visual", "research", "document"]
    assert meta["needs_structured_handoff"] is True
    assert meta["recommended_recipe_id"] == "youtube_content_extraction"
    assert meta["goal_spec"]["output_mode"] == "report"
    assert meta["adaptive_plan"]["planner_mode"] == "advisory"
    assert meta["planner_resolution"]["state"] in {"fallback_current", "rejected", "adopted"}
    assert meta["task_profile"]["intent"] == "content_extraction"
    assert meta["selected_strategy"]["strategy_id"] == "layered_youtube_extraction"
    assert [item["recipe_id"] for item in meta["alternative_recipes"]] == [
        "youtube_search_then_visual",
        "youtube_research_only",
    ]
    assert meta["meta_self_state"]["identity"] == "Timus"
    assert any(item["name"] == "get_youtube_subtitles" for item in meta["tool_affordances"])
    assert meta["meta_self_state"]["strategy_posture"] in {"neutral", "preferred", "conservative"}
    assert len(meta["recipe_stages"]) == 3
    assert len(meta["recipe_recoveries"]) == 1
    parsed = MetaAgent._parse_meta_orchestration_handoff(result)
    assert parsed is not None
    assert parsed["meta_self_state"]["identity"] == "Timus"
    assert parsed["goal_spec"]["output_mode"] == "report"
    assert parsed["adaptive_plan"]["recommended_chain"] == ["meta", "visual", "research", "document"]
    assert parsed["planner_resolution"]["state"] in {"fallback_current", "rejected", "adopted"}
    assert parsed["task_profile"]["intent"] == "content_extraction"
    assert parsed["selected_strategy"]["strategy_id"] == "layered_youtube_extraction"
    assert parsed["meta_self_state"]["runtime_constraints"]["budget_state"] == "soft_limit"


@pytest.mark.asyncio
async def test_run_agent_meta_handoff_strips_canvas_wrappers_from_original_user_task(monkeypatch):
    import main_dispatcher

    _patch_dispatcher_dependencies(monkeypatch)
    monkeypatch.setitem(main_dispatcher.AGENT_CLASS_MAP, "meta", _DummyMetaAgent)

    wrapped_query = (
        "Antworte ausschließlich auf Deutsch. "
        "Nutze nur dann englische Fachbegriffe, wenn sie technisch nötig sind.\n\n"
        "Nutzeranfrage:\n"
        "# LIVE LOCATION CONTEXT\n"
        "presence_status: recent\n"
        "usable_for_context: True\n"
        "display_name: Flutstraße 33, 63071 Offenbach am Main, Deutschland\n"
        "latitude: 50.100241\n"
        "longitude: 8.7787097\n"
        "Use this location only for nearby, routing, navigation, or explicit place-context tasks.\n\n"
        "zeig mir den weg nach münster mit dem auto"
    )

    result = await main_dispatcher.run_agent(
        agent_name="meta",
        query=wrapped_query,
        tools_description="tools",
        session_id="sess_meta_wrapped_route",
    )

    assert result.startswith("dummy:# META ORCHESTRATION HANDOFF")
    assert "task_type: location_route" in result
    assert "recommended_recipe_id: location_route" in result
    assert "# ORIGINAL USER TASK\nzeig mir den weg nach münster mit dem auto" in result
    assert "# LIVE LOCATION CONTEXT" not in result
    assert "Antworte ausschließlich auf Deutsch" not in result


@pytest.mark.asyncio
async def test_run_agent_meta_handoff_skips_model_validation_for_structured_recipe(monkeypatch):
    import main_dispatcher

    _patch_dispatcher_dependencies(monkeypatch)
    _CapturingMetaAgent.last_init_kwargs = None
    monkeypatch.setitem(main_dispatcher.AGENT_CLASS_MAP, "meta", _CapturingMetaAgent)

    result = await main_dispatcher.run_agent(
        agent_name="meta",
        query="zeig mir den weg nach münster mit dem auto",
        tools_description="tools",
        session_id="sess_meta_skip_validation",
    )

    assert result.startswith("captured:# META ORCHESTRATION HANDOFF")
    assert _CapturingMetaAgent.last_init_kwargs == {"skip_model_validation": True}


@pytest.mark.asyncio
async def test_real_meta_agent_can_execute_structured_route_recipe_without_llm_init(monkeypatch):
    import main_dispatcher
    from agent.agents.meta import MetaAgent
    from agent.base_agent import BaseAgent

    async def _fake_call_tool(self, method, params):
        assert method == "delegate_to_agent"
        assert params["agent_type"] == "executor"
        return {
            "status": "success",
            "result": "Aktive Route erfolgreich erstellt.",
            "blackboard_key": "delegation:executor:test",
            "metadata": {},
            "artifacts": [],
        }

    async def _empty_meta_context(self):
        return ""

    monkeypatch.setattr(BaseAgent, "_call_tool", _fake_call_tool)
    monkeypatch.setattr(MetaAgent, "_build_meta_context", _empty_meta_context)
    monkeypatch.setattr(MetaAgent, "_init_skill_system", lambda self: setattr(self, "skill_registry", None))

    payload = main_dispatcher._build_meta_handoff_payload("zeig mir den weg nach münster mit dem auto")
    handoff = (
        main_dispatcher._render_meta_handoff_block(payload)
        + "\n\n# ORIGINAL USER TASK\nzeig mir den weg nach münster mit dem auto"
    )

    agent = MetaAgent(tools_description_string="tools", skip_model_validation=True)
    agent.conversation_session_id = "sess_meta_real_recipe"
    result = await agent.run(handoff)

    assert "Meta-Rezept 'location_route'" in result
    assert "Aktive Route erfolgreich erstellt." in result


def test_build_meta_handoff_payload_exposes_learning_snapshot(monkeypatch):
    import main_dispatcher
    from orchestration.meta_self_state import build_meta_self_state as _build_meta_self_state

    class _FakeFeedbackEngine:
        def get_target_stats(self, namespace, target_key, default=1.0):
            mapping = {
                ("meta_recipe", "youtube_content_extraction"): {"evidence_count": 6},
                ("meta_site_recipe", "youtube::youtube_content_extraction"): {"evidence_count": 5},
                ("meta_recipe", "youtube_research_only"): {"evidence_count": 4},
                ("meta_site_recipe", "youtube::youtube_research_only"): {"evidence_count": 4},
                ("meta_agent_chain", "meta__visual__research__document"): {"evidence_count": 4},
                ("meta_task_type", "youtube_content_extraction"): {"evidence_count": 5},
            }
            return mapping.get((namespace, target_key), {"evidence_count": 0})

        def get_effective_target_score(self, namespace, target_key, default=1.0):
            mapping = {
                ("meta_recipe", "youtube_content_extraction"): 0.82,
                ("meta_site_recipe", "youtube::youtube_content_extraction"): 0.78,
                ("meta_recipe", "youtube_research_only"): 1.19,
                ("meta_site_recipe", "youtube::youtube_research_only"): 1.11,
                ("meta_agent_chain", "meta__visual__research__document"): 0.91,
                ("meta_task_type", "youtube_content_extraction"): 0.95,
            }
            return mapping.get((namespace, target_key), default)

    monkeypatch.setattr(
        "orchestration.feedback_engine.get_feedback_engine",
        lambda: _FakeFeedbackEngine(),
    )
    monkeypatch.setattr(
        main_dispatcher,
        "build_meta_self_state",
        lambda payload, learning: _build_meta_self_state(
            payload,
            learning,
            _stable_runtime_constraints(),
        ),
    )

    payload = main_dispatcher._build_meta_handoff_payload(
        "Hole aus einem YouTube-Video maximal viel Inhalt raus und schreibe einen Bericht dazu"
    )

    learning = payload["learning_snapshot"]
    self_state = payload["meta_self_state"]
    assert learning["posture"] == "conservative"
    assert learning["recipe_score"] == 0.82
    assert learning["recipe_evidence"] == 6
    assert learning["site_recipe_key"] == "youtube::youtube_content_extraction"
    assert learning["site_recipe_score"] == 0.78
    assert learning["site_recipe_evidence"] == 5
    assert learning["chain_key"] == "meta__visual__research__document"
    assert learning["alternative_recipe_scores"] == [
        {
            "recipe_id": "youtube_search_then_visual",
            "recipe_score": 1.0,
            "recipe_evidence": 0,
            "site_recipe_key": "youtube::youtube_search_then_visual",
            "site_recipe_score": 1.0,
            "site_recipe_evidence": 0,
        },
        {
            "recipe_id": "youtube_research_only",
            "recipe_score": 1.19,
            "recipe_evidence": 4,
            "site_recipe_key": "youtube::youtube_research_only",
            "site_recipe_score": 1.11,
            "site_recipe_evidence": 4,
        },
    ]
    assert self_state["identity"] == "Timus"
    assert self_state["strategy_posture"] == "conservative"
    assert self_state["preferred_entry_agent"] == "meta"
    assert "bounded_replanning_only" in self_state["known_limits"]
    assert self_state["runtime_constraints"]["stability_gate_state"] == "warn"
    assert any(risk["signal"] == "negative_outcome_history" for risk in self_state["active_risks"])
    rendered = main_dispatcher._render_meta_handoff_block(payload)
    assert payload["task_profile"]["intent"] == "content_extraction"
    assert payload["selected_strategy"]["strategy_id"] == "layered_youtube_extraction"
    assert payload["goal_spec"]["task_type"] == "youtube_content_extraction"
    assert payload["adaptive_plan"]["planner_mode"] == "advisory"
    assert payload["planner_resolution"]["state"] in {"fallback_current", "rejected", "adopted"}
    assert "meta_learning_posture: conservative" in rendered
    assert "task_profile_intent: content_extraction" in rendered
    assert "selected_strategy_id: layered_youtube_extraction" in rendered
    assert "recipe_feedback_score: 0.82 (evidence=6)" in rendered
    assert "site_recipe_key: youtube::youtube_content_extraction" in rendered
    assert "site_recipe_feedback_score: 0.78 (evidence=5)" in rendered
    assert "recommended_agent_chain_key: meta__visual__research__document" in rendered
    assert "meta_self_state_json:" in rendered
    assert "meta_policy_decision_json:" in rendered
    assert "goal_spec_json:" in rendered
    assert "capability_graph_json:" in rendered
    assert "adaptive_plan_json:" in rendered
    assert "planner_resolution_json:" in rendered
    assert "task_profile_json:" in rendered
    assert "selected_strategy_json:" in rendered
    assert "alternative_recipes_json:" in rendered
    assert "alternative_recipe_scores_json:" in rendered


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
                "site_kind": "youtube",
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
        "namespace": "meta_site_recipe",
        "key": "youtube::youtube_content_extraction",
    } in captured["feedback_targets"]
    assert {
        "namespace": "meta_agent_chain",
        "key": "meta__visual__research__document",
    } in captured["feedback_targets"]


def test_build_meta_handoff_payload_adopts_safe_adaptive_plan(monkeypatch):
    import main_dispatcher
    from orchestration.meta_orchestration import resolve_orchestration_recipe

    current = resolve_orchestration_recipe("simple_live_lookup")
    alternative = resolve_orchestration_recipe("simple_live_lookup_document")

    monkeypatch.setattr(
        main_dispatcher,
        "evaluate_query_orchestration",
        lambda _query: {
            "task_type": "simple_live_lookup",
            "site_kind": "web",
            "required_capabilities": ["live_lookup", "light_search"],
            "recommended_entry_agent": "meta",
            "recommended_agent_chain": ["meta", "executor"],
            "needs_structured_handoff": True,
            "meta_classification_reason": "simple_live_lookup",
            "recommended_recipe_id": current["recipe_id"],
            "recipe_stages": current["recipe_stages"],
            "recipe_recoveries": current["recipe_recoveries"],
            "alternative_recipes": [alternative],
            "goal_spec": {"goal_signature": "pricing|live|light|artifact|txt|loc=0|deliver=0"},
            "capability_graph": {"goal_gaps": ["artifact_output_stage_missing"]},
            "adaptive_plan": {
                "planner_mode": "advisory",
                "confidence": 0.91,
                "recommended_chain": ["meta", "executor", "document"],
                "recommended_recipe_hint": "simple_live_lookup_document",
            },
            "task_profile": {},
            "tool_affordances": [],
            "selected_strategy": {},
        },
    )

    payload = main_dispatcher._build_meta_handoff_payload("Speichere mir aktuelle LLM-Preise als txt Datei")

    assert payload["recommended_recipe_id"] == "simple_live_lookup_document"
    assert payload["recommended_agent_chain"] == ["meta", "executor", "document"]
    assert payload["planner_resolution"]["state"] == "adopted"
    assert payload["alternative_recipes"][0]["recipe_id"] == "simple_live_lookup"
