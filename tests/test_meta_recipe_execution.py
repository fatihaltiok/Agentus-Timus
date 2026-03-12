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
) -> str:
    lines = [
        "# META ORCHESTRATION HANDOFF",
        f"task_type: {task_type}",
        f"site_kind: {site_kind}",
        f"recommended_agent_chain: {chain}",
        f"recommended_recipe_id: {recipe_id}",
        "needs_structured_handoff: yes",
        "reason: test",
        "recipe_stages:",
    ]
    for stage_id, agent, goal, expected_output, optional in stages:
        suffix = " (optional)" if optional else ""
        lines.append(f"- {stage_id}: {agent}{suffix}")
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
