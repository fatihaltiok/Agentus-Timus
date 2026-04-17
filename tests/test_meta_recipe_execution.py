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
    adaptive_plan: dict | None = None,
    planner_resolution: dict | None = None,
    goal_spec: dict | None = None,
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
    if adaptive_plan is not None:
        lines.append("adaptive_plan_json: " + json.dumps(adaptive_plan, ensure_ascii=False, sort_keys=True))
    if planner_resolution is not None:
        lines.append("planner_resolution_json: " + json.dumps(planner_resolution, ensure_ascii=False, sort_keys=True))
    if goal_spec is not None:
        lines.append("goal_spec_json: " + json.dumps(goal_spec, ensure_ascii=False, sort_keys=True))
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
    assert "task_packet_json:" in calls[0]["task"]
    assert "request_preflight_json:" in calls[0]["task"]
    assert "task_packet_json:" in calls[1]["task"]
    assert "request_preflight_json:" in calls[1]["task"]
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
async def test_meta_recipe_execution_returns_direct_result_for_simple_live_lookup(monkeypatch):
    from agent.agents.meta import MetaAgent
    from agent.base_agent import BaseAgent

    async def _fake_call_tool(self, method: str, params: dict):
        assert method == "delegate_to_agent"
        assert params["agent_type"] == "executor"
        assert "task_type: simple_live_lookup" in params["task"]
        assert "task_packet_json:" in params["task"]
        assert "request_preflight_json:" in params["task"]
        return {
            "status": "success",
            "agent": "executor",
            "result": "Aus der Wissenschaft fallen gerade drei aktuelle Meldungen auf.",
            "blackboard_key": "delegation:executor:2",
            "metadata": {},
            "artifacts": [],
        }

    monkeypatch.setattr(BaseAgent, "_call_tool", _fake_call_tool)

    agent = MetaAgent.__new__(MetaAgent)
    agent.conversation_session_id = "sess-meta-live-lookup-direct"

    task = _build_meta_task(
        recipe_id="simple_live_lookup",
        chain="meta -> executor",
        stages=[
            ("live_lookup_scan", "executor", "Fuehre die Live-Recherche kompakt aus", "quick_summary", False),
        ],
        original_task="Was gibt es Neues aus der Wissenschaft?",
        task_type="simple_live_lookup",
        site_kind="web",
    )

    result = await MetaAgent.run(agent, task)

    assert "Wissenschaft" in result
    assert "Meta-Rezept 'simple_live_lookup' ausgefuehrt." not in result


@pytest.mark.asyncio
async def test_meta_recipe_execution_returns_direct_result_for_lookup_document_recipe(monkeypatch):
    from agent.agents.meta import MetaAgent
    from agent.base_agent import BaseAgent

    calls = []

    async def _fake_call_tool(self, method: str, params: dict):
        assert method == "delegate_to_agent"
        calls.append(dict(params))
        if params["agent_type"] == "executor":
            assert "task_packet_json:" in params["task"]
            assert "request_preflight_json:" in params["task"]
            return {
                "status": "success",
                "agent": "executor",
                "result": (
                    "Ich habe aus der zuletzt geprueften Quelle diese Preis-Tabelle herausgezogen:\n\n"
                    "| Anbieter | Modell | Input | Output | Cached |\n"
                    "| --- | --- | --- | --- | --- |\n"
                    "| OpenAI | GPT-5.4 mini | $0.75 / 1M | $4.50 / 1M | $0.075 / 1M |\n"
                    "| DeepSeek | DeepSeek V3 | $0.27 / 1M | $1.10 / 1M | $0.07 / 1M |"
                ),
                "blackboard_key": "delegation:executor:pricing",
                "metadata": {},
                "artifacts": [],
            }
        assert "output_format: XLSX" in params["task"]
        assert "artifact_name: LLM_Preise_Vergleich" in params["task"]
        assert "source_material:" in params["task"]
        assert "task_packet_json:" in params["task"]
        assert "request_preflight_json:" in params["task"]
        return {
            "status": "success",
            "agent": "document",
            "result": "**Dokument erstellt:** `results/LLM_Preise_Vergleich.xlsx`\n**Format:** XLSX",
            "blackboard_key": "delegation:document:pricing",
            "metadata": {"artifact": "results/LLM_Preise_Vergleich.xlsx"},
            "artifacts": ["results/LLM_Preise_Vergleich.xlsx"],
        }

    monkeypatch.setattr(BaseAgent, "_call_tool", _fake_call_tool)

    agent = MetaAgent.__new__(MetaAgent)
    agent.conversation_session_id = "sess-meta-lookup-document"

    task = _build_meta_task(
        recipe_id="simple_live_lookup_document",
        chain="meta -> executor -> document",
        stages=[
            ("live_lookup_scan", "executor", "Fuehre die Live-Recherche kompakt aus", "structured_lookup_result", False),
            ("document_output", "document", "Erzeuge Tabelle oder Datei", "xlsx artifact", False),
        ],
        original_task="Erstelle mir eine Liste mit den aktuellen Preisen der besten LLMs und zeige mir dann die Tabelle",
        task_type="simple_live_lookup_document",
        site_kind="web",
    )

    result = await MetaAgent.run(agent, task)

    assert [call["agent_type"] for call in calls] == ["executor", "document"]
    assert result.startswith("**Dokument erstellt:**")
    assert "Meta-Rezept 'simple_live_lookup_document' ausgefuehrt." not in result


@pytest.mark.asyncio
async def test_meta_recipe_execution_prefers_adaptive_plan_before_recipe_fallbacks(monkeypatch):
    from agent.agents.meta import MetaAgent
    from agent.base_agent import BaseAgent
    from orchestration.meta_orchestration import resolve_orchestration_recipe

    calls = []

    async def _fake_call_tool(self, method: str, params: dict):
        assert method == "delegate_to_agent"
        calls.append(dict(params))
        if params["agent_type"] == "executor":
            return {
                "status": "success",
                "agent": "executor",
                "result": "Preiszeilen extrahiert",
                "blackboard_key": "delegation:executor:pricing",
                "metadata": {},
                "artifacts": [],
            }
        return {
            "status": "success",
            "agent": "document",
            "result": "**Dokument erstellt:** `results/LLM_Preise_Vergleich.txt`\n**Format:** TXT",
            "blackboard_key": "delegation:document:pricing",
            "metadata": {"artifact": "results/LLM_Preise_Vergleich.txt"},
            "artifacts": ["results/LLM_Preise_Vergleich.txt"],
        }

    monkeypatch.setattr(BaseAgent, "_call_tool", _fake_call_tool)

    agent = MetaAgent.__new__(MetaAgent)
    agent.conversation_session_id = "sess-meta-adaptive-planner"

    document_recipe = resolve_orchestration_recipe("simple_live_lookup_document")
    task = _build_meta_task(
        recipe_id="simple_live_lookup",
        chain="meta -> executor",
        stages=[
            ("live_lookup_scan", "executor", "Fuehre die Live-Recherche kompakt aus", "quick_summary", False),
        ],
        original_task="Speichere mir aktuelle LLM-Preise als txt Datei",
        task_type="simple_live_lookup",
        site_kind="web",
        alternative_recipes=[document_recipe],
        adaptive_plan={
            "planner_mode": "advisory",
            "confidence": 0.91,
            "recommended_chain": ["meta", "executor", "document"],
            "recommended_recipe_hint": "simple_live_lookup_document",
        },
    )

    result = await MetaAgent.run(agent, task)

    assert [call["agent_type"] for call in calls] == ["executor", "document"]
    assert result.startswith("**Dokument erstellt:**")


@pytest.mark.asyncio
async def test_meta_recipe_execution_runtime_replan_inserts_document_stage_after_success(monkeypatch):
    from agent.agents.meta import MetaAgent
    from agent.base_agent import BaseAgent

    calls = []

    async def _fake_call_tool(self, method: str, params: dict):
        assert method == "delegate_to_agent"
        calls.append(dict(params))
        if params["agent_type"] == "research":
            return {
                "status": "success",
                "agent": "research",
                "result": "Belastbare Modellpreise extrahiert und strukturiert zusammengestellt.",
                "blackboard_key": "delegation:research:prices",
                "metadata": {"sources": ["https://example.com/pricing"]},
                "artifacts": [],
            }
        assert params["agent_type"] == "document"
        assert "source_material:" in params["task"]
        assert "output_format: TXT" in params["task"]
        return {
            "status": "success",
            "agent": "document",
            "result": "**Dokument erstellt:** `results/Preisvergleich.txt`\n**Format:** TXT",
            "blackboard_key": "delegation:document:prices",
            "metadata": {"artifact": "results/Preisvergleich.txt"},
            "artifacts": ["results/Preisvergleich.txt"],
        }

    monkeypatch.setattr(BaseAgent, "_call_tool", _fake_call_tool)

    agent = MetaAgent.__new__(MetaAgent)
    agent.conversation_session_id = "sess-meta-runtime-gap"

    task = _build_meta_task(
        recipe_id="knowledge_research",
        chain="meta -> research",
        stages=[
            ("research_discovery", "research", "Recherchiere aktuelle Modellpreise", "summary", False),
        ],
        original_task="Recherchiere aktuelle LLM-Preise und speichere sie als txt Datei",
        task_type="knowledge_research",
        site_kind="web",
        goal_spec={
            "goal_signature": "pricing|recent|verified|artifact|txt|loc=0|deliver=0",
            "task_type": "knowledge_research",
            "domain": "pricing",
            "freshness": "recent",
            "evidence_level": "verified",
            "output_mode": "artifact",
            "artifact_format": "txt",
            "uses_location": False,
            "delivery_required": False,
            "advisory_only": True,
        },
    )

    result = await MetaAgent.run(agent, task)

    assert [call["agent_type"] for call in calls] == ["research", "document"]
    assert result.startswith("**Dokument erstellt:**")


@pytest.mark.asyncio
async def test_meta_recipe_execution_runtime_replan_inserts_verification_stage_after_executor_success(monkeypatch):
    from agent.agents.meta import MetaAgent
    from agent.base_agent import BaseAgent

    calls = []

    async def _fake_call_tool(self, method: str, params: dict):
        assert method == "delegate_to_agent"
        calls.append(dict(params))
        if params["agent_type"] == "executor":
            return {
                "status": "success",
                "agent": "executor",
                "result": "Top-Quellen zu aktuellen Modellpreisen gesammelt.",
                "blackboard_key": "delegation:executor:prices",
                "metadata": {"source_urls": ["https://example.com/pricing"]},
                "artifacts": [],
            }
        assert params["agent_type"] == "research"
        assert "previous_stage_result:" in params["task"]
        return {
            "status": "success",
            "agent": "research",
            "result": "Verifizierte Preisübersicht mit belastbaren Quellen erstellt.",
            "blackboard_key": "delegation:research:verify",
            "metadata": {"sources": ["https://example.com/pricing"]},
            "artifacts": [],
        }

    monkeypatch.setattr(BaseAgent, "_call_tool", _fake_call_tool)

    agent = MetaAgent.__new__(MetaAgent)
    agent.conversation_session_id = "sess-meta-runtime-gap-verification"

    task = _build_meta_task(
        recipe_id="simple_live_lookup",
        chain="meta -> executor",
        stages=[
            ("live_lookup_scan", "executor", "Suche aktuelle Modellpreise", "quick_summary", False),
        ],
        original_task="Suche aktuelle LLM-Preise mit Quellen und verifiziere sie",
        task_type="simple_live_lookup",
        site_kind="web",
        goal_spec={
            "goal_signature": "pricing|live|verified|answer|none|loc=0|deliver=0",
            "task_type": "simple_live_lookup",
            "domain": "pricing",
            "freshness": "live",
            "evidence_level": "verified",
            "output_mode": "answer",
            "artifact_format": None,
            "uses_location": False,
            "delivery_required": False,
            "advisory_only": True,
        },
    )

    result = await MetaAgent.run(agent, task)

    assert [call["agent_type"] for call in calls] == ["executor", "research"]
    assert result == "Verifizierte Preisübersicht mit belastbaren Quellen erstellt."


@pytest.mark.asyncio
async def test_meta_recipe_execution_runtime_replan_inserts_delivery_stage_after_document_success(monkeypatch):
    from agent.agents.meta import MetaAgent
    from agent.base_agent import BaseAgent

    calls = []

    async def _fake_call_tool(self, method: str, params: dict):
        assert method == "delegate_to_agent"
        calls.append(dict(params))
        if params["agent_type"] == "executor":
            return {
                "status": "success",
                "agent": "executor",
                "result": "Aktuelle Modellpreise strukturiert gesammelt.",
                "blackboard_key": "delegation:executor:pricing",
                "metadata": {"rows": 8},
                "artifacts": [],
            }
        if params["agent_type"] == "document":
            return {
                "status": "success",
                "agent": "document",
                "result": "**Dokument erstellt:** `results/Preisvergleich.txt`\n**Format:** TXT",
                "blackboard_key": "delegation:document:pricing",
                "metadata": {"artifact": "results/Preisvergleich.txt"},
                "artifacts": ["results/Preisvergleich.txt"],
            }
        assert params["agent_type"] == "communication"
        assert "attachment_path: results/Preisvergleich.txt" in params["task"]
        assert "source_material:" in params["task"]
        return {
            "status": "success",
            "agent": "communication",
            "result": "**Nachricht erstellt:** Versand mit Artefakt vorbereitet.",
            "blackboard_key": "delegation:communication:pricing",
            "metadata": {"channel": "direct_message"},
            "artifacts": [],
        }

    monkeypatch.setattr(BaseAgent, "_call_tool", _fake_call_tool)

    agent = MetaAgent.__new__(MetaAgent)
    agent.conversation_session_id = "sess-meta-runtime-gap-delivery"

    task = _build_meta_task(
        recipe_id="simple_live_lookup_document",
        chain="meta -> executor -> document",
        stages=[
            ("live_lookup_scan", "executor", "Suche aktuelle Modellpreise", "structured_lookup_result", False),
            ("document_output", "document", "Erzeuge txt Export", "txt artifact", False),
        ],
        original_task="Suche aktuelle LLM-Preise und schicke mir danach die txt Datei",
        task_type="simple_live_lookup_document",
        site_kind="web",
        goal_spec={
            "goal_signature": "pricing|live|light|artifact|txt|loc=0|deliver=1",
            "task_type": "simple_live_lookup_document",
            "domain": "pricing",
            "freshness": "live",
            "evidence_level": "light",
            "output_mode": "artifact",
            "artifact_format": "txt",
            "uses_location": False,
            "delivery_required": True,
            "advisory_only": True,
        },
    )

    result = await MetaAgent.run(agent, task)

    assert [call["agent_type"] for call in calls] == ["executor", "document", "communication"]
    assert result == "**Nachricht erstellt:** Versand mit Artefakt vorbereitet."


@pytest.mark.asyncio
async def test_meta_recipe_execution_records_learned_chain_outcome_after_runtime_gap(monkeypatch):
    from agent.agents.meta import MetaAgent
    from agent.base_agent import BaseAgent

    recorded = []
    observed = []

    class _FakeAdaptivePlanMemory:
        def record_outcome(self, **kwargs):
            recorded.append(kwargs)

    class _FakeFeedbackEngine:
        def record_runtime_outcome(self, **kwargs):
            return kwargs

    async def _fake_call_tool(self, method: str, params: dict):
        assert method == "delegate_to_agent"
        if params["agent_type"] == "research":
            return {
                "status": "success",
                "agent": "research",
                "result": "Belastbare Modellpreise extrahiert und strukturiert zusammengestellt.",
                "blackboard_key": "delegation:research:prices",
                "metadata": {"sources": ["https://example.com/pricing"]},
                "artifacts": [],
            }
        assert params["agent_type"] == "document"
        return {
            "status": "success",
            "agent": "document",
            "result": "**Dokument erstellt:** `results/Preisvergleich.txt`\n**Format:** TXT",
            "blackboard_key": "delegation:document:prices",
            "metadata": {"artifact": "results/Preisvergleich.txt"},
            "artifacts": ["results/Preisvergleich.txt"],
        }

    monkeypatch.setattr(BaseAgent, "_call_tool", _fake_call_tool)
    monkeypatch.setattr("orchestration.feedback_engine.get_feedback_engine", lambda: _FakeFeedbackEngine())
    monkeypatch.setattr("agent.agents.meta.get_adaptive_plan_memory", lambda: _FakeAdaptivePlanMemory())
    monkeypatch.setattr(
        "agent.agents.meta.record_autonomy_observation",
        lambda event_type, payload, observed_at="": observed.append(
            {"event_type": event_type, "payload": dict(payload), "observed_at": observed_at}
        )
        or True,
    )

    agent = MetaAgent.__new__(MetaAgent)
    agent.conversation_session_id = "sess-meta-runtime-gap-learning"

    task = _build_meta_task(
        recipe_id="knowledge_research",
        chain="meta -> research",
        stages=[
            ("research_discovery", "research", "Recherchiere aktuelle Modellpreise", "summary", False),
        ],
        original_task="Recherchiere aktuelle LLM-Preise und speichere sie als txt Datei",
        task_type="knowledge_research",
        site_kind="web",
        goal_spec={
            "goal_signature": "pricing|recent|verified|artifact|txt|loc=0|deliver=0",
            "task_type": "knowledge_research",
            "domain": "pricing",
            "freshness": "recent",
            "evidence_level": "verified",
            "output_mode": "artifact",
            "artifact_format": "txt",
            "uses_location": False,
            "delivery_required": False,
            "advisory_only": True,
        },
        adaptive_plan={
            "planner_mode": "advisory",
            "advisory_only": True,
            "goal_signature": "pricing|recent|verified|artifact|txt|loc=0|deliver=0",
            "current_chain": ["meta", "research"],
            "recommended_chain": ["meta", "research"],
            "recommended_recipe_hint": "knowledge_research",
            "confidence": 0.82,
            "reason": "current_chain_retained",
            "goal_gaps": ["artifact_output_stage_missing"],
            "candidate_chains": [],
        },
    )

    result = await MetaAgent.run(agent, task)

    assert result.startswith("**Dokument erstellt:**")
    assert len(recorded) == 1
    assert recorded[0]["goal_signature"] == "pricing|recent|verified|artifact|txt|loc=0|deliver=0"
    assert recorded[0]["final_chain"] == ["meta", "research", "document"]
    assert recorded[0]["runtime_gap_insertions"] == ["runtime_goal_gap_document"]
    assert recorded[0]["success"] is True
    assert [item["event_type"] for item in observed] == [
        "runtime_goal_gap_inserted",
        "meta_recipe_outcome",
    ]


@pytest.mark.asyncio
async def test_meta_system_diagnosis_emits_primary_fix_task_from_system_result(monkeypatch):
    from agent.agents.meta import MetaAgent
    from agent.base_agent import BaseAgent

    observed = []

    async def _fake_call_tool(self, method: str, params: dict):
        assert method == "delegate_to_agent"
        assert params["agent_type"] == "system"
        return {
            "status": "success",
            "agent": "system",
            "result": (
                "Diagnose: System stabil aber mit wiederkehrenden Vision-Tool-Fehlern.\n"
                "Ursache:\n\n"
                "Vision-Engine Datentyp-Fehler: Moondream gibt dict statt string zurueck -> "
                "AttributeError: 'dict' object has no attribute 'strip' in tools/verified_vision_tool/tool.py:352\n"
                "Screen-Contract OCR-Fehler: OCR-Texte kommen als dict statt str -> "
                "TypeError in tools/screen_contract_tool/tool.py:118\n"
                "Tool-Loop-Erkennung: Mehrfache Wiederholungen bei get_all_screen_text und scan_ui_elements.\n"
                "Empfehlung:\n"
                "Vision-Tool zuerst beheben."
            ),
            "blackboard_key": "delegation:system:vision",
            "metadata": {},
            "artifacts": [],
        }

    monkeypatch.setattr(BaseAgent, "_call_tool", _fake_call_tool)
    monkeypatch.setattr(
        "agent.agents.meta.record_autonomy_observation",
        lambda event_type, payload, observed_at="": observed.append(
            {"event_type": event_type, "payload": dict(payload), "observed_at": observed_at}
        )
        or True,
    )

    agent = MetaAgent.__new__(MetaAgent)
    agent.conversation_session_id = "sess-meta-system-primary-fix"

    task = _build_meta_task(
        recipe_id="system_diagnosis",
        chain="meta -> system",
        stages=[
            ("system_observe", "system", "Analysiere Logs und Services", "incident_summary", False),
            ("shell_remediation", "shell", "Nur falls noetig", "command_output", True),
        ],
        original_task=(
            "Analysiere den aktuell wichtigsten wiederkehrenden Fehler aus den Logs und erstelle daraus "
            "genau einen Primary-Fix-Task. Wenn die Root Cause nicht belegt ist, gib verification needed aus."
        ),
        task_type="system_diagnosis",
        site_kind="ops",
    )

    result = await MetaAgent.run(agent, task)

    assert result.startswith("Primary-Fix-Task")
    assert "tools/verified_vision_tool/tool.py" in result
    assert "type_normalization" in result
    event_types = [item["event_type"] for item in observed]
    assert "lead_diagnosis_selected" in event_types
    assert "developer_task_compiled" in event_types
    assert "primary_fix_task_emitted" in event_types


@pytest.mark.asyncio
async def test_meta_system_diagnosis_returns_verification_needed_without_verified_root_cause(monkeypatch):
    from agent.agents.meta import MetaAgent
    from agent.base_agent import BaseAgent

    observed = []

    async def _fake_call_tool(self, method: str, params: dict):
        assert method == "delegate_to_agent"
        assert params["agent_type"] == "system"
        return {
            "status": "success",
            "agent": "system",
            "result": (
                "Diagnose: System stabil.\n"
                "Ursache:\n\n"
                "Monitoring fuer kuenftige Vorfaelle verbessern.\n"
                "Empfehlung:\n"
                "Spaeter Telemetrie ausbauen."
            ),
            "blackboard_key": "delegation:system:weak",
            "metadata": {},
            "artifacts": [],
        }

    monkeypatch.setattr(BaseAgent, "_call_tool", _fake_call_tool)
    monkeypatch.setattr(
        "agent.agents.meta.record_autonomy_observation",
        lambda event_type, payload, observed_at="": observed.append(
            {"event_type": event_type, "payload": dict(payload), "observed_at": observed_at}
        )
        or True,
    )

    agent = MetaAgent.__new__(MetaAgent)
    agent.conversation_session_id = "sess-meta-system-verification-needed"

    task = _build_meta_task(
        recipe_id="system_diagnosis",
        chain="meta -> system",
        stages=[
            ("system_observe", "system", "Analysiere Logs und Services", "incident_summary", False),
        ],
        original_task=(
            "Analysiere den aktuell wichtigsten wiederkehrenden Fehler aus den Logs und erstelle daraus "
            "genau einen Primary-Fix-Task. Wenn die Root Cause nicht belegt ist, gib verification needed aus."
        ),
        task_type="system_diagnosis",
        site_kind="ops",
    )

    result = await MetaAgent.run(agent, task)

    assert result.startswith("verification needed")
    assert "weak_root_cause_evidence" in result
    event_types = [item["event_type"] for item in observed]
    assert "lead_diagnosis_selected" in event_types
    assert "developer_task_compiled" in event_types
    assert "root_cause_gate_blocked" in event_types


@pytest.mark.asyncio
async def test_meta_call_tool_records_specialist_and_direct_meta_observation(monkeypatch):
    from agent.agents.meta import MetaAgent
    from agent.base_agent import BaseAgent

    observed = []

    async def _fake_call_tool(self, method: str, params: dict):
        if method == "delegate_to_agent":
            return {
                "status": "error",
                "agent": params["agent_type"],
                "error": "context overflow",
                "blackboard_key": "delegation:research:ctx",
            }
        if method == "search_web":
            return {"status": "error", "error": "timeout"}
        return {"status": "success"}

    monkeypatch.setattr(BaseAgent, "_call_tool", _fake_call_tool)
    monkeypatch.setattr(
        "agent.agents.meta.record_autonomy_observation",
        lambda event_type, payload, observed_at="": observed.append(
            {"event_type": event_type, "payload": dict(payload), "observed_at": observed_at}
        )
        or True,
    )

    agent = MetaAgent.__new__(MetaAgent)
    agent.conversation_session_id = "sess-meta-observation"

    specialist = await MetaAgent._call_tool(
        agent,
        "start_deep_research",
        {"query": "LLM Markt 2026"},
    )
    direct = await MetaAgent._call_tool(
        agent,
        "search_web",
        {"query": "best countries tech immigration 2026"},
    )

    assert specialist["status"] == "error"
    assert direct["status"] == "error"
    assert [item["event_type"] for item in observed] == [
        "meta_specialist_delegation",
        "meta_direct_tool_call",
    ]
    assert observed[0]["payload"]["agent"] == "research"
    assert observed[0]["payload"]["status"] == "error"
    assert observed[1]["payload"]["method"] == "search_web"
    assert observed[1]["payload"]["has_error"] is True


@pytest.mark.asyncio
async def test_meta_screen_text_read_uses_direct_tool_instead_of_visual_delegation(monkeypatch):
    from agent.agents.meta import MetaAgent
    from agent.base_agent import BaseAgent

    observed = []
    calls = []

    async def _fake_call_tool(self, method: str, params: dict):
        calls.append((method, dict(params or {})))
        if method == "delegate_to_agent":
            raise AssertionError("screen-text reads should not delegate to visual anymore")
        if method == "get_all_screen_text":
            return {"status": "success", "text": "Google Calendar", "items": ["Google Calendar"]}
        raise AssertionError(f"unexpected method: {method}")

    monkeypatch.setattr(BaseAgent, "_call_tool", _fake_call_tool)
    monkeypatch.setattr(
        "agent.agents.meta.record_autonomy_observation",
        lambda event_type, payload, observed_at="": observed.append(
            {"event_type": event_type, "payload": dict(payload), "observed_at": observed_at}
        )
        or True,
    )

    agent = MetaAgent.__new__(MetaAgent)
    agent.conversation_session_id = "sess-meta-direct-screen-text"

    result = await MetaAgent._call_tool(agent, "get_all_screen_text", {})

    assert result["status"] == "success"
    assert calls == [("get_all_screen_text", {})]
    assert [item["event_type"] for item in observed] == ["meta_direct_tool_call"]
    assert observed[0]["payload"]["method"] == "get_all_screen_text"
    assert observed[0]["payload"]["has_error"] is False


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
