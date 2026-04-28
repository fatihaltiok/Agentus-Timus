from orchestration.direct_response_intent import (
    extract_requested_direct_response,
    looks_like_direct_response_instruction,
)


def test_direct_response_intent_detects_exact_output_requests():
    assert looks_like_direct_response_instruction("Antworte exakt nur mit CHAT_OK")
    assert looks_like_direct_response_instruction("führe aus: antworte exakt nur mit KIMI_CHAT_OK")
    assert extract_requested_direct_response("gib exakt OK zurück") == "OK"


def test_direct_response_intent_does_not_capture_behavior_preferences():
    assert not looks_like_direct_response_instruction("antworte mir ab jetzt weniger formal")
    assert not looks_like_direct_response_instruction("speichere dir dass ich kurze antworten bevorzuge")


def test_direct_response_intent_does_not_capture_shell_execution():
    assert not looks_like_direct_response_instruction("führe aus: systemctl restart timus-mcp")
    assert not looks_like_direct_response_instruction("führe aus: pip install numpy")
