import os
import sys
import json
from pathlib import Path

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent import providers as providers_mod
from agent.agents.communication import CommunicationAgent
from agent.agents.document import DocumentAgent
from agent.agents.executor import ExecutorAgent
from agent.agents.research import DeepResearchAgent
from agent.agents.shell import ShellAgent
from agent.agents.system import SystemAgent
from agent.agents.visual import VisualAgent
from agent.base_agent import BaseAgent
from agent.shared.delegation_handoff import parse_delegation_handoff
from orchestration.specialist_context import build_specialist_context_payload


@pytest.fixture(autouse=True)
def _disable_model_validation(monkeypatch):
    monkeypatch.setenv("TIMUS_VALIDATE_CONFIGURED_MODELS", "false")
    providers_mod._provider_client = None
    yield
    providers_mod._provider_client = None


def _sample_handoff() -> str:
    specialist_context = build_specialist_context_payload(
        current_topic="YouTube-Modellvergleich",
        active_goal="Hauptthesen aus dem Video extrahieren",
        open_loop="Videoseite oeffnen und Kontext sichern",
        turn_type="followup",
        response_mode="execute",
        user_preferences=["Quellen zuerst"],
        recent_corrections=["Nicht in Deep Research kippen"],
    )
    return (
        "# DELEGATION HANDOFF\n"
        "target_agent: visual\n"
        "goal: Oeffne die YouTube-Seite und erreiche die Videoseite.\n"
        "expected_output: source_url, page_state, page_title, captured_context\n"
        "success_signal: Zielzustand bestaetigt\n"
        "constraints:\n"
        "- recipe_stage=visual_access\n"
        "- site_kind=youtube\n"
        "handoff_data:\n"
        "- recipe_id: youtube_content_extraction\n"
        "- stage_id: visual_access\n"
        "- expected_state: video_page\n"
        "- source_url: https://www.youtube.com/watch?v=abc123\n"
        "- previous_stage_result: Suchergebnisse fuer Modellvergleich\n"
        "- previous_blackboard_key: bb-meta-42\n"
        f"- specialist_context_json: {json.dumps(specialist_context, ensure_ascii=False, sort_keys=True)}\n"
    )


def _handoff_for(agent: str, goal: str, extra: str = "") -> str:
    specialist_context = build_specialist_context_payload(
        current_topic="D0.9 Specialist Context",
        active_goal=goal,
        open_loop="Vorliegenden Handoff zielgerichtet bearbeiten",
        turn_type="followup",
        response_mode="execute",
        user_preferences=["Bleibe knapp und kontexttreu"],
        recent_corrections=["Nicht vom eigentlichen Ziel abdriften"],
    )
    return (
        "# DELEGATION HANDOFF\n"
        f"target_agent: {agent}\n"
        f"goal: {goal}\n"
        "expected_output: strukturierter Output\n"
        "success_signal: Zielzustand bestaetigt\n"
        "constraints:\n"
        "- handoff=true\n"
        "handoff_data:\n"
        "- recipe_id: test_recipe\n"
        "- stage_id: stage_alpha\n"
        "- previous_stage_result: vorgaenger ok\n"
        f"- specialist_context_json: {json.dumps(specialist_context, ensure_ascii=False, sort_keys=True)}\n"
        + extra
    )


def test_parse_delegation_handoff_extracts_structured_fields():
    payload = parse_delegation_handoff(_sample_handoff())

    assert payload is not None
    assert payload.target_agent == "visual"
    assert payload.goal == "Oeffne die YouTube-Seite und erreiche die Videoseite."
    assert payload.expected_output.startswith("source_url")
    assert payload.success_signal == "Zielzustand bestaetigt"
    assert "recipe_stage=visual_access" in payload.constraints
    assert payload.handoff_data["expected_state"] == "video_page"
    assert payload.handoff_data["source_url"] == "https://www.youtube.com/watch?v=abc123"
    assert "specialist_context_json" in payload.handoff_data


def test_visual_prepare_task_uses_goal_and_handoff_state():
    agent = VisualAgent(tools_description_string="")

    effective_task, context = agent._prepare_visual_task(_sample_handoff())

    assert effective_task == "Oeffne die YouTube-Seite und erreiche die Videoseite."
    assert "expected_state=video_page" in context
    assert "recipe_id=youtube_content_extraction" in context
    assert "previous_stage_result=Suchergebnisse fuer Modellvergleich" in context
    assert "SPEZIALISTENKONTEXT:" in context
    assert "Aktuelles Thema: YouTube-Modellvergleich" in context
    assert agent.current_browser_url == "https://www.youtube.com/watch?v=abc123"


@pytest.mark.asyncio
async def test_research_run_uses_structured_handoff_context(monkeypatch):
    captured = {}
    specialist_context = build_specialist_context_payload(
        current_topic="YouTube-Faktencheck",
        active_goal="Hauptthesen extrahieren",
        open_loop="Quellen und Kernaussagen sichern",
        turn_type="followup",
        response_mode="execute",
        user_preferences=["Bleibe knapp und kontexttreu"],
        recent_corrections=["Nicht vom eigentlichen Ziel abdriften"],
    )

    async def _fake_context(self, task: str, policy=None) -> str:
        captured["effective_task"] = task
        captured["policy"] = dict(policy or {})
        return "# RECHERCHE-KONTEXT (automatisch geladen)\nAktive Timus-Ziele: testing"

    async def _fake_super_run(self, task: str) -> str:
        captured["enriched_task"] = task
        return "ok"

    handoff_task = """# DELEGATION HANDOFF
target_agent: research
goal: Analysiere das YouTube-Video und extrahiere die Hauptthesen.
expected_output: summary, sources, extracted_content
success_signal: belastbare Zusammenfassung mit Quellen
handoff_data:
- recipe_id: youtube_content_extraction
- stage_id: research_synthesis
- source_urls: https://www.youtube.com/watch?v=abc123
- captured_context: Titel und Beschreibung bereits gesichert
- previous_stage_result: YouTube-Seite erfolgreich geoeffnet
- specialist_context_json: {specialist_context_json}
"""
    handoff_task = handoff_task.format(
        specialist_context_json=json.dumps(specialist_context, ensure_ascii=False, sort_keys=True)
    )

    monkeypatch.setattr(DeepResearchAgent, "_build_research_context", _fake_context)
    monkeypatch.setattr(BaseAgent, "run", _fake_super_run)

    agent = DeepResearchAgent(tools_description_string="")
    try:
        result = await agent.run(handoff_task)
    finally:
        await agent.http_client.aclose()

    assert result == "ok"
    assert captured["effective_task"] == "Analysiere das YouTube-Video und extrahiere die Hauptthesen."
    assert captured["policy"]["source_first"] is True
    assert captured["enriched_task"].startswith("Analysiere das YouTube-Video")
    assert "# STRUKTURIERTER RESEARCH-HANDOFF" in captured["enriched_task"]
    assert "# SPEZIALISTENKONTEXT" in captured["enriched_task"]
    assert "Nutzerpraeferenzen: Bleibe knapp und kontexttreu" in captured["enriched_task"]
    assert "Quell-URLs: https://www.youtube.com/watch?v=abc123" in captured["enriched_task"]
    assert "Bereits erfasster Kontext: Titel und Beschreibung bereits gesichert" in captured["enriched_task"]


@pytest.mark.asyncio
async def test_document_run_uses_structured_handoff(monkeypatch):
    captured = {}

    async def _fake_super_run(self, task: str) -> str:
        captured["task"] = task
        return "ok"

    monkeypatch.setattr(BaseAgent, "run", _fake_super_run)

    agent = DocumentAgent(tools_description_string="")
    result = await agent.run(
        _handoff_for(
            "document",
            "Erstelle einen PDF-Bericht aus den recherchierten Quellen.",
            "- output_format: PDF\n- source_urls: https://example.com/report\n",
        )
    )

    assert result == "ok"
    assert captured["task"].startswith("Erstelle einen PDF-Bericht")
    assert "# STRUKTURIERTER DOCUMENT-HANDOFF" in captured["task"]
    assert "Zielformat: PDF" in captured["task"]


@pytest.mark.asyncio
async def test_document_run_exports_lookup_table_without_llm(monkeypatch):
    captured = {}

    async def _unexpected_super_run(self, task: str) -> str:
        raise AssertionError("BaseAgent.run darf fuer strukturierte Lookup-Tabellenexports nicht aufgerufen werden")

    async def _fake_call_tool(self, method: str, params: dict):
        captured["method"] = method
        captured["params"] = dict(params)
        return {
            "status": "success",
            "path": "results/LLM_Preise_Vergleich.xlsx",
            "filename": "LLM_Preise_Vergleich.xlsx",
        }

    monkeypatch.setattr(BaseAgent, "run", _unexpected_super_run)
    monkeypatch.setattr(BaseAgent, "_call_tool", _fake_call_tool)

    agent = DocumentAgent(tools_description_string="")
    result = await agent.run(
        _handoff_for(
            "document",
            "Erzeuge aus dem Lookup-Ergebnis die angeforderte Tabelle oder Datei.",
            (
                "- output_format: XLSX\n"
                "- artifact_name: LLM_Preise_Vergleich\n"
                "- source_material: | Anbieter | Modell | Input | Output | Cached |\\n"
                "| --- | --- | --- | --- | --- |\\n"
                "| OpenAI | GPT-5.4 mini | $0.75 / 1M | $4.50 / 1M | $0.075 / 1M |\\n"
                "| DeepSeek | DeepSeek V3 | $0.27 / 1M | $1.10 / 1M | $0.07 / 1M |\n"
            ),
        )
    )

    assert captured["method"] == "create_xlsx"
    assert captured["params"]["title"] == "LLM_Preise_Vergleich"
    assert captured["params"]["headers"] == ["Anbieter", "Modell", "Input", "Output", "Cached"]
    assert captured["params"]["rows"][0][0] == "OpenAI"
    assert "Dokument erstellt" in result
    assert "Vorschau" in result


@pytest.mark.asyncio
async def test_system_run_uses_structured_handoff(monkeypatch):
    captured = {}

    async def _fake_snapshot(self, preferred_service: str = "", *, compact: bool = False) -> str:
        captured["preferred_service"] = preferred_service
        captured["compact"] = compact
        return "[SYSTEM-SNAPSHOT]\nCPU: 10%"

    async def _fake_super_run(self, task: str) -> str:
        captured["task"] = task
        return "ok"

    monkeypatch.setattr(SystemAgent, "_get_system_snapshot", _fake_snapshot)
    monkeypatch.setattr(BaseAgent, "run", _fake_super_run)

    agent = SystemAgent(tools_description_string="")
    result = await agent.run(
        _handoff_for(
            "system",
            "Pruefe den Zustand von timus-mcp und liefere eine Diagnose.",
            "- service_name: timus-mcp\n- expected_state: active\n",
        )
    )

    assert result == "ok"
    assert captured["task"].startswith("Pruefe den Zustand von timus-mcp")
    assert "# STRUKTURIERTER SYSTEM-HANDOFF" in captured["task"]
    assert "# SPEZIALISTENKONTEXT" in captured["task"]
    assert "Jungste Korrekturen: Nicht vom eigentlichen Ziel abdriften" in captured["task"]
    assert "Service: timus-mcp" in captured["task"]
    assert "Erwarteter Zustand: active" in captured["task"]
    assert captured["preferred_service"] == "timus-mcp"


def test_executor_handoff_context_renders_specialist_context():
    agent = ExecutorAgent(tools_description_string="")
    handoff = parse_delegation_handoff(
        _handoff_for(
            "executor",
            "Hol die aktuellen Treffer zu einer kurzen Live-Suche.",
            "- preferred_search_tool: search_web\n",
        )
    )

    context = agent._build_executor_handoff_context(handoff)

    assert "# SPEZIALISTENKONTEXT" in context
    assert "Aktuelles Thema: D0.9 Specialist Context" in context
    assert "Meta-Response-Modus: execute" in context
    assert "Signal-Protokoll:" in context


def test_executor_user_action_blocker_normalizes_phase_d_auth_payload():
    agent = ExecutorAgent(tools_description_string="")
    captured: list[tuple[str, dict]] = []

    def _callback(stage: str, payload: dict) -> None:
        captured.append((stage, payload))

    agent._delegation_progress_callback = _callback
    agent._emit_user_action_blocker(
        {
            "status": "auth_required",
            "platform": "twitter",
            "url": "https://x.com/example/status/1",
            "message": "X/Twitter verlangt Login.",
            "user_action_required": "Bitte Login-Zugriff bestaetigen.",
        }
    )

    assert captured
    stage, payload = captured[0]
    assert stage == "user_action_required"
    assert payload["kind"] == "blocker"
    assert payload["blocker_reason"] == "auth_required"
    assert payload["workflow_id"].startswith("wf_")
    assert payload["service"] == "x"
    assert payload["tool_status"] == "auth_required"
    assert payload["auth_required"] is True


@pytest.mark.asyncio
async def test_executor_short_circuits_when_state_mode_conflicts_with_action_task():
    agent = ExecutorAgent(tools_description_string="")
    specialist_context = build_specialist_context_payload(
        current_topic="Weltlage und News-Qualitaet",
        active_goal="Lagebild zusammenfassen",
        open_loop="Offenen News-Faden zusammenfassen",
        turn_type="followup",
        response_mode="summarize_state",
    )
    task = (
        "# DELEGATION HANDOFF\n"
        "target_agent: executor\n"
        "goal: Fuehre eine kompakte aktuelle Live-Recherche aus.\n"
        "expected_output: Treffer\n"
        "success_signal: erledigt\n"
        "handoff_data:\n"
        "- task_type: simple_live_lookup\n"
        "- original_user_task: Fuehre eine kompakte aktuelle Live-Recherche aus.\n"
        f"- specialist_context_json: {json.dumps(specialist_context, ensure_ascii=False, sort_keys=True)}\n"
    )

    result = await agent.run(task)

    assert result.startswith("Specialist Signal: needs_meta_reframe")
    assert "state_mode_conflicts_with_action_task" in result


@pytest.mark.asyncio
async def test_research_short_circuits_when_lightweight_lookup_hits_deep_research():
    agent = DeepResearchAgent(tools_description_string="")
    specialist_context = build_specialist_context_payload(
        current_topic="Live-News",
        active_goal="Kurzen Nachrichtenstand holen",
        open_loop="Kompakten News-Faden fortsetzen",
        turn_type="followup",
        response_mode="execute",
        user_preferences=["Nicht in Deep Research kippen"],
    )
    task = (
        "# DELEGATION HANDOFF\n"
        "target_agent: research\n"
        "goal: Hole schnell ein kurzes Update zur aktuellen Lage.\n"
        "expected_output: kompakte Treffer\n"
        "success_signal: erledigt\n"
        "handoff_data:\n"
        "- task_type: simple_live_lookup\n"
        "- original_user_task: Hole schnell ein kurzes Update zur aktuellen Lage.\n"
        f"- specialist_context_json: {json.dumps(specialist_context, ensure_ascii=False, sort_keys=True)}\n"
    )

    try:
        result = await agent.run(task)
    finally:
        await agent.http_client.aclose()

    assert result.startswith("Specialist Signal: needs_meta_reframe")
    assert "lightweight_lookup_conflicts_with_deep_research" in result


@pytest.mark.asyncio
async def test_visual_short_circuits_when_state_mode_conflicts_with_visual_action():
    agent = VisualAgent(tools_description_string="")
    specialist_context = build_specialist_context_payload(
        current_topic="Browser-Login",
        active_goal="Status der Login-Hilfe zusammenfassen",
        open_loop="UI-Aktion noch offen",
        turn_type="followup",
        response_mode="summarize_state",
    )
    task = (
        "# DELEGATION HANDOFF\n"
        "target_agent: visual\n"
        "goal: Oeffne die Website und pruefe den Login-Dialog.\n"
        "expected_output: ui_state\n"
        "success_signal: dialog sichtbar\n"
        "handoff_data:\n"
        "- source_url: https://example.com/login\n"
        "- expected_state: login_dialog\n"
        "- original_user_task: Oeffne die Website und pruefe den Login-Dialog.\n"
        f"- specialist_context_json: {json.dumps(specialist_context, ensure_ascii=False, sort_keys=True)}\n"
    )

    result = await agent.run(task)

    assert result.startswith("Specialist Signal: needs_meta_reframe")
    assert "state_mode_conflicts_with_visual_action" in result


@pytest.mark.asyncio
async def test_system_uses_direct_status_summary_when_meta_requests_summary(monkeypatch):
    captured = {}

    async def _fake_snapshot(self, preferred_service: str = "", *, compact: bool = False) -> str:
        captured["preferred_service"] = preferred_service
        captured["compact"] = compact
        return "[SYSTEM-SNAPSHOT]\ntimus-mcp: active"

    async def _unexpected_super_run(self, task: str) -> str:
        raise AssertionError("BaseAgent.run darf fuer direkte Status-Zusammenfassungen nicht aufgerufen werden")

    monkeypatch.setattr(SystemAgent, "_get_system_snapshot", _fake_snapshot)
    monkeypatch.setattr(BaseAgent, "run", _unexpected_super_run)

    agent = SystemAgent(tools_description_string="")
    specialist_context = build_specialist_context_payload(
        current_topic="Runtime-Status",
        active_goal="Status des MCP zusammenfassen",
        open_loop="Health-Frage beantworten",
        turn_type="followup",
        response_mode="summarize_state",
    )
    task = (
        "# DELEGATION HANDOFF\n"
        "target_agent: system\n"
        "goal: Pruefe den Zustand von timus-mcp und fasse ihn kurz zusammen.\n"
        "expected_output: status summary\n"
        "success_signal: status zusammengefasst\n"
        "handoff_data:\n"
        "- service_name: timus-mcp\n"
        "- expected_state: active\n"
        "- original_user_task: Pruefe den Zustand von timus-mcp und fasse ihn kurz zusammen.\n"
        f"- specialist_context_json: {json.dumps(specialist_context, ensure_ascii=False, sort_keys=True)}\n"
    )

    result = await agent.run(task)

    assert "Systemstatus-Zusammenfassung" in result
    assert "Service: timus-mcp" in result
    assert "Erwarteter Zustand: active" in result
    assert "timus-mcp: active" in result
    assert captured["preferred_service"] == "timus-mcp"
    assert captured["compact"] is True


@pytest.mark.asyncio
async def test_research_context_policy_prefers_sources_and_compact_mode():
    agent = DeepResearchAgent(tools_description_string="")
    specialist_context = build_specialist_context_payload(
        current_topic="Live-News",
        active_goal="Belastbare Quellen knapp zusammenfassen",
        open_loop="News-Faden fortsetzen",
        next_expected_step="Bitte knapp zusammenfassen",
        turn_type="followup",
        response_mode="execute",
        user_preferences=["Quellen zuerst", "Bitte kurz"],
    )
    handoff = parse_delegation_handoff(
        "\n".join(
            [
                "# DELEGATION HANDOFF",
                "target_agent: research",
                "goal: Fasse die Lage kompakt zusammen.",
                "expected_output: kompakte Quellenzusammenfassung",
                "handoff_data:",
                "- source_urls: https://example.com/a",
                "- captured_context: erste Notizen vorhanden",
                f"- specialist_context_json: {json.dumps(specialist_context, ensure_ascii=False, sort_keys=True)}",
            ]
        )
    )

    try:
        policy = agent._derive_research_context_policy(handoff, specialist_context)
    finally:
        await agent.http_client.aclose()

    assert policy["source_first"] is True
    assert policy["compact_mode"] is True
    assert policy["suppress_blackboard"] is True
    assert policy["suppress_curiosity"] is True


@pytest.mark.asyncio
async def test_research_context_skips_blackboard_and_curiosity_in_compact_source_mode(monkeypatch):
    agent = DeepResearchAgent(tools_description_string="")
    monkeypatch.setattr(agent, "_get_active_goals", lambda: "Ziel A")
    monkeypatch.setattr(agent, "_get_blackboard_for_task", lambda task: "Blackboard")
    monkeypatch.setattr(agent, "_get_recent_curiosity_topics", lambda: "Curiosity")

    try:
        context = await agent._build_research_context(
            "Kurze Lageeinschaetzung",
            policy={
                "source_first": True,
                "compact_mode": True,
                "suppress_blackboard": True,
                "suppress_curiosity": True,
            },
        )
    finally:
        await agent.http_client.aclose()

    assert "Ziel A" in context
    assert "Blackboard" not in context
    assert "Curiosity" not in context
    assert "Priorisierung: Nutze zuerst uebergebene Quellen" in context
    assert "Priorisierung: Halte den ersten Recherchepass kompakt" in context


@pytest.mark.asyncio
async def test_visual_prefers_vision_first_for_text_reading(monkeypatch):
    agent = VisualAgent(tools_description_string="")
    specialist_context = build_specialist_context_payload(
        current_topic="Dialog lesen",
        active_goal="Zuerst den sichtbaren Text lesen",
        open_loop="OCR/Text zuerst",
        next_expected_step="Bitte zuerst den sichtbaren Text lesen",
        turn_type="followup",
        response_mode="execute",
        user_preferences=["OCR/Text zuerst"],
    )
    task = (
        "# DELEGATION HANDOFF\n"
        "target_agent: visual\n"
        "goal: Lies den sichtbaren Text im Dialog und gib ihn wieder.\n"
        "expected_output: extracted_text\n"
        "success_signal: text erfasst\n"
        "handoff_data:\n"
        "- source_url: https://example.com/login\n"
        "- expected_state: login_dialog\n"
        "- original_user_task: Lies den sichtbaren Text im Dialog und gib ihn wieder.\n"
        f"- specialist_context_json: {json.dumps(specialist_context, ensure_ascii=False, sort_keys=True)}\n"
    )

    async def _unexpected_structured_navigation(self, task_text: str):
        raise AssertionError("_try_structured_navigation darf im vision_first-Modus nicht aufgerufen werden")

    async def _fake_detect_dynamic_ui_and_set_roi(self, task_text: str):
        return False

    async def _fake_call_llm(self, messages):
        return "Final Answer: Text erkannt"

    monkeypatch.setattr(VisualAgent, "_try_structured_navigation", _unexpected_structured_navigation)
    monkeypatch.setattr(VisualAgent, "_detect_dynamic_ui_and_set_roi", _fake_detect_dynamic_ui_and_set_roi)
    monkeypatch.setattr(VisualAgent, "_call_llm", _fake_call_llm)
    monkeypatch.setattr(VisualAgent, "_get_screenshot_as_base64", lambda self: "ZmFrZQ==")

    result = await agent.run(task)

    assert result == "Text erkannt"


@pytest.mark.asyncio
async def test_system_snapshot_compact_mode_targets_requested_service(monkeypatch):
    calls = []

    async def _fake_call_tool(self, method: str, params: dict):
        calls.append((method, dict(params)))
        if method == "get_service_status":
            return {"status": "active"}
        if method == "get_system_stats":
            return {"cpu_percent": 10, "memory_percent": 20, "disk_percent": 30}
        return {}

    monkeypatch.setattr(BaseAgent, "_call_tool", _fake_call_tool)

    agent = SystemAgent(tools_description_string="")
    snapshot = await agent._get_system_snapshot("timus-mcp", compact=True)

    assert "timus-mcp: active" in snapshot
    assert calls == [("get_service_status", {"service_name": "timus-mcp"})]


@pytest.mark.asyncio
async def test_shell_run_uses_structured_handoff(monkeypatch):
    captured = {}

    async def _fake_context(self) -> str:
        return "# SHELL-KONTEXT\nGit: sauber"

    async def _fake_super_run(self, task: str) -> str:
        captured["task"] = task
        return "ok"

    monkeypatch.setattr(ShellAgent, "_build_shell_context", _fake_context)
    monkeypatch.setattr(BaseAgent, "run", _fake_super_run)

    agent = ShellAgent(tools_description_string="")
    result = await agent.run(
        _handoff_for(
            "shell",
            "Sammle Journal-Ausgaben fuer timus-mcp.",
            "- service_name: timus-mcp\n- allowed_command_context: journalctl diagnostics\n",
        )
    )

    assert result == "ok"
    assert captured["task"].startswith("Sammle Journal-Ausgaben")
    assert "# STRUKTURIERTER SHELL-HANDOFF" in captured["task"]
    assert "Service: timus-mcp" in captured["task"]
    assert "Erlaubter Kommando-Kontext: journalctl diagnostics" in captured["task"]


@pytest.mark.asyncio
async def test_communication_run_uses_structured_handoff(monkeypatch):
    captured = {}

    async def _fake_context(self) -> str:
        return "# KOMMUNIKATIONS-KONTEXT\nE-Mail: verbunden"

    async def _fake_super_run(self, task: str) -> str:
        captured["task"] = task
        return "ok"

    monkeypatch.setattr(CommunicationAgent, "_build_comm_context", _fake_context)
    monkeypatch.setattr(CommunicationAgent, "_email_send_requested", staticmethod(lambda task: False))
    monkeypatch.setattr(BaseAgent, "run", _fake_super_run)

    agent = CommunicationAgent(tools_description_string="")
    result = await agent.run(
        _handoff_for(
            "communication",
            "Formuliere eine E-Mail an den Kunden mit kurzem Update.",
            "- channel: email\n- recipient: kunde@example.com\n- subject_hint: Projektupdate\n",
        )
    )

    assert result == "ok"
    assert captured["task"].startswith("Formuliere eine E-Mail")
    assert "# STRUKTURIERTER COMMUNICATION-HANDOFF" in captured["task"]
    assert "Kanal: email" in captured["task"]
    assert "Empfaenger: kunde@example.com" in captured["task"]
