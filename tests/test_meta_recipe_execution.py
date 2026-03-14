import sys
from pathlib import Path

import pytest


project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))


def _build_meta_task(
    *,
    recipe_id: str,
    chain: str,
    stages: list[tuple[str, str, str, str, bool]],
    original_task: str,
    task_type: str = "youtube_content_extraction",
    site_kind: str = "youtube",
    recoveries: list[tuple[str, str, str, str, str, bool]] | None = None,
    alternative_recipes: list[dict] | None = None,
    meta_self_state: dict | None = None,
    selected_strategy: dict | None = None,
) -> str:
    import json

    lines = [
        "# META ORCHESTRATION HANDOFF",
        f"task_type: {task_type}",
        f"site_kind: {site_kind}",
        f"recommended_agent_chain: {chain}",
        f"recommended_recipe_id: {recipe_id}",
        "needs_structured_handoff: yes",
        "reason: test",
    ]
    if meta_self_state is not None:
        lines.append("meta_self_state_json: " + json.dumps(meta_self_state, ensure_ascii=False, sort_keys=True))
    if selected_strategy is not None:
        lines.append("selected_strategy_json: " + json.dumps(selected_strategy, ensure_ascii=False, sort_keys=True))
    if alternative_recipes is not None:
        lines.append("alternative_recipes_json: " + json.dumps(alternative_recipes, ensure_ascii=False, sort_keys=True))
    lines.append("recipe_stages:")
    for stage_id, agent, goal, expected_output, optional in stages:
        suffix = " (optional)" if optional else ""
        lines.append(f"- {stage_id}: {agent}{suffix}")
        lines.append(f"  goal: {goal}")
        lines.append(f"  expected_output: {expected_output}")
    if recoveries:
        lines.append("recipe_recoveries:")
        for failed_stage_id, recovery_stage_id, agent, goal, expected_output, terminal in recoveries:
            suffix = " [terminal]" if terminal else ""
            lines.append(f"- {failed_stage_id} => {recovery_stage_id}: {agent}{suffix}")
            lines.append(f"  goal: {goal}")
            lines.append(f"  expected_output: {expected_output}")
    lines.extend(["", "# ORIGINAL USER TASK", original_task])
    return "\n".join(lines)


@pytest.mark.asyncio
async def test_meta_recipe_execution_runs_stages_sequentially(monkeypatch):
    from agent.agents.meta import MetaAgent
    from agent.base_agent import BaseAgent

    calls = []

    async def _fake_call_tool(self, method: str, params: dict):
        assert method == "delegate_to_agent"
        calls.append(dict(params))
        if params["agent_type"] == "visual":
            return {
                "status": "success",
                "agent": "visual",
                "result": "YouTube-Seite erreicht",
                "blackboard_key": "delegation:visual:1",
                "metadata": {"page_state": "video_page"},
                "artifacts": [],
            }
        return {
            "status": "success",
            "agent": "research",
            "result": "Zusammenfassung erstellt",
            "blackboard_key": "delegation:research:2",
            "metadata": {"sources": ["https://youtube.com/watch?v=123"]},
            "artifacts": [],
        }

    monkeypatch.setattr(BaseAgent, "_call_tool", _fake_call_tool)

    agent = MetaAgent.__new__(MetaAgent)
    agent.conversation_session_id = "sess-meta-recipe"

    task = _build_meta_task(
        recipe_id="youtube_content_extraction",
        chain="meta -> visual -> research",
        stages=[
            ("visual_access", "visual", "Oeffne YouTube", "page_state", False),
            ("research_synthesis", "research", "Verdichte den Inhalt", "summary", False),
        ],
        original_task="Hole maximal viel Inhalt aus dem YouTube-Video.",
    )

    result = await MetaAgent.run(agent, task)

    assert len(calls) == 2
    assert calls[0]["agent_type"] == "visual"
    assert calls[1]["agent_type"] == "research"
    assert "previous_blackboard_key: delegation:visual:1" in calls[1]["task"]
    assert "previous_stage_result: YouTube-Seite erreicht" in calls[1]["task"]
    assert "Finales Ergebnis:" in result
    assert "Zusammenfassung erstellt" in result


@pytest.mark.asyncio
async def test_meta_recipe_execution_returns_direct_result_for_location_light_recipe(monkeypatch):
    from agent.agents.meta import MetaAgent
    from agent.base_agent import BaseAgent

    async def _fake_call_tool(self, method: str, params: dict):
        assert method == "delegate_to_agent"
        return {
            "status": "success",
            "agent": "executor",
            "result": "Du bist gerade in Offenbach am Main, Flutstraße 33. In der Nähe sind REWE und ROSSMANN offen.",
            "blackboard_key": "delegation:executor:1",
            "metadata": {},
            "artifacts": [],
        }

    monkeypatch.setattr(BaseAgent, "_call_tool", _fake_call_tool)

    agent = MetaAgent.__new__(MetaAgent)
    agent.conversation_session_id = "sess-meta-location-direct"

    task = _build_meta_task(
        recipe_id="location_local_search",
        chain="meta -> executor",
        stages=[
            ("location_context_scan", "executor", "Bestimme Standort und nearby Places", "location_summary", False),
        ],
        original_task="Wo bin ich gerade und was ist in meiner Nähe offen?",
        task_type="location_local_search",
        site_kind="maps",
    )

    result = await MetaAgent.run(agent, task)

    assert "Offenbach am Main" in result
    assert "Meta-Rezept 'location_local_search' ausgefuehrt." not in result


@pytest.mark.asyncio
async def test_meta_recipe_execution_inserts_strategy_lightweight_preflight(monkeypatch):
    from agent.agents.meta import MetaAgent
    from agent.base_agent import BaseAgent

    calls = []

    async def _fake_call_tool(self, method: str, params: dict):
        calls.append(dict(params))
        return {
            "status": "success",
            "agent": params["agent_type"],
            "result": f"{params['agent_type']} ok",
            "blackboard_key": f"delegation:{params['agent_type']}:1",
            "metadata": {},
            "artifacts": [],
        }

    monkeypatch.setattr(BaseAgent, "_call_tool", _fake_call_tool)

    agent = MetaAgent.__new__(MetaAgent)
    agent.conversation_session_id = "sess-meta-strategy-preflight"

    task = _build_meta_task(
        recipe_id="youtube_content_extraction",
        chain="meta -> visual -> research",
        stages=[
            ("visual_access", "visual", "Oeffne YouTube", "page_state", False),
            ("research_synthesis", "research", "Verdichte den Inhalt", "summary", False),
        ],
        original_task="Hole maximal viel Inhalt aus dem YouTube-Video.",
        selected_strategy={
            "strategy_id": "layered_youtube_extraction",
            "strategy_mode": "layered_extraction",
            "error_strategy": "recover_then_continue",
            "preferred_tools": ["search_youtube", "get_youtube_video_info", "get_youtube_subtitles"],
            "fallback_tools": ["search_web"],
            "avoid_tools": ["start_deep_research"],
        },
    )

    result = await MetaAgent.run(agent, task)

    assert [call["agent_type"] for call in calls] == ["research", "visual", "research"]
    assert "stage_id: research_context_seed" in calls[0]["task"]
    assert "preferred_tools: search_youtube, get_youtube_video_info, get_youtube_subtitles" in calls[0]["task"]
    assert "research_context_seed" in result


@pytest.mark.asyncio
async def test_meta_recipe_execution_skips_optional_stage_not_in_chain(monkeypatch):
    from agent.agents.meta import MetaAgent
    from agent.base_agent import BaseAgent

    calls = []

    async def _fake_call_tool(self, method: str, params: dict):
        calls.append(dict(params))
        return {
            "status": "success",
            "agent": params["agent_type"],
            "result": f"{params['agent_type']} ok",
            "blackboard_key": f"delegation:{params['agent_type']}:1",
            "metadata": {},
            "artifacts": [],
        }

    monkeypatch.setattr(BaseAgent, "_call_tool", _fake_call_tool)

    agent = MetaAgent.__new__(MetaAgent)
    agent.conversation_session_id = "sess-meta-optional"

    task = _build_meta_task(
        recipe_id="youtube_content_extraction",
        chain="meta -> visual -> research",
        stages=[
            ("visual_access", "visual", "Oeffne YouTube", "page_state", False),
            ("research_synthesis", "research", "Verdichte den Inhalt", "summary", False),
            ("document_output", "document", "Erzeuge Bericht", "pdf", True),
        ],
        original_task="Hole maximal viel Inhalt aus dem YouTube-Video.",
    )

    result = await MetaAgent.run(agent, task)

    assert [call["agent_type"] for call in calls] == ["visual", "research"]
    assert "[SKIPPED] document_output -> document" in result


@pytest.mark.asyncio
async def test_meta_recipe_execution_aborts_on_required_stage_error(monkeypatch):
    from agent.agents.meta import MetaAgent
    from agent.base_agent import BaseAgent

    calls = []

    async def _fake_call_tool(self, method: str, params: dict):
        calls.append(dict(params))
        if params["agent_type"] == "visual":
            return {
                "status": "error",
                "agent": "visual",
                "error": "Login-Maske konnte nicht verifiziert werden",
                "blackboard_key": "delegation:visual:error",
                "metadata": {},
                "artifacts": [],
            }
        raise AssertionError("Nach Fehler in Pflicht-Stage darf keine weitere Delegation passieren")

    monkeypatch.setattr(BaseAgent, "_call_tool", _fake_call_tool)

    agent = MetaAgent.__new__(MetaAgent)
    agent.conversation_session_id = "sess-meta-error"

    task = _build_meta_task(
        recipe_id="booking_search",
        chain="meta -> visual",
        stages=[
            ("visual_search_setup", "visual", "Oeffne Booking", "search_form_state", False),
            ("visual_results_capture", "visual", "Erreiche Ergebnisse", "results_url", False),
        ],
        original_task="Suche auf booking.com nach Hotels in Berlin.",
        task_type="multi_stage_web_task",
        site_kind="booking",
    )

    result = await MetaAgent.run(agent, task)

    assert len(calls) == 1
    assert "Abbruch bei Pflicht-Stage 'visual_search_setup'" in result
    assert "Login-Maske konnte nicht verifiziert werden" in result


@pytest.mark.asyncio
async def test_meta_recipe_execution_uses_recovery_stage_for_required_failure(monkeypatch):
    from agent.agents.meta import MetaAgent
    from agent.base_agent import BaseAgent

    calls = []

    async def _fake_call_tool(self, method: str, params: dict):
        calls.append(dict(params))
        if params["agent_type"] == "visual":
            return {
                "status": "error",
                "agent": "visual",
                "error": "Videoseite konnte nicht verifiziert werden",
                "blackboard_key": "delegation:visual:error",
                "metadata": {},
                "artifacts": [],
            }
        if params["agent_type"] == "research":
            return {
                "status": "success",
                "agent": "research",
                "result": "Konservative Recovery-Zusammenfassung",
                "blackboard_key": "delegation:research:recovery",
                "metadata": {"sources": ["https://youtube.com/watch?v=123"]},
                "artifacts": [],
            }
        raise AssertionError(f"Unerwarteter Agent: {params['agent_type']}")

    monkeypatch.setattr(BaseAgent, "_call_tool", _fake_call_tool)

    agent = MetaAgent.__new__(MetaAgent)
    agent.conversation_session_id = "sess-meta-recovery"

    task = _build_meta_task(
        recipe_id="youtube_content_extraction",
        chain="meta -> visual -> research",
        stages=[
            ("visual_access", "visual", "Oeffne YouTube", "page_state", False),
            ("research_synthesis", "research", "Verdichte den Inhalt", "summary", False),
        ],
        recoveries=[
            (
                "visual_access",
                "research_context_recovery",
                "research",
                "Erzeuge konservative Zusammenfassung ohne UI-Zugriff",
                "summary",
                True,
            )
        ],
        original_task="Hole maximal viel Inhalt aus dem YouTube-Video.",
    )

    result = await MetaAgent.run(agent, task)

    assert [call["agent_type"] for call in calls] == ["visual", "research"]
    assert "Recovery fuer: visual_access" in result
    assert "Konservative Recovery-Zusammenfassung" in result


@pytest.mark.asyncio
async def test_meta_recipe_execution_continues_after_nonterminal_recovery(monkeypatch):
    from agent.agents.meta import MetaAgent
    from agent.base_agent import BaseAgent

    calls = []

    async def _fake_call_tool(self, method: str, params: dict):
        calls.append(dict(params))
        if params["agent_type"] == "visual":
            return {
                "status": "error",
                "agent": "visual",
                "error": "Videoseite konnte nicht verifiziert werden",
                "blackboard_key": "delegation:visual:error",
                "metadata": {},
                "artifacts": [],
            }
        if params["agent_type"] == "research":
            return {
                "status": "success",
                "agent": "research",
                "result": "Konservative Recovery-Zusammenfassung",
                "blackboard_key": "delegation:research:recovery",
                "metadata": {"sources": ["https://youtube.com/watch?v=123"]},
                "artifacts": [],
            }
        if params["agent_type"] == "document":
            return {
                "status": "success",
                "agent": "document",
                "result": "PDF-Bericht erstellt",
                "blackboard_key": "delegation:document:1",
                "metadata": {"artifact": "report.pdf"},
                "artifacts": ["report.pdf"],
            }
        raise AssertionError(f"Unerwarteter Agent: {params['agent_type']}")

    monkeypatch.setattr(BaseAgent, "_call_tool", _fake_call_tool)

    agent = MetaAgent.__new__(MetaAgent)
    agent.conversation_session_id = "sess-meta-recovery-continue"

    task = _build_meta_task(
        recipe_id="youtube_content_extraction",
        chain="meta -> visual -> research -> document",
        stages=[
            ("visual_access", "visual", "Oeffne YouTube", "page_state", False),
            ("research_synthesis", "research", "Verdichte den Inhalt", "summary", False),
            ("document_output", "document", "Erzeuge Bericht", "pdf", True),
        ],
        recoveries=[
            (
                "visual_access",
                "research_context_recovery",
                "research",
                "Erzeuge konservative Zusammenfassung ohne UI-Zugriff",
                "summary",
                False,
            )
        ],
        original_task="Hole maximal viel Inhalt aus dem YouTube-Video und erstelle einen Bericht.",
    )

    result = await MetaAgent.run(agent, task)

    assert [call["agent_type"] for call in calls] == ["visual", "research", "research", "document"]
    assert "research_validation_gate" in result
    assert "Validiere die bisherige Quellenlage" in calls[2]["task"]
    assert "PDF-Bericht erstellt" in result
    assert "Recovery fuer: visual_access" in result


@pytest.mark.asyncio
async def test_meta_recipe_execution_inserts_learning_preflight(monkeypatch):
    from agent.agents.meta import MetaAgent
    from agent.base_agent import BaseAgent

    calls = []

    async def _fake_call_tool(self, method: str, params: dict):
        calls.append(dict(params))
        return {
            "status": "success",
            "agent": params["agent_type"],
            "result": f"{params['agent_type']} ok",
            "blackboard_key": f"delegation:{params['agent_type']}:1",
            "metadata": {},
            "artifacts": [],
        }

    monkeypatch.setattr(BaseAgent, "_call_tool", _fake_call_tool)

    agent = MetaAgent.__new__(MetaAgent)
    agent.conversation_session_id = "sess-meta-learning"

    task = (
        _build_meta_task(
            recipe_id="youtube_content_extraction",
            chain="meta -> visual -> research",
            stages=[
                ("visual_access", "visual", "Oeffne YouTube", "page_state", False),
                ("research_synthesis", "research", "Verdichte den Inhalt", "summary", False),
            ],
            original_task="Hole maximal viel Inhalt aus dem YouTube-Video.",
        )
        .replace("reason: test", "meta_learning_posture: conservative\nreason: test")
    )

    result = await MetaAgent.run(agent, task)

    assert [call["agent_type"] for call in calls] == ["research", "visual", "research"]
    assert "research_context_seed" in result


@pytest.mark.asyncio
async def test_meta_recipe_execution_inserts_validation_for_negative_learning_scores(monkeypatch):
    from agent.agents.meta import MetaAgent
    from agent.base_agent import BaseAgent

    calls = []

    async def _fake_call_tool(self, method: str, params: dict):
        calls.append(dict(params))
        return {
            "status": "success",
            "agent": params["agent_type"],
            "result": f"{params['agent_type']} ok",
            "blackboard_key": f"delegation:{params['agent_type']}:1",
            "metadata": {},
            "artifacts": [],
        }

    monkeypatch.setattr(BaseAgent, "_call_tool", _fake_call_tool)

    agent = MetaAgent.__new__(MetaAgent)
    agent.conversation_session_id = "sess-meta-negative-learning"

    task = (
        _build_meta_task(
            recipe_id="youtube_content_extraction",
            chain="meta -> visual -> research -> document",
            stages=[
                ("visual_access", "visual", "Oeffne YouTube", "page_state", False),
                ("research_synthesis", "research", "Verdichte den Inhalt", "summary", False),
                ("document_output", "document", "Erzeuge Bericht", "pdf", True),
            ],
            original_task="Hole maximal viel Inhalt aus dem YouTube-Video und erstelle einen Bericht.",
        )
        .replace(
            "reason: test",
            "recipe_feedback_score: -0.40\nchain_feedback_score: -0.30\ntask_type_feedback_score: -0.10\nreason: test",
        )
    )

    result = await MetaAgent.run(agent, task)

    assert [call["agent_type"] for call in calls] == ["visual", "research", "research", "document"]
    assert "research_validation_gate" in result
    assert "Validiere die bisherige Quellenlage" in calls[2]["task"]


@pytest.mark.asyncio
async def test_meta_recipe_execution_selects_initial_alternative_recipe_from_self_state(monkeypatch):
    from agent.agents.meta import MetaAgent
    from agent.base_agent import BaseAgent

    calls = []

    async def _fake_call_tool(self, method: str, params: dict):
        calls.append(dict(params))
        return {
            "status": "success",
            "agent": params["agent_type"],
            "result": f"{params['agent_type']} ok",
            "blackboard_key": f"delegation:{params['agent_type']}:1",
            "metadata": {},
            "artifacts": [],
        }

    monkeypatch.setattr(BaseAgent, "_call_tool", _fake_call_tool)

    agent = MetaAgent.__new__(MetaAgent)
    agent.conversation_session_id = "sess-meta-initial-alternative"

    task = _build_meta_task(
        recipe_id="youtube_content_extraction",
        chain="meta -> visual -> research -> document",
        stages=[
            ("visual_access", "visual", "Oeffne YouTube", "page_state", False),
            ("research_synthesis", "research", "Verdichte den Inhalt", "summary", False),
            ("document_output", "document", "Erzeuge Bericht", "pdf", True),
        ],
        alternative_recipes=[
            {
                "recipe_id": "youtube_research_only",
                "recipe_stages": [
                    {
                        "stage_id": "research_discovery",
                        "agent": "research",
                        "goal": "Recherchiere das Video ohne UI-Zugriff",
                        "expected_output": "summary",
                        "optional": False,
                    },
                    {
                        "stage_id": "document_output",
                        "agent": "document",
                        "goal": "Erzeuge Bericht",
                        "expected_output": "pdf",
                        "optional": True,
                    },
                ],
                "recipe_recoveries": [],
                "recommended_agent_chain": ["meta", "research", "document"],
            }
        ],
        meta_self_state={
            "runtime_constraints": {"stability_gate_state": "blocked"},
            "active_tools": [],
        },
        original_task="Hole maximal viel Inhalt aus dem YouTube-Video und erstelle einen Bericht.",
    )

    result = await MetaAgent.run(agent, task)

    assert [call["agent_type"] for call in calls] == ["research", "document"]
    assert "stage_id: research_discovery" in calls[0]["task"]
    assert "Meta-Rezept 'youtube_research_only' ausgefuehrt." in result
    assert "research_discovery" in result


@pytest.mark.asyncio
async def test_meta_recipe_execution_prefers_learned_alternative_recipe(monkeypatch):
    from agent.agents.meta import MetaAgent
    from agent.base_agent import BaseAgent

    calls = []

    async def _fake_call_tool(self, method: str, params: dict):
        calls.append(dict(params))
        return {
            "status": "success",
            "agent": params["agent_type"],
            "result": f"{params['agent_type']} ok",
            "blackboard_key": f"delegation:{params['agent_type']}:1",
            "metadata": {},
            "artifacts": [],
        }

    monkeypatch.setattr(BaseAgent, "_call_tool", _fake_call_tool)

    agent = MetaAgent.__new__(MetaAgent)
    agent.conversation_session_id = "sess-meta-learning-preference"

    task = (
        _build_meta_task(
            recipe_id="youtube_content_extraction",
            chain="meta -> visual -> research -> document",
            stages=[
                ("visual_access", "visual", "Oeffne YouTube", "page_state", False),
                ("research_synthesis", "research", "Verdichte den Inhalt", "summary", False),
                ("document_output", "document", "Erzeuge Bericht", "pdf", True),
            ],
            alternative_recipes=[
                {
                    "recipe_id": "youtube_research_only",
                    "recipe_stages": [
                        {
                            "stage_id": "research_discovery",
                            "agent": "research",
                            "goal": "Recherchiere das Video ohne UI-Zugriff",
                            "expected_output": "summary",
                            "optional": False,
                        },
                        {
                            "stage_id": "document_output",
                            "agent": "document",
                            "goal": "Erzeuge Bericht",
                            "expected_output": "pdf",
                            "optional": True,
                        },
                    ],
                    "recipe_recoveries": [],
                    "recommended_agent_chain": ["meta", "research", "document"],
                }
            ],
            original_task="Hole maximal viel Inhalt aus dem YouTube-Video und erstelle einen Bericht.",
        )
        .replace(
            "reason: test",
            (
                "meta_learning_posture: conservative\n"
                "site_recipe_feedback_score: 0.82 (evidence=5)\n"
                "recipe_feedback_score: 0.80 (evidence=6)\n"
                "alternative_recipe_scores_json: "
                '[{"recipe_evidence":4,"recipe_id":"youtube_research_only","recipe_score":1.21,'
                '"site_recipe_evidence":4,"site_recipe_key":"youtube::youtube_research_only",'
                '"site_recipe_score":1.11}]\n'
                "reason: test"
            ),
        )
    )

    result = await MetaAgent.run(agent, task)

    assert [call["agent_type"] for call in calls] == ["research", "research", "document"]
    assert "stage_id: research_context_seed" in calls[0]["task"]
    assert "stage_id: research_discovery" in calls[1]["task"]
    assert "Meta-Rezept 'youtube_research_only' ausgefuehrt." in result
    assert "research_discovery" in result


@pytest.mark.asyncio
async def test_meta_recipe_execution_switches_to_alternative_recipe_after_stage_failure(monkeypatch):
    from agent.agents.meta import MetaAgent
    from agent.base_agent import BaseAgent

    calls = []

    async def _fake_call_tool(self, method: str, params: dict):
        calls.append(dict(params))
        if params["agent_type"] == "visual":
            return {
                "status": "error",
                "agent": "visual",
                "error": "Video konnte nicht geladen werden",
                "blackboard_key": "delegation:visual:error",
                "metadata": {},
                "artifacts": [],
            }
        if params["agent_type"] == "research" and "recovery_stage_id: research_context_recovery" in params["task"]:
            return {
                "status": "error",
                "agent": "research",
                "error": "Recovery lieferte zu wenig belastbare Quellen",
                "blackboard_key": "delegation:research:error",
                "metadata": {},
                "artifacts": [],
            }
        return {
            "status": "success",
            "agent": params["agent_type"],
            "result": f"{params['agent_type']} ok",
            "blackboard_key": f"delegation:{params['agent_type']}:1",
            "metadata": {},
            "artifacts": [],
        }

    monkeypatch.setattr(BaseAgent, "_call_tool", _fake_call_tool)

    agent = MetaAgent.__new__(MetaAgent)
    agent.conversation_session_id = "sess-meta-switch-alternative"

    task = _build_meta_task(
        recipe_id="youtube_content_extraction",
        chain="meta -> visual -> research -> document",
        stages=[
            ("visual_access", "visual", "Oeffne YouTube", "page_state", False),
            ("research_synthesis", "research", "Verdichte den Inhalt", "summary", False),
            ("document_output", "document", "Erzeuge Bericht", "pdf", True),
        ],
        alternative_recipes=[
            {
                "recipe_id": "youtube_research_only",
                "recipe_stages": [
                    {
                        "stage_id": "research_discovery",
                        "agent": "research",
                        "goal": "Recherchiere das Video ohne UI-Zugriff",
                        "expected_output": "summary",
                        "optional": False,
                    },
                    {
                        "stage_id": "document_output",
                        "agent": "document",
                        "goal": "Erzeuge Bericht",
                        "expected_output": "pdf",
                        "optional": True,
                    },
                ],
                "recipe_recoveries": [],
                "recommended_agent_chain": ["meta", "research", "document"],
            }
        ],
        original_task="Hole maximal viel Inhalt aus dem YouTube-Video und erstelle einen Bericht.",
    )

    result = await MetaAgent.run(agent, task)

    assert [call["agent_type"] for call in calls] == ["visual", "research", "research", "document"]
    assert "recovery_stage_id: research_context_recovery" in calls[1]["task"]
    assert "stage_id: research_discovery" in calls[2]["task"]
    assert (
        "Meta-Rezept 'youtube_content_extraction' wurde nach Fehler in Stage "
        "'visual_access' auf 'youtube_research_only' umgestellt" in result
    )
    assert "Meta-Rezept 'youtube_research_only' ausgefuehrt." in result


@pytest.mark.asyncio
async def test_meta_recipe_execution_passes_error_classification_into_recovery(monkeypatch):
    from agent.agents.meta import MetaAgent
    from agent.base_agent import BaseAgent

    calls = []

    async def _fake_call_tool(self, method: str, params: dict):
        calls.append(dict(params))
        if params["agent_type"] == "visual":
            return {
                "status": "error",
                "agent": "visual",
                "error": "Videoseite konnte nicht verifiziert werden",
                "blackboard_key": "delegation:visual:error",
                "metadata": {},
                "artifacts": [],
            }
        return {
            "status": "success",
            "agent": "research",
            "result": "Konservative Recovery-Zusammenfassung",
            "blackboard_key": "delegation:research:recovery",
            "metadata": {},
            "artifacts": [],
        }

    monkeypatch.setattr(BaseAgent, "_call_tool", _fake_call_tool)

    agent = MetaAgent.__new__(MetaAgent)
    agent.conversation_session_id = "sess-meta-error-signal"

    task = _build_meta_task(
        recipe_id="youtube_content_extraction",
        chain="meta -> visual -> research",
        stages=[
            ("visual_access", "visual", "Oeffne YouTube", "page_state", False),
            ("research_synthesis", "research", "Verdichte den Inhalt", "summary", False),
        ],
        recoveries=[
            (
                "visual_access",
                "research_context_recovery",
                "research",
                "Erzeuge konservative Zusammenfassung ohne UI-Zugriff",
                "summary",
                True,
            )
        ],
        original_task="Hole maximal viel Inhalt aus dem YouTube-Video.",
        selected_strategy={
            "strategy_id": "layered_youtube_extraction",
            "strategy_mode": "layered_extraction",
            "fallback_recipe_id": "youtube_research_only",
            "error_strategy": "recover_then_continue",
        },
    )

    await MetaAgent.run(agent, task)

    assert [call["agent_type"] for call in calls] == ["research", "visual", "research"]
    assert "failed_error_class: browser_runtime_failure" in calls[2]["task"]
    assert "failed_error_reaction: switch_to_non_browser_fallback" in calls[2]["task"]


@pytest.mark.asyncio
async def test_meta_recipe_execution_records_actual_executed_recipe_outcomes(monkeypatch):
    from agent.agents.meta import MetaAgent
    from agent.base_agent import BaseAgent

    recorded = []

    class _FakeFeedbackEngine:
        def record_runtime_outcome(self, **kwargs):
            recorded.append(kwargs)

    calls = []

    async def _fake_call_tool(self, method: str, params: dict):
        calls.append(dict(params))
        if params["agent_type"] == "visual":
            return {
                "status": "error",
                "agent": "visual",
                "error": "Video konnte nicht geladen werden",
                "blackboard_key": "delegation:visual:error",
                "metadata": {},
                "artifacts": [],
            }
        if params["agent_type"] == "research" and "recovery_stage_id: research_context_recovery" in params["task"]:
            return {
                "status": "error",
                "agent": "research",
                "error": "Recovery lieferte zu wenig belastbare Quellen",
                "blackboard_key": "delegation:research:error",
                "metadata": {},
                "artifacts": [],
            }
        return {
            "status": "success",
            "agent": params["agent_type"],
            "result": f"{params['agent_type']} ok",
            "blackboard_key": f"delegation:{params['agent_type']}:1",
            "metadata": {},
            "artifacts": [],
        }

    monkeypatch.setattr("orchestration.feedback_engine.get_feedback_engine", lambda: _FakeFeedbackEngine())
    monkeypatch.setattr(BaseAgent, "_call_tool", _fake_call_tool)

    agent = MetaAgent.__new__(MetaAgent)
    agent.conversation_session_id = "sess-meta-record-outcomes"

    task = _build_meta_task(
        recipe_id="youtube_content_extraction",
        chain="meta -> visual -> research -> document",
        stages=[
            ("visual_access", "visual", "Oeffne YouTube", "page_state", False),
            ("research_synthesis", "research", "Verdichte den Inhalt", "summary", False),
            ("document_output", "document", "Erzeuge Bericht", "pdf", True),
        ],
        recoveries=[
            (
                "visual_access",
                "research_context_recovery",
                "research",
                "Erzeuge konservative Zusammenfassung ohne UI-Zugriff",
                "summary",
                False,
            )
        ],
        alternative_recipes=[
            {
                "recipe_id": "youtube_research_only",
                "recipe_stages": [
                    {
                        "stage_id": "research_discovery",
                        "agent": "research",
                        "goal": "Recherchiere das Video ohne UI-Zugriff",
                        "expected_output": "summary",
                        "optional": False,
                    },
                    {
                        "stage_id": "document_output",
                        "agent": "document",
                        "goal": "Erzeuge Bericht",
                        "expected_output": "pdf",
                        "optional": True,
                    },
                ],
                "recipe_recoveries": [],
                "recommended_agent_chain": ["meta", "research", "document"],
            }
        ],
        original_task="Hole maximal viel Inhalt aus dem YouTube-Video und erstelle einen Bericht.",
    )

    result = await MetaAgent.run(agent, task)

    assert "Meta-Rezept 'youtube_research_only' ausgefuehrt." in result
    assert [entry["success"] for entry in recorded] == [False, True]
    assert recorded[0]["context"]["meta_recipe_id"] == "youtube_content_extraction"
    assert recorded[0]["context"]["failed_stage_id"] == "visual_access"
    assert recorded[0]["context"]["switch_reason"].startswith("error_class:browser_runtime_failure")
    assert {
        "namespace": "meta_site_recipe",
        "key": "youtube::youtube_content_extraction",
    } in recorded[0]["feedback_targets"]
    assert recorded[1]["context"]["meta_recipe_id"] == "youtube_research_only"
    assert recorded[1]["context"]["meta_agent_chain"] == "meta -> research -> document"
    assert {
        "namespace": "meta_site_recipe",
        "key": "youtube::youtube_research_only",
    } in recorded[1]["feedback_targets"]
