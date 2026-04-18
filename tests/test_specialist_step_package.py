import json

from orchestration.specialist_context import build_specialist_context_payload
from orchestration.specialist_step_package import (
    build_specialist_step_package_payload,
    format_specialist_step_signal_response,
    parse_specialist_step_package_payload,
    parse_specialist_step_signal_response,
    render_specialist_step_package_block,
)


def test_specialist_step_package_roundtrip_keeps_step_focus():
    payload = build_specialist_step_package_payload(
        plan_summary={
            "plan_id": "plan_z4",
            "plan_mode": "multi_step_execution",
            "goal": "Twilio-Anruffunktion mit Lennart einrichten",
            "goal_satisfaction_mode": "goal_satisfied",
        },
        plan_step={
            "id": "twilio_voice_bridge",
            "title": "Twilio mit Inworld-TTS verdrahten",
            "step_kind": "execution",
            "assigned_agent": "developer",
            "delegation_mode": "recipe_stage",
            "expected_output": "laufender Call-Flow",
            "completion_signals": ["bridge_connected", "call_ready"],
            "depends_on": ["verify_numbers"],
        },
        specialist_context=build_specialist_context_payload(
            current_topic="Twilio Voice",
            active_goal="Anruffunktion produktiv schalten",
            open_loop="Bridge und Trigger verbinden",
            next_expected_step="Twilio mit Inworld-TTS verdrahten",
            turn_type="followup",
            response_mode="execute",
        ),
        original_user_task="Richte eine Anruffunktion mit Lennart ein.",
        previous_stage_result="Credentials und Vorarbeit bestaetigt",
        captured_context="Twilio-Testskript und Inworld-TTS vorhanden",
        source_urls=["https://api.inworld.ai", "https://api.twilio.com"],
    )

    parsed = parse_specialist_step_package_payload(json.dumps(payload, ensure_ascii=False))

    assert parsed["plan_id"] == "plan_z4"
    assert parsed["step_id"] == "twilio_voice_bridge"
    assert parsed["step_title"] == "Twilio mit Inworld-TTS verdrahten"
    assert parsed["focus_context"]["previous_stage_result"] == "Credentials und Vorarbeit bestaetigt"
    assert parsed["return_signal_contract"] == [
        "step_completed",
        "step_blocked",
        "step_unnecessary",
        "goal_satisfied",
    ]


def test_render_specialist_step_package_block_includes_signal_protocol():
    payload = build_specialist_step_package_payload(
        plan_summary={"plan_id": "plan_1", "goal": "Setup abschliessen"},
        plan_step={"id": "step_1", "title": "Login pruefen", "expected_output": "login_state"},
        specialist_context=build_specialist_context_payload(
            active_goal="Setup abschliessen",
            next_expected_step="Login pruefen",
        ),
        previous_stage_result="Domain bereits aufgeloest",
    )

    block = render_specialist_step_package_block(payload)

    assert "# ARBEITSSCHRITT-PAKET" in block
    assert "Aktueller Arbeitsschritt: Login pruefen" in block
    assert "Vorheriges Schritt-Ergebnis: Domain bereits aufgeloest" in block
    assert "Specialist Step Signal: step_completed" in block


def test_specialist_step_signal_response_roundtrip():
    response = format_specialist_step_signal_response(
        "step_blocked",
        reason="missing_credentials",
        message="Twilio-Nummer fehlt noch.",
    )

    parsed = parse_specialist_step_signal_response(response)

    assert parsed["signal"] == "step_blocked"
    assert parsed["reason"] == "missing_credentials"
    assert parsed["message"] == "Twilio-Nummer fehlt noch."
