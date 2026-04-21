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
from orchestration.specialist_step_package import build_specialist_step_package_payload


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
    specialist_step_package = build_specialist_step_package_payload(
        plan_summary={
            "plan_id": "yt_plan_1",
            "plan_mode": "multi_step_execution",
            "goal": "Video oeffnen und Hauptthesen sichern",
        },
        plan_step={
            "id": "visual_access",
            "title": "YouTube-Seite oeffnen",
            "step_kind": "execution",
            "assigned_agent": "visual",
            "expected_output": "page_state",
        },
        specialist_context=specialist_context,
        original_user_task="Hole Hauptthesen aus dem YouTube-Video.",
        previous_stage_result="Suchergebnisse fuer Modellvergleich",
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
        f"- specialist_step_package_json: {json.dumps(specialist_step_package, ensure_ascii=False, sort_keys=True)}\n"
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
    specialist_step_package = build_specialist_step_package_payload(
        plan_summary={"plan_id": "test_plan", "plan_mode": "multi_step_execution", "goal": goal},
        plan_step={
            "id": "stage_alpha",
            "title": goal,
            "step_kind": "execution",
            "assigned_agent": agent,
            "expected_output": "strukturierter Output",
        },
        specialist_context=specialist_context,
        original_user_task=goal,
        previous_stage_result="vorgaenger ok",
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
        f"- specialist_step_package_json: {json.dumps(specialist_step_package, ensure_ascii=False, sort_keys=True)}\n"
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
    assert "ARBEITSSCHRITT-PAKET:" in context
    assert "Aktuelles Thema: YouTube-Modellvergleich" in context
    assert "Aktueller Arbeitsschritt: YouTube-Seite oeffnen" in context
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
    specialist_step_package = build_specialist_step_package_payload(
        plan_summary={
            "plan_id": "yt_plan_research",
            "plan_mode": "multi_step_execution",
            "goal": "Hauptthesen und Quellen sichern",
        },
        plan_step={
            "id": "research_synthesis",
            "title": "Hauptthesen aus dem Video verdichten",
            "step_kind": "research",
            "assigned_agent": "research",
            "expected_output": "summary, sources, extracted_content",
        },
        specialist_context=specialist_context,
        original_user_task="Analysiere das YouTube-Video und extrahiere die Hauptthesen.",
        previous_stage_result="YouTube-Seite erfolgreich geoeffnet",
        captured_context="Titel und Beschreibung bereits gesichert",
        source_urls=["https://www.youtube.com/watch?v=abc123"],
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
- specialist_step_package_json: {specialist_step_package_json}
"""
    handoff_task = handoff_task.format(
        specialist_context_json=json.dumps(specialist_context, ensure_ascii=False, sort_keys=True),
        specialist_step_package_json=json.dumps(specialist_step_package, ensure_ascii=False, sort_keys=True),
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
    assert "# ARBEITSSCHRITT-PAKET" in captured["enriched_task"]
    assert "Nutzerpraeferenzen: Bleibe knapp und kontexttreu" in captured["enriched_task"]
    assert "Aktueller Arbeitsschritt:" in captured["enriched_task"]
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
async def test_document_run_reads_explicit_file_evidence_without_llm(monkeypatch):
    tool_calls = []

    async def _unexpected_super_run(self, task: str) -> str:
        raise AssertionError("BaseAgent.run darf fuer explizite Datei-Evidenz nicht aufgerufen werden")

    async def _fake_call_tool(self, method: str, params: dict):
        tool_calls.append((method, dict(params)))
        assert method == "read_file"
        path = str(params.get("path") or "")
        return {
            "status": "success",
            "path": f"/home/fatih-ubuntu/dev/timus/{path}",
            "content": f"Inhalt aus {path}\nNaechster Hauptblock: Zwischenprojekt Mehrschrittplanung",
        }

    monkeypatch.setattr(BaseAgent, "run", _unexpected_super_run)
    monkeypatch.setattr(BaseAgent, "_call_tool", _fake_call_tool)

    agent = DocumentAgent(tools_description_string="")
    result = await agent.run(
        "Lies docs/PHASE_F_PLAN.md und docs/CHANGELOG_DEV.md und sag was als naechstes ansteht."
    )

    assert [call[1]["path"] for call in tool_calls] == [
        "docs/PHASE_F_PLAN.md",
        "docs/CHANGELOG_DEV.md",
    ]
    assert "# DOKUMENT-EVIDENZ" in result
    assert "DATEI: /home/fatih-ubuntu/dev/timus/docs/PHASE_F_PLAN.md" in result
    assert "Naechster Hauptblock: Zwischenprojekt Mehrschrittplanung" in result


@pytest.mark.asyncio
async def test_executor_run_setup_build_probe_uses_repo_search_instead_of_llm(monkeypatch):
    tool_calls = []

    async def _unexpected_super_run(self, task: str) -> str:
        raise AssertionError("BaseAgent.run darf fuer setup_build_probe nicht aufgerufen werden")

    async def _fake_call_tool(self, method: str, params: dict):
        tool_calls.append((method, dict(params)))
        if method == "search_in_files":
            text = str(params.get("text") or "")
            if text == "twilio":
                return {
                    "status": "success",
                    "results": [
                        {
                            "file": "/home/fatih-ubuntu/dev/timus/skills/twilio-voice/scripts/test_call.py",
                            "matches": [{"content": "from twilio.rest import Client"}],
                        }
                    ],
                }
            if text == "inworld":
                return {
                    "status": "success",
                    "results": [
                        {
                            "file": "/home/fatih-ubuntu/dev/timus/tools/voice_tool/tool.py",
                            "matches": [{"content": "INWORLD_API_KEY = os.getenv('INWORLD_API_KEY')"}],
                        }
                    ],
                }
            if text in {"voice_", "voice", "call"}:
                return {
                    "status": "success",
                    "results": [
                        {
                            "file": "/home/fatih-ubuntu/dev/timus/tools/voice_tool/tool.py",
                            "matches": [{"content": "def voice_speak(text: str):"}],
                        }
                    ],
                }
            if text in {"TWILIO_", "INWORLD_"}:
                if text == "TWILIO_":
                    return {
                        "status": "success",
                        "results": [
                            {
                                "file": "/home/fatih-ubuntu/dev/timus/.env",
                                "matches": [{"content": "TWILIO_ACCOUNT_SID=ACsupersecretvalue"}],
                            }
                        ],
                    }
                return {
                    "status": "success",
                    "results": [
                        {
                            "file": "/home/fatih-ubuntu/dev/timus/.env.backup",
                            "matches": [{"content": "INWORLD_API_KEY=verysecretapikey"}],
                        }
                    ],
                }
            raise AssertionError(f"unerwarteter Suchterm: {text}")
        if method == "read_file":
            path = str(params.get("path") or "")
            if path.endswith("test_call.py"):
                return {
                    "status": "success",
                    "path": path,
                    "content": "from twilio.rest import Client\nclient.calls.create(to='x', from_='y')",
                }
            if path.endswith("tool.py"):
                return {
                    "status": "success",
                    "path": path,
                    "content": "INWORLD_API_KEY = os.getenv('INWORLD_API_KEY')\ndef voice_speak(text: str):\n    pass",
                }
            raise AssertionError(f"unerwarteter Dateipfad: {path}")
        raise AssertionError(f"unerwartetes Tool: {method}")

    monkeypatch.setattr(BaseAgent, "run", _unexpected_super_run)
    monkeypatch.setattr(BaseAgent, "_call_tool", _fake_call_tool)

    agent = ExecutorAgent(tools_description_string="")
    result = await agent.run(
        "# DELEGATION HANDOFF\n"
        "target_agent: executor\n"
        "goal: Pruefe vorhandene Vorbereitungen fuer eine Twilio-Anruffunktion mit Inworld-Stimme.\n"
        "expected_output: Repo-Probe\n"
        "success_signal: Setup-Stand geklaert\n"
        "handoff_data:\n"
        "- task_type: setup_build_probe\n"
        "- original_user_task: Richte fuer mich eine Anruffunktion ein. Du sollst mich ueber Twilio anrufen koennen mit der Stimme von Inworld.ai Lennart.\n"
        "- query: Richte fuer mich eine Anruffunktion ein. Du sollst mich ueber Twilio anrufen koennen mit der Stimme von Inworld.ai Lennart.\n"
        "- project_root: /home/fatih-ubuntu/dev/timus\n"
    )

    assert any(method == "search_in_files" for method, _ in tool_calls)
    assert not any(
        method == "read_file" and str(params.get("path") or "").endswith((".env", ".env.backup"))
        for method, params in tool_calls
    )
    assert "Twilio-Bezug im Repo: ja" in result
    assert "Inworld-Bezug im Repo: ja" in result
    assert "Outbound-Call-Logik fuer Twilio sichtbar: ja" in result
    assert "TWILIO_ACCOUNT_SID=<configured>" in result
    assert "INWORLD_API_KEY=<configured>" in result
    assert "ACsupersecretvalue" not in result
    assert "verysecretapikey" not in result


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
async def test_visual_login_flow_stops_at_login_maske_and_returns_awaiting_user(monkeypatch):
    agent = VisualAgent(tools_description_string="")
    specialist_context = build_specialist_context_payload(
        current_topic="GitHub Login",
        active_goal="Bis zur Login-Maske navigieren und dann uebergeben",
        open_loop="Login kontrolliert vorbereiten",
        next_expected_step="Nur bis zur Login-Maske gehen",
        turn_type="followup",
        response_mode="execute",
        user_preferences=["Login user-mediated"],
    )
    task = (
        "# DELEGATION HANDOFF\n"
        "target_agent: visual\n"
        "goal: Oeffne github.com/login und fuehre mich bis zur Login-Maske.\n"
        "expected_output: login_handoff\n"
        "success_signal: login maske sichtbar\n"
        "handoff_data:\n"
        "- source_url: https://github.com/login\n"
        "- expected_state: login_dialog\n"
        "- original_user_task: Oeffne github.com/login und fuehre mich bis zur Login-Maske.\n"
        f"- specialist_context_json: {json.dumps(specialist_context, ensure_ascii=False, sort_keys=True)}\n"
    )

    progress_events = []

    def _progress_callback(*args, **kwargs):
        if kwargs:
            progress_events.append(kwargs)
            return
        stage = args[0] if len(args) > 0 else ""
        payload = args[1] if len(args) > 1 else {}
        progress_events.append({"stage": stage, "payload": payload})

    async def _fake_execute_structured_step(self, step):
        return {
            "success": True,
            "strategy": "dom_lookup",
            "verification_result": {"success": True, "matched_signals": [step.expected_state]},
        }

    async def _fake_detect_dynamic_ui_and_set_roi(self, task_text: str):
        return False

    monkeypatch.setattr(VisualAgent, "_execute_structured_step", _fake_execute_structured_step)
    monkeypatch.setattr(VisualAgent, "_detect_dynamic_ui_and_set_roi", _fake_detect_dynamic_ui_and_set_roi)
    setattr(agent, "_delegation_progress_callback", _progress_callback)

    result = await agent.run(task)

    assert isinstance(result, dict)
    assert result["status"] == "awaiting_user"
    assert result["service"] == "github"
    assert result["reason"] == "user_mediated_login"
    assert result["url"] == "https://github.com/login"
    assert "2fa" in result["user_action_required"].lower()
    assert "weiter" in result["resume_hint"].lower()
    assert progress_events
    payload = progress_events[-1]["payload"]
    assert payload["kind"] == "blocker"
    assert payload["status"] == "awaiting_user"
    assert payload["workflow_reason"] == "user_mediated_login"
    assert payload["workflow_id"].startswith("wf_")


@pytest.mark.asyncio
async def test_visual_login_flow_uses_chrome_credential_broker_when_requested(monkeypatch):
    agent = VisualAgent(tools_description_string="")
    specialist_context = build_specialist_context_payload(
        current_topic="GitHub Login",
        active_goal="Chrome-Profil fuer gespeicherten Login oeffnen",
        open_loop="Login kontrolliert vorbereiten",
        next_expected_step="Chrome-Profil oeffnen und Passwortmanager fuer den gespeicherten Login anbieten",
        turn_type="new_task",
        response_mode="execute",
        user_preferences=["Login user-mediated", "Chrome credential broker"],
    )
    task = (
        "# DELEGATION HANDOFF\n"
        "target_agent: visual\n"
        "goal: Oeffne github.com/login in Chrome und nutze den Passwortmanager.\n"
        "expected_output: login_handoff\n"
        "success_signal: login maske sichtbar\n"
        "handoff_data:\n"
        "- source_url: https://github.com/login\n"
        "- expected_state: login_dialog\n"
        "- browser_type: chrome\n"
        "- credential_broker: chrome_password_manager\n"
        "- broker_profile: Default\n"
        "- domain: github.com\n"
        "- original_user_task: Oeffne github.com/login in Chrome und nutze den Passwortmanager.\n"
        f"- specialist_context_json: {json.dumps(specialist_context, ensure_ascii=False, sort_keys=True)}\n"
    )

    progress_events = []
    browser_calls = []

    def _progress_callback(*args, **kwargs):
        if kwargs:
            progress_events.append(kwargs)
            return
        stage = args[0] if len(args) > 0 else ""
        payload = args[1] if len(args) > 1 else {}
        progress_events.append({"stage": stage, "payload": payload})

    async def _fake_call_tool(self, method: str, params: dict):
        if method == "start_visual_browser":
            browser_calls.append(dict(params))
            return {"success": True, "url": params.get("url")}
        raise AssertionError(f"unexpected tool call: {method}")

    async def _fake_verify_structured_step(self, step):
        return {
            "success": True,
            "matched_signals": [step.expected_state],
            "observation": {"current_url": "https://github.com/login", "elements": []},
        }

    async def _fake_detect_dynamic_ui_and_set_roi(self, task_text: str):
        return False

    async def _fake_detect_credential_broker_ready_state(self, service: str, credential_broker: str):
        return {"success": False, "positive_hits": [], "text_preview": "", "visible_browser": ""}

    monkeypatch.setattr(BaseAgent, "_call_tool", _fake_call_tool)
    monkeypatch.setattr(VisualAgent, "_verify_structured_step", _fake_verify_structured_step)
    monkeypatch.setattr(VisualAgent, "_detect_dynamic_ui_and_set_roi", _fake_detect_dynamic_ui_and_set_roi)
    monkeypatch.setattr(VisualAgent, "_detect_credential_broker_ready_state", _fake_detect_credential_broker_ready_state)
    setattr(agent, "_delegation_progress_callback", _progress_callback)

    result = await agent.run(task)

    assert browser_calls
    assert browser_calls[0]["browser_type"] == "chrome"
    assert browser_calls[0]["profile_name"] == "Default"
    assert isinstance(result, dict)
    assert result["status"] == "awaiting_user"
    assert result["preferred_browser"] == "chrome"
    assert result["credential_broker"] == "chrome_password_manager"
    assert result["broker_profile"] == "Default"
    assert result["domain"] == "github.com"
    assert progress_events
    payload = progress_events[-1]["payload"]
    assert payload["kind"] == "blocker"
    assert payload["tool_status"] == "awaiting_user"


@pytest.mark.asyncio
async def test_visual_login_flow_marks_credential_broker_ready_when_passkey_ui_is_visible(monkeypatch):
    agent = VisualAgent(tools_description_string="")
    specialist_context = build_specialist_context_payload(
        current_topic="GitHub Login",
        active_goal="Chrome-Passwortmanager gezielt uebernehmen lassen",
        open_loop="Broker-Schritt sichtbar unterscheiden",
        next_expected_step="Passkey- oder Passwortmanager-Schritt bestaetigen lassen",
        turn_type="new_task",
        response_mode="execute",
        user_preferences=["Chrome credential broker"],
    )
    task = (
        "# DELEGATION HANDOFF\n"
        "target_agent: visual\n"
        "goal: Oeffne github.com/login in Chrome und nutze den Passwortmanager.\n"
        "expected_output: login_handoff\n"
        "success_signal: login maske sichtbar\n"
        "handoff_data:\n"
        "- source_url: https://github.com/login\n"
        "- expected_state: login_dialog\n"
        "- browser_type: chrome\n"
        "- credential_broker: chrome_password_manager\n"
        "- broker_profile: Default\n"
        "- domain: github.com\n"
        "- original_user_task: Bitte melde mich in Chrome bei GitHub an und nutze den Passwortmanager.\n"
        f"- specialist_context_json: {json.dumps(specialist_context, ensure_ascii=False, sort_keys=True)}\n"
    )

    progress_events = []

    def _progress_callback(*args, **kwargs):
        if kwargs:
            progress_events.append(kwargs)
            return
        stage = args[0] if len(args) > 0 else ""
        payload = args[1] if len(args) > 1 else {}
        progress_events.append({"stage": stage, "payload": payload})

    async def _fake_call_tool(self, method: str, params: dict):
        if method == "start_visual_browser":
            return {"success": True, "url": params.get("url")}
        raise AssertionError(f"unexpected tool call: {method}")

    async def _fake_verify_structured_step(self, step):
        return {
            "success": True,
            "matched_signals": [step.expected_state],
            "observation": {"current_url": "https://github.com/login", "elements": []},
        }

    async def _fake_detect_dynamic_ui_and_set_roi(self, task_text: str):
        return False

    async def _fake_detect_authenticated_session_state(self, service: str):
        return {"success": False, "positive_hits": [], "negative_hits": [], "text_preview": "", "visible_browser": "chrome"}

    async def _fake_detect_credential_broker_ready_state(self, service: str, credential_broker: str):
        return {
            "success": True,
            "positive_hits": ["sign in with a passkey", "passkey"],
            "text_preview": "sign in with a passkey | chrome",
            "visible_browser": "chrome",
        }

    monkeypatch.setattr(BaseAgent, "_call_tool", _fake_call_tool)
    monkeypatch.setattr(VisualAgent, "_verify_structured_step", _fake_verify_structured_step)
    monkeypatch.setattr(VisualAgent, "_detect_dynamic_ui_and_set_roi", _fake_detect_dynamic_ui_and_set_roi)
    monkeypatch.setattr(VisualAgent, "_detect_authenticated_session_state", _fake_detect_authenticated_session_state)
    monkeypatch.setattr(VisualAgent, "_detect_credential_broker_ready_state", _fake_detect_credential_broker_ready_state)
    setattr(agent, "_delegation_progress_callback", _progress_callback)

    result = await agent.run(task)

    assert isinstance(result, dict)
    assert result["status"] == "awaiting_user"
    assert result["step"] == "credential_broker_ready"
    assert result["credential_broker"] == "chrome_password_manager"
    assert "passkey" in result["message"].lower()
    assert "gespeicherten zugang" in result["user_action_required"].lower()
    assert progress_events
    payload = progress_events[-1]["payload"]
    assert payload["kind"] == "blocker"
    assert payload["tool_status"] == "awaiting_user"
    assert "passkey" in payload["message"].lower()


@pytest.mark.asyncio
async def test_visual_login_flow_returns_manual_browser_prepare_when_chrome_context_is_not_ready(monkeypatch):
    agent = VisualAgent(tools_description_string="")
    specialist_context = build_specialist_context_payload(
        current_topic="GitHub Login",
        active_goal="Chrome-Login nur bis zum sicheren Hand-off vorbereiten",
        open_loop="Chrome und Passwortmanager kontrolliert einbinden",
        next_expected_step="Wenn Chrome nicht sauber bereit ist, Nutzer gezielt uebernehmen lassen",
        turn_type="new_task",
        response_mode="execute",
        user_preferences=["Login dynamisch behandeln", "Chrome credential broker"],
    )
    task = (
        "# DELEGATION HANDOFF\n"
        "target_agent: visual\n"
        "goal: Oeffne github.com/login in Chrome und nutze den Passwortmanager.\n"
        "expected_output: login_handoff\n"
        "success_signal: login maske sichtbar\n"
        "handoff_data:\n"
        "- source_url: https://github.com/login\n"
        "- expected_state: login_dialog\n"
        "- browser_type: chrome\n"
        "- credential_broker: chrome_password_manager\n"
        "- broker_profile: Default\n"
        "- domain: github.com\n"
        "- original_user_task: Bitte melde mich in Chrome bei GitHub an und nutze den Passwortmanager.\n"
        f"- specialist_context_json: {json.dumps(specialist_context, ensure_ascii=False, sort_keys=True)}\n"
    )

    progress_events = []
    browser_calls = []

    def _progress_callback(*args, **kwargs):
        if kwargs:
            progress_events.append(kwargs)
            return
        stage = args[0] if len(args) > 0 else ""
        payload = args[1] if len(args) > 1 else {}
        progress_events.append({"stage": stage, "payload": payload})

    async def _fake_call_tool(self, method: str, params: dict):
        if method == "start_visual_browser":
            browser_calls.append(dict(params))
            return {"success": True, "url": params.get("url")}
        raise AssertionError(f"unexpected tool call: {method}")

    async def _fake_verify_structured_step(self, step):
        return {
            "success": False,
            "matched_signals": [],
            "observation": {"current_url": "about:blank", "elements": []},
        }

    async def _fake_detect_authenticated_session_state(self, service: str):
        return {
            "success": False,
            "positive_hits": [],
            "negative_hits": [],
            "text_preview": "mozilla firefox timus canvas",
            "visible_browser": "firefox",
        }

    async def _fake_detect_dynamic_ui_and_set_roi(self, task_text: str):
        return False

    async def _unexpected_llm(self, messages):
        raise AssertionError("LLM-Fallback darf fuer den manuellen Chrome-Prepare-Pfad nicht aufgerufen werden")

    monkeypatch.setattr(BaseAgent, "_call_tool", _fake_call_tool)
    monkeypatch.setattr(VisualAgent, "_verify_structured_step", _fake_verify_structured_step)
    monkeypatch.setattr(VisualAgent, "_detect_authenticated_session_state", _fake_detect_authenticated_session_state)
    monkeypatch.setattr(VisualAgent, "_detect_dynamic_ui_and_set_roi", _fake_detect_dynamic_ui_and_set_roi)
    monkeypatch.setattr(VisualAgent, "_call_llm", _unexpected_llm)
    setattr(agent, "_delegation_progress_callback", _progress_callback)

    result = await agent.run(task)

    assert browser_calls
    assert browser_calls[0]["browser_type"] == "chrome"
    assert browser_calls[0]["profile_name"] == "Default"
    assert isinstance(result, dict)
    assert result["status"] == "awaiting_user"
    assert result["step"] == "manual_browser_prepare"
    assert result["credential_broker"] == "chrome_password_manager"
    assert "chrome" in result["message"].lower()
    assert "https://github.com/login" in result["user_action_required"].lower()
    assert progress_events
    payload = progress_events[-1]["payload"]
    assert payload["kind"] == "blocker"
    assert payload["tool_status"] == "awaiting_user"
    assert payload["workflow_reason"] == "user_mediated_login"
    assert "https://github.com/login" in payload["user_action_required"].lower()


@pytest.mark.asyncio
async def test_visual_login_flow_stops_after_login_modal_mismatch_instead_of_falling_back_to_vision(monkeypatch):
    agent = VisualAgent(tools_description_string="")
    specialist_context = build_specialist_context_payload(
        current_topic="GitHub Login",
        active_goal="Chrome-Login nur bis zum sicheren Hand-off vorbereiten",
        open_loop="Nach erfolgreicher Navigation nicht in den Vision-Loop kippen",
        next_expected_step="Wenn die Login-Maske nicht bestaetigt werden kann, sofort awaiting_user setzen",
        turn_type="new_task",
        response_mode="execute",
        user_preferences=["Login dynamisch behandeln", "Chrome credential broker"],
    )
    task = (
        "# DELEGATION HANDOFF\n"
        "target_agent: visual\n"
        "goal: Oeffne github.com/login in Chrome und nutze den Passwortmanager.\n"
        "expected_output: login_handoff\n"
        "success_signal: login maske sichtbar\n"
        "handoff_data:\n"
        "- source_url: https://github.com/login\n"
        "- expected_state: login_dialog\n"
        "- browser_type: chrome\n"
        "- credential_broker: chrome_password_manager\n"
        "- broker_profile: Default\n"
        "- domain: github.com\n"
        "- original_user_task: Bitte melde mich in Chrome bei GitHub an und nutze den Passwortmanager.\n"
        f"- specialist_context_json: {json.dumps(specialist_context, ensure_ascii=False, sort_keys=True)}\n"
    )

    progress_events = []
    browser_calls = []
    verify_states = []

    def _progress_callback(*args, **kwargs):
        if kwargs:
            progress_events.append(kwargs)
            return
        stage = args[0] if len(args) > 0 else ""
        payload = args[1] if len(args) > 1 else {}
        progress_events.append({"stage": stage, "payload": payload})

    async def _fake_call_tool(self, method: str, params: dict):
        if method == "start_visual_browser":
            browser_calls.append(dict(params))
            return {"success": True, "url": params.get("url")}
        raise AssertionError(f"unexpected tool call: {method}")

    async def _fake_verify_structured_step(self, step):
        verify_states.append(step.expected_state)
        if step.expected_state == "landing":
            return {
                "success": True,
                "matched_signals": ["url_contains=github.com"],
                "observation": {"current_url": "https://github.com/login", "elements": []},
            }
        return {
            "success": False,
            "matched_signals": [],
            "observation": {"current_url": "about:blank", "elements": []},
        }

    async def _fake_detect_authenticated_session_state(self, service: str):
        return {
            "success": False,
            "positive_hits": [],
            "negative_hits": [],
            "text_preview": "mozilla firefox timus canvas",
            "visible_browser": "firefox",
        }

    async def _fake_detect_visible_browser_state(self):
        return {
            "success": True,
            "visible_browser": "firefox",
            "text_preview": "mozilla firefox timus canvas",
        }

    async def _fake_detect_dynamic_ui_and_set_roi(self, task_text: str):
        return False

    async def _unexpected_llm(self, messages):
        raise AssertionError("LLM-Fallback darf nach login_modal-Mismatch nicht mehr aufgerufen werden")

    monkeypatch.setattr(BaseAgent, "_call_tool", _fake_call_tool)
    monkeypatch.setattr(VisualAgent, "_verify_structured_step", _fake_verify_structured_step)
    monkeypatch.setattr(VisualAgent, "_detect_authenticated_session_state", _fake_detect_authenticated_session_state)
    monkeypatch.setattr(VisualAgent, "_detect_visible_browser_state", _fake_detect_visible_browser_state)
    monkeypatch.setattr(VisualAgent, "_detect_dynamic_ui_and_set_roi", _fake_detect_dynamic_ui_and_set_roi)
    monkeypatch.setattr(VisualAgent, "_call_llm", _unexpected_llm)
    setattr(agent, "_delegation_progress_callback", _progress_callback)

    result = await agent.run(task)

    assert browser_calls
    assert verify_states[:2] == ["landing", "login_modal"]
    assert isinstance(result, dict)
    assert result["status"] == "awaiting_user"
    assert result["step"] == "manual_browser_prepare"
    assert result["credential_broker"] == "chrome_password_manager"
    assert "nicht chrome" in result["message"].lower()
    assert "https://github.com/login" in result["user_action_required"].lower()
    assert progress_events
    payload = progress_events[-1]["payload"]
    assert payload["kind"] == "blocker"
    assert payload["tool_status"] == "awaiting_user"
    assert payload["workflow_reason"] == "user_mediated_login"


@pytest.mark.asyncio
async def test_visual_login_flow_returns_manual_prepare_when_generic_login_entry_cannot_be_confirmed(monkeypatch):
    agent = VisualAgent(tools_description_string="")
    specialist_context = build_specialist_context_payload(
        current_topic="Generischer Chrome Login",
        active_goal="Unbekannte Sites ohne starres /login behandeln",
        open_loop="Wenn der Login-Einstieg nicht sicher gefunden wird, geordnet an den Nutzer uebergeben",
        next_expected_step="Bei Root-Domain-Discovery nicht in den Vision-Loop kippen",
        turn_type="new_task",
        response_mode="execute",
        user_preferences=["Login dynamisch behandeln", "Chrome credential broker"],
    )
    task = (
        "# DELEGATION HANDOFF\n"
        "target_agent: visual\n"
        "goal: Oeffne grok.com in Chrome und nutze den Passwortmanager.\n"
        "expected_output: login_handoff\n"
        "success_signal: login maske sichtbar\n"
        "handoff_data:\n"
        "- source_url: https://grok.com\n"
        "- expected_state: login_dialog\n"
        "- browser_type: chrome\n"
        "- credential_broker: chrome_password_manager\n"
        "- broker_profile: Default\n"
        "- domain: grok.com\n"
        "- original_user_task: Bitte melde mich in Chrome bei grok.com an und nutze den Passwortmanager.\n"
        f"- specialist_context_json: {json.dumps(specialist_context, ensure_ascii=False, sort_keys=True)}\n"
    )

    progress_events = []
    executed_actions = []

    def _progress_callback(*args, **kwargs):
        if kwargs:
            progress_events.append(kwargs)
            return
        stage = args[0] if len(args) > 0 else ""
        payload = args[1] if len(args) > 1 else {}
        progress_events.append({"stage": stage, "payload": payload})

    async def _fake_execute_structured_step(self, step):
        executed_actions.append(step.action)
        if step.action == "navigate":
            return {
                "success": True,
                "strategy": "direct_navigate",
                "matched_signals": ["url_contains=grok.com"],
                "verification_result": {
                    "success": True,
                    "matched_signals": ["url_contains=grok.com"],
                    "observation": {"current_url": "https://grok.com", "elements": []},
                },
            }
        return {
            "success": False,
            "strategy": "vision_scan",
            "verification_result": {
                "success": False,
                "matched_signals": [],
                "observation": {"current_url": "https://grok.com", "elements": []},
            },
        }

    async def _fake_detect_authenticated_session_state(self, service: str):
        return {
            "success": False,
            "positive_hits": [],
            "negative_hits": [],
            "text_preview": "grok chrome",
            "visible_browser": "chrome",
        }

    async def _fake_detect_visible_browser_state(self):
        return {
            "success": True,
            "visible_browser": "chrome",
            "text_preview": "grok chrome",
        }

    async def _fake_detect_credential_broker_ready_state(self, service: str, credential_broker: str):
        return {
            "success": False,
            "positive_hits": [],
            "negative_hits": [],
            "text_preview": "grok chrome",
            "visible_browser": "chrome",
        }

    async def _fake_detect_dynamic_ui_and_set_roi(self, task_text: str):
        return False

    async def _unexpected_llm(self, messages):
        raise AssertionError("LLM-Fallback darf nach generic-login-entry-Mismatch nicht aufgerufen werden")

    monkeypatch.setattr(VisualAgent, "_execute_structured_step", _fake_execute_structured_step)
    monkeypatch.setattr(VisualAgent, "_detect_authenticated_session_state", _fake_detect_authenticated_session_state)
    monkeypatch.setattr(VisualAgent, "_detect_visible_browser_state", _fake_detect_visible_browser_state)
    monkeypatch.setattr(VisualAgent, "_detect_credential_broker_ready_state", _fake_detect_credential_broker_ready_state)
    monkeypatch.setattr(VisualAgent, "_detect_dynamic_ui_and_set_roi", _fake_detect_dynamic_ui_and_set_roi)
    monkeypatch.setattr(VisualAgent, "_call_llm", _unexpected_llm)
    setattr(agent, "_delegation_progress_callback", _progress_callback)

    result = await agent.run(task)

    assert executed_actions[:2] == ["navigate", "click_target"]
    assert isinstance(result, dict)
    assert result["status"] == "awaiting_user"
    assert result["step"] == "manual_browser_prepare"
    assert result["credential_broker"] == "chrome_password_manager"
    assert "login-einstieg" in result["message"].lower()
    assert "https://grok.com" in result["user_action_required"].lower()
    assert progress_events
    payload = progress_events[-1]["payload"]
    assert payload["kind"] == "blocker"
    assert payload["tool_status"] == "awaiting_user"
    assert payload["workflow_reason"] == "user_mediated_login"


@pytest.mark.asyncio
async def test_visual_login_flow_accepts_visible_authenticated_state_as_goal_satisfied(monkeypatch):
    agent = VisualAgent(tools_description_string="")
    specialist_context = build_specialist_context_payload(
        current_topic="GitHub Login",
        active_goal="Wenn schon eingeloggt, Login-Schritt ueberspringen",
        open_loop="GitHub-Zugriff funktional sicherstellen",
        next_expected_step="Bei bestehender Auth direkt fortsetzen",
        turn_type="new_task",
        response_mode="execute",
        user_preferences=["Login dynamisch behandeln"],
    )
    task = (
        "# DELEGATION HANDOFF\n"
        "target_agent: visual\n"
        "goal: Oeffne github.com/login in Chrome und nutze den Passwortmanager.\n"
        "expected_output: login_handoff\n"
        "success_signal: login maske sichtbar\n"
        "handoff_data:\n"
        "- source_url: https://github.com/login\n"
        "- expected_state: login_dialog\n"
        "- browser_type: chrome\n"
        "- credential_broker: chrome_password_manager\n"
        "- broker_profile: Default\n"
        "- domain: github.com\n"
        "- original_user_task: Oeffne github.com/login in Chrome und nutze den Passwortmanager.\n"
        f"- specialist_context_json: {json.dumps(specialist_context, ensure_ascii=False, sort_keys=True)}\n"
    )

    progress_events = []
    browser_calls = []

    def _progress_callback(*args, **kwargs):
        if kwargs:
            progress_events.append(kwargs)
            return
        stage = args[0] if len(args) > 0 else ""
        payload = args[1] if len(args) > 1 else {}
        progress_events.append({"stage": stage, "payload": payload})

    async def _fake_call_tool(self, method: str, params: dict):
        if method == "start_visual_browser":
            browser_calls.append(dict(params))
            return {"success": True, "url": params.get("url")}
        raise AssertionError(f"unexpected tool call: {method}")

    async def _fake_verify_structured_step(self, step):
        if step.expected_state == "login_modal":
            return {
                "success": False,
                "matched_signals": [],
                "observation": {"current_url": "https://github.com", "elements": []},
            }
        return {
            "success": True,
            "matched_signals": [step.expected_state],
            "observation": {"current_url": "https://github.com", "elements": []},
        }

    async def _fake_detect_authenticated_session_state(self, service: str):
        return {
            "success": True,
            "positive_hits": ["repositories", "profile"],
            "negative_hits": [],
            "text_preview": "repositories profile mozilla firefox",
            "visible_browser": "firefox",
        }

    async def _fake_detect_dynamic_ui_and_set_roi(self, task_text: str):
        return False

    monkeypatch.setattr(BaseAgent, "_call_tool", _fake_call_tool)
    monkeypatch.setattr(VisualAgent, "_verify_structured_step", _fake_verify_structured_step)
    monkeypatch.setattr(VisualAgent, "_detect_authenticated_session_state", _fake_detect_authenticated_session_state)
    monkeypatch.setattr(VisualAgent, "_detect_dynamic_ui_and_set_roi", _fake_detect_dynamic_ui_and_set_roi)
    setattr(agent, "_delegation_progress_callback", _progress_callback)

    result = await agent.run(task)

    assert browser_calls
    assert browser_calls[0]["browser_type"] == "chrome"
    assert browser_calls[0]["profile_name"] == "Default"
    assert "funktional bereits erfüllt" in result
    assert "repositories" in result
    assert "nicht im angeforderten chrome" in result.lower()
    assert progress_events
    payload = progress_events[-1]["payload"]
    assert payload["kind"] == "auth_session"
    assert payload["auth_session_status"] == "authenticated"
    assert payload["auth_session_service"] == "github"
    assert payload["auth_session_browser_type"] == "firefox"


@pytest.mark.asyncio
async def test_detect_authenticated_session_state_uses_verified_vision_fallback(monkeypatch):
    agent = VisualAgent(tools_description_string="")

    async def _fake_call_tool(self, method: str, params: dict):
        if method == "get_all_screen_text":
            return {"texts": [{"text": "GitHub - Mozilla Firefox"}]}
        if method == "analyze_screen_verified":
            return {
                "filtered_elements": [
                    {"label": "Repositories", "element_type": "text", "ocr_text": "repositories"},
                    {"label": "Profile", "element_type": "text", "ocr_text": "profile"},
                    {"label": "Mozilla Firefox", "element_type": "text", "ocr_text": "mozilla firefox"},
                ]
            }
        raise AssertionError(f"unexpected tool call: {method}")

    monkeypatch.setattr(BaseAgent, "_call_tool", _fake_call_tool)

    result = await agent._detect_authenticated_session_state("github")

    assert result["success"] is True
    assert any(marker in result["positive_hits"] for marker in ("github", "repositories", "profile"))
    assert result["visible_browser"] == "firefox"


@pytest.mark.asyncio
async def test_visual_login_success_result_is_rewrapped_as_phase_d_pending_when_not_authenticated(monkeypatch):
    agent = VisualAgent(tools_description_string="")
    specialist_context = build_specialist_context_payload(
        current_topic="GitHub Login",
        active_goal="Bis zur Login-Maske navigieren und dann uebergeben",
        open_loop="Login kontrolliert vorbereiten",
        next_expected_step="Nur bis zur Login-Maske gehen",
        turn_type="new_task",
        response_mode="execute",
        user_preferences=["Login user-mediated"],
    )
    task = (
        "# DELEGATION HANDOFF\n"
        "target_agent: visual\n"
        "goal: Oeffne github.com/login und fuehre mich bis zur Login-Maske.\n"
        "expected_output: login_handoff\n"
        "success_signal: login maske sichtbar\n"
        "handoff_data:\n"
        "- source_url: https://github.com/login\n"
        "- expected_state: login_dialog\n"
        "- original_user_task: Oeffne github.com/login und fuehre mich bis zur Login-Maske.\n"
        f"- specialist_context_json: {json.dumps(specialist_context, ensure_ascii=False, sort_keys=True)}\n"
    )

    progress_events = []

    def _progress_callback(*args, **kwargs):
        if kwargs:
            progress_events.append(kwargs)
            return
        stage = args[0] if len(args) > 0 else ""
        payload = args[1] if len(args) > 1 else {}
        progress_events.append({"stage": stage, "payload": payload})

    async def _fake_detect_dynamic_ui_and_set_roi(self, task_text: str):
        return False

    async def _fake_try_structured_navigation(self, task_text: str, *, handoff=None, auth_session=None):
        return {
            "success": True,
            "result": "login_handoff — GitHub-Login-Maske ist sichtbar und bereit zur nutzergesteuerten Anmeldung.",
            "current_state": "login_modal",
        }

    async def _fake_detect_authenticated_session_state(self, service: str):
        return {
            "success": False,
            "positive_hits": [],
            "negative_hits": ["login", "password"],
            "text_preview": "login password",
        }

    monkeypatch.setattr(VisualAgent, "_detect_dynamic_ui_and_set_roi", _fake_detect_dynamic_ui_and_set_roi)
    monkeypatch.setattr(VisualAgent, "_try_structured_navigation", _fake_try_structured_navigation)
    monkeypatch.setattr(VisualAgent, "_detect_authenticated_session_state", _fake_detect_authenticated_session_state)
    setattr(agent, "_delegation_progress_callback", _progress_callback)

    result = await agent.run(task)

    assert isinstance(result, dict)
    assert result["status"] == "awaiting_user"
    assert result["service"] == "github"
    assert result["reason"] == "user_mediated_login"
    assert result["current_state"] == "login_modal"
    assert progress_events
    payload = progress_events[-1]["payload"]
    assert payload["kind"] == "blocker"
    assert payload["status"] == "awaiting_user"
    assert payload["workflow_reason"] == "user_mediated_login"


@pytest.mark.asyncio
async def test_visual_resumes_pending_login_followup_after_user_reports_success(monkeypatch):
    agent = VisualAgent(tools_description_string="")
    progress_events = []

    def _progress_callback(*args, **kwargs):
        if kwargs:
            progress_events.append(kwargs)
            return
        stage = args[0] if len(args) > 0 else ""
        payload = args[1] if len(args) > 1 else {}
        progress_events.append({"stage": stage, "payload": payload})

    async def _fake_detect_authenticated_session_state(self, service: str):
        return {
            "success": True,
            "positive_hits": ["repositories", "profile"],
            "negative_hits": [],
            "text_preview": "repositories profile",
        }

    monkeypatch.setattr(VisualAgent, "_detect_authenticated_session_state", _fake_detect_authenticated_session_state)
    setattr(agent, "_delegation_progress_callback", _progress_callback)

    task = "\n".join(
        [
            "# FOLLOW-UP CONTEXT",
            "last_agent: meta",
            "pending_workflow_id: wf_login_resume",
            "pending_workflow_status: awaiting_user",
            "pending_workflow_service: github",
            "pending_workflow_reason: user_mediated_login",
            "pending_workflow_url: https://github.com/login",
            "pending_workflow_source_agent: visual",
            "pending_workflow_reply_kind: resume_requested",
            "",
            "# CURRENT USER QUERY",
            "ich bin eingeloggt",
        ]
    )

    result = await agent.run(task)

    assert "Login bei github wirkt bestaetigt" in result
    assert "repositories" in result
    assert progress_events
    payload = progress_events[-1]["payload"]
    assert payload["kind"] == "auth_session"
    assert payload["auth_session_service"] == "github"
    assert payload["auth_session_status"] == "authenticated"
    assert payload["auth_session_reuse_ready"] is True


@pytest.mark.asyncio
async def test_visual_resumes_pending_challenge_followup_after_user_reports_resolution(monkeypatch):
    agent = VisualAgent(tools_description_string="")
    progress_events = []

    def _progress_callback(*args, **kwargs):
        if kwargs:
            progress_events.append(kwargs)
            return
        stage = args[0] if len(args) > 0 else ""
        payload = args[1] if len(args) > 1 else {}
        progress_events.append({"stage": stage, "payload": payload})

    async def _fake_detect_authenticated_session_state(self, service: str):
        return {
            "success": True,
            "positive_hits": ["repositories", "profile"],
            "negative_hits": [],
            "text_preview": "repositories profile",
        }

    monkeypatch.setattr(VisualAgent, "_detect_authenticated_session_state", _fake_detect_authenticated_session_state)
    setattr(agent, "_delegation_progress_callback", _progress_callback)

    task = "\n".join(
        [
            "# FOLLOW-UP CONTEXT",
            "last_agent: meta",
            "pending_workflow_id: wf_login_challenge",
            "pending_workflow_status: challenge_required",
            "pending_workflow_service: github",
            "pending_workflow_reason: security_challenge",
            "pending_workflow_url: https://github.com/login",
            "pending_workflow_challenge_type: 2fa",
            "pending_workflow_source_agent: visual",
            "pending_workflow_reply_kind: challenge_resolved",
            "",
            "# CURRENT USER QUERY",
            "2fa erledigt, weiter",
        ]
    )

    result = await agent.run(task)

    assert "Login bei github wirkt bestaetigt" in result
    assert progress_events
    payload = progress_events[-1]["payload"]
    assert payload["kind"] == "auth_session"
    assert payload["auth_session_service"] == "github"
    assert payload["auth_session_status"] == "authenticated"


@pytest.mark.asyncio
async def test_visual_resumes_pending_login_followup_for_visual_login_source_agent(monkeypatch):
    agent = VisualAgent(tools_description_string="")
    progress_events = []

    def _progress_callback(*args, **kwargs):
        if kwargs:
            progress_events.append(kwargs)
            return
        stage = args[0] if len(args) > 0 else ""
        payload = args[1] if len(args) > 1 else {}
        progress_events.append({"stage": stage, "payload": payload})

    async def _fake_detect_authenticated_session_state(self, service: str):
        return {
            "success": True,
            "positive_hits": ["repositories", "profile"],
            "negative_hits": [],
            "text_preview": "repositories profile",
        }

    monkeypatch.setattr(VisualAgent, "_detect_authenticated_session_state", _fake_detect_authenticated_session_state)
    setattr(agent, "_delegation_progress_callback", _progress_callback)

    task = "\n".join(
        [
            "# FOLLOW-UP CONTEXT",
            "last_agent: meta",
            "pending_workflow_id: wf_login_visual_login",
            "pending_workflow_status: awaiting_user",
            "pending_workflow_service: github",
            "pending_workflow_reason: user_action_required",
            "pending_workflow_url: https://github.com/login",
            "pending_workflow_source_agent: visual_login",
            "pending_workflow_reply_kind: resume_requested",
            "",
            "# CURRENT USER QUERY",
            "ich bin eingeloggt",
        ]
    )

    result = await agent.run(task)

    assert "Login bei github wirkt bestaetigt" in result
    assert progress_events
    payload = progress_events[-1]["payload"]
    assert payload["kind"] == "auth_session"
    assert payload["auth_session_service"] == "github"


@pytest.mark.asyncio
async def test_visual_reuses_existing_auth_session_before_new_login_flow(monkeypatch):
    agent = VisualAgent(tools_description_string="")
    progress_events = []

    def _progress_callback(*args, **kwargs):
        if kwargs:
            progress_events.append(kwargs)
            return
        stage = args[0] if len(args) > 0 else ""
        payload = args[1] if len(args) > 1 else {}
        progress_events.append({"stage": stage, "payload": payload})

    async def _fake_call_tool(self, method: str, params: dict):
        if method == "start_visual_browser":
            return {"success": True, "url": params.get("url")}
        raise AssertionError(f"unexpected tool call: {method}")

    async def _fake_detect_authenticated_session_state(self, service: str):
        return {
            "success": True,
            "positive_hits": ["profile", "sign out"],
            "negative_hits": [],
            "text_preview": "profile sign out",
        }

    async def _fake_detect_dynamic_ui_and_set_roi(self, task_text: str):
        return False

    monkeypatch.setattr(BaseAgent, "_call_tool", _fake_call_tool)
    monkeypatch.setattr(VisualAgent, "_detect_authenticated_session_state", _fake_detect_authenticated_session_state)
    monkeypatch.setattr(VisualAgent, "_detect_dynamic_ui_and_set_roi", _fake_detect_dynamic_ui_and_set_roi)
    setattr(agent, "_delegation_progress_callback", _progress_callback)

    task = (
        "# DELEGATION HANDOFF\n"
        "target_agent: visual\n"
        "goal: Oeffne github.com/login und fuehre mich bis zur Login-Maske.\n"
        "expected_output: login_handoff\n"
        "success_signal: login maske sichtbar\n"
        "handoff_data:\n"
        "- source_url: https://github.com/login\n"
        "- expected_state: login_dialog\n"
        "- auth_session_service: github\n"
        "- auth_session_status: authenticated\n"
        "- auth_session_scope: session\n"
        "- auth_session_url: https://github.com/settings/profile\n"
        "- auth_session_confirmed_at: 2026-04-09T18:00:00Z\n"
        "- auth_session_expires_at: 2026-04-11T18:00:00Z\n"
        "- original_user_task: Oeffne github.com/login und fuehre mich bis zur Login-Maske.\n"
    )

    result = await agent.run(task)

    assert "Bestehende Session bei github wiederverwendet" in result
    assert progress_events
    payload = progress_events[-1]["payload"]
    assert payload["kind"] == "auth_session"
    assert payload["auth_session_status"] == "session_reused"
    assert payload["auth_session_service"] == "github"
    assert payload["auth_session_browser_type"] == "firefox"


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
