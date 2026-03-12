import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent import providers as providers_mod
from agent.agents.communication import CommunicationAgent
from agent.agents.document import DocumentAgent
from agent.agents.research import DeepResearchAgent
from agent.agents.shell import ShellAgent
from agent.agents.system import SystemAgent
from agent.agents.visual import VisualAgent
from agent.base_agent import BaseAgent
from agent.shared.delegation_handoff import parse_delegation_handoff


@pytest.fixture(autouse=True)
def _disable_model_validation(monkeypatch):
    monkeypatch.setenv("TIMUS_VALIDATE_CONFIGURED_MODELS", "false")
    providers_mod._provider_client = None
    yield
    providers_mod._provider_client = None


def _sample_handoff() -> str:
    return """# DELEGATION HANDOFF
target_agent: visual
goal: Oeffne die YouTube-Seite und erreiche die Videoseite.
expected_output: source_url, page_state, page_title, captured_context
success_signal: Zielzustand bestaetigt
constraints:
- recipe_stage=visual_access
- site_kind=youtube
handoff_data:
- recipe_id: youtube_content_extraction
- stage_id: visual_access
- expected_state: video_page
- source_url: https://www.youtube.com/watch?v=abc123
- previous_stage_result: Suchergebnisse fuer Modellvergleich
- previous_blackboard_key: bb-meta-42
"""


def _handoff_for(agent: str, goal: str, extra: str = "") -> str:
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


def test_visual_prepare_task_uses_goal_and_handoff_state():
    agent = VisualAgent(tools_description_string="")

    effective_task, context = agent._prepare_visual_task(_sample_handoff())

    assert effective_task == "Oeffne die YouTube-Seite und erreiche die Videoseite."
    assert "expected_state=video_page" in context
    assert "recipe_id=youtube_content_extraction" in context
    assert "previous_stage_result=Suchergebnisse fuer Modellvergleich" in context
    assert agent.current_browser_url == "https://www.youtube.com/watch?v=abc123"


@pytest.mark.asyncio
async def test_research_run_uses_structured_handoff_context(monkeypatch):
    captured = {}

    async def _fake_context(self, task: str) -> str:
        captured["effective_task"] = task
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
"""

    monkeypatch.setattr(DeepResearchAgent, "_build_research_context", _fake_context)
    monkeypatch.setattr(BaseAgent, "run", _fake_super_run)

    agent = DeepResearchAgent(tools_description_string="")
    try:
        result = await agent.run(handoff_task)
    finally:
        await agent.http_client.aclose()

    assert result == "ok"
    assert captured["effective_task"] == "Analysiere das YouTube-Video und extrahiere die Hauptthesen."
    assert captured["enriched_task"].startswith("Analysiere das YouTube-Video")
    assert "# STRUKTURIERTER RESEARCH-HANDOFF" in captured["enriched_task"]
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
async def test_system_run_uses_structured_handoff(monkeypatch):
    captured = {}

    async def _fake_snapshot(self) -> str:
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
    assert "Service: timus-mcp" in captured["task"]
    assert "Erwarteter Zustand: active" in captured["task"]


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
