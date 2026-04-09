import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def test_assess_specialist_context_alignment_detects_needs_meta_reframe():
    from orchestration.specialist_context import (
        assess_specialist_context_alignment,
        build_specialist_context_payload,
    )

    payload = build_specialist_context_payload(
        current_topic="Weltlage und News-Qualitaet",
        active_goal="Agenturmeldungen priorisieren",
        open_loop="Weltlage-Follow-up fortsetzen",
        turn_type="followup",
        response_mode="resume_open_loop",
    )

    result = assess_specialist_context_alignment(
        current_task="Pruefe den Zustand von timus-mcp und gib eine Diagnose.",
        payload=payload,
    )

    assert result["alignment_state"] == "needs_meta_reframe"
    assert result["reason"] == "followup_without_shared_anchor"


@pytest.mark.asyncio
async def test_agent_registry_attaches_specialist_return_signal_and_transport_event(monkeypatch):
    from agent.agent_registry import AgentRegistry
    import agent.agent_registry as agent_registry_mod
    from orchestration.specialist_context import build_specialist_context_payload

    registry = AgentRegistry()

    async def _fake_tools():
        return "tools"

    registry._get_tools_description = _fake_tools
    emitted: list[dict] = []
    monkeypatch.setattr(agent_registry_mod, "_delegation_transport_hook", lambda payload: emitted.append(payload))

    class _SystemAgent:
        conversation_session_id = None

        async def run(self, task: str) -> str:
            return "Dienst laeuft, aber der Kontext passt nicht zur eigentlichen Nutzerabsicht."

    registry.register_spec(
        "system",
        "system",
        ["diagnostics"],
        lambda tools_description_string: _SystemAgent(),
    )

    specialist_context = build_specialist_context_payload(
        current_topic="Weltlage und News-Qualitaet",
        active_goal="Agenturmeldungen priorisieren",
        open_loop="Weltlage-Follow-up fortsetzen",
        turn_type="followup",
        response_mode="resume_open_loop",
    )
    task = "\n".join(
        [
            "# DELEGATION HANDOFF",
            "target_agent: system",
            "goal: Pruefe den Zustand von timus-mcp und gib eine Diagnose.",
            "expected_output: strukturierter Output",
            "success_signal: Zielzustand bestaetigt",
            "handoff_data:",
            "- original_user_task: Pruefe den Zustand von timus-mcp und gib eine Diagnose.",
            f"- specialist_context_json: {json.dumps(specialist_context, ensure_ascii=False, sort_keys=True)}",
        ]
    )

    result = await registry.delegate(
        from_agent="meta",
        to_agent="system",
        task=task,
        session_id="d09_context_signal",
    )

    assert result["status"] == "success"
    assert result["metadata"]["specialist_return_signal"] == "needs_meta_reframe"
    assert result["metadata"]["specialist_context_alignment"]["alignment_state"] == "needs_meta_reframe"
    assert any(event.get("kind") == "needs_meta_reframe" for event in emitted)
    signal = next(event for event in emitted if event.get("kind") == "needs_meta_reframe")
    assert signal["stage"] == "delegation_needs_meta_reframe"


def test_specialist_signal_response_roundtrip():
    from orchestration.specialist_context import (
        format_specialist_signal_response,
        parse_specialist_signal_response,
    )

    response = format_specialist_signal_response(
        "needs_meta_reframe",
        reason="followup_without_shared_anchor",
        message="Meta sollte die Anfrage zuerst neu rahmen.",
    )
    parsed = parse_specialist_signal_response(response)

    assert parsed["signal"] == "needs_meta_reframe"
    assert parsed["reason"] == "followup_without_shared_anchor"
    assert "neu rahmen" in parsed["message"]


@pytest.mark.asyncio
async def test_agent_registry_treats_explicit_specialist_signal_as_partial(monkeypatch):
    from agent.agent_registry import AgentRegistry
    from orchestration.specialist_context import format_specialist_signal_response

    registry = AgentRegistry()

    async def _fake_tools():
        return "tools"

    registry._get_tools_description = _fake_tools

    class _ResearchAgent:
        conversation_session_id = None

        async def run(self, task: str) -> str:
            return format_specialist_signal_response(
                "needs_meta_reframe",
                reason="followup_without_shared_anchor",
                message="Meta sollte den Recherchefokus zuerst neu rahmen.",
            )

    registry.register_spec(
        "research",
        "research",
        ["research"],
        lambda tools_description_string: _ResearchAgent(),
    )

    result = await registry.delegate(
        from_agent="meta",
        to_agent="research",
        task="bitte pruefen",
        session_id="d09_explicit_signal",
    )

    assert result["status"] == "partial"
    assert result["metadata"]["specialist_return_signal"] == "needs_meta_reframe"
    assert result["metadata"]["specialist_signal_source"] == "agent"
    assert "Recherchefokus" in result["result"]


@pytest.mark.asyncio
async def test_agent_registry_emits_email_observation_events_for_communication_success(monkeypatch):
    from agent.agent_registry import AgentRegistry
    import agent.agent_registry as agent_registry_mod
    from orchestration.request_correlation import bind_request_correlation

    registry = AgentRegistry()

    async def _fake_tools():
        return "tools"

    registry._get_tools_description = _fake_tools
    observed: list[tuple[str, dict]] = []
    monkeypatch.setattr(
        agent_registry_mod,
        "record_autonomy_observation",
        lambda event, payload: observed.append((event, dict(payload))),
    )

    class _CommunicationAgent:
        conversation_session_id = None

        async def run(self, task: str):
            return {
                "status": "success",
                "success": True,
                "to": "fatihaltiok@outlook.com",
                "subject": "Timus README.md",
                "backend": "resend",
                "attachment": "README.md",
            }

    registry.register_spec(
        "communication",
        "communication",
        ["communication", "email"],
        lambda tools_description_string: _CommunicationAgent(),
    )

    task = "\n".join(
        [
            "# DELEGATION HANDOFF",
            "target_agent: communication",
            "goal: Sende die README.md per E-Mail an den Nutzer.",
            "expected_output: E-Mail erfolgreich versendet",
            "success_signal: send_email returns success",
            "handoff_data:",
            "- recipient: fatihaltiok@outlook.com",
            "- subject_hint: Timus README.md",
            "- attachment_path: /home/fatih-ubuntu/dev/timus/README.md",
        ]
    )

    with bind_request_correlation(request_id="req_mail_1", session_id="tg_mail_demo"):
        result = await registry.delegate(
            from_agent="meta",
            to_agent="communication",
            task=task,
            session_id="tg_mail_demo",
        )

    assert result["status"] == "success"
    event_names = [name for name, _payload in observed]
    assert "communication_task_started" in event_names
    assert "communication_task_completed" in event_names
    assert "send_email_succeeded" in event_names
    success_payload = next(payload for name, payload in observed if name == "send_email_succeeded")
    assert success_payload["request_id"] == "req_mail_1"
    assert success_payload["session_id"] == "tg_mail_demo"
    assert success_payload["source"] == "telegram_chat"
    assert success_payload["backend"] == "resend"
    assert success_payload["recipient"] == "fatihaltiok@outlook.com"
