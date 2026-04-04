from tools.screen_contract_tool.tool import _normalize_ocr_text_lines
from tools.verified_vision_tool.tool import (
    _normalize_target_elements,
    _parse_json_like_payload,
    _stringify_model_payload,
)


def test_parse_json_like_payload_unwraps_engine_raw_response_dict():
    payload = {
        "success": True,
        "actions": [],
        "raw_response": '[{"type":"button","label":"Submit","confidence":0.9}]',
        "error": None,
    }

    parsed = _parse_json_like_payload(payload)

    assert isinstance(parsed, list)
    assert parsed[0]["label"] == "Submit"


def test_parse_json_like_payload_accepts_markdown_wrapped_json():
    payload = "```json\n[{\"element_type\":\"button\",\"label\":\"OK\"}]\n```"

    parsed = _parse_json_like_payload(payload)

    assert parsed == [{"element_type": "button", "label": "OK"}]


def test_stringify_model_payload_prefers_raw_response_text():
    payload = {
        "success": True,
        "raw_response": '[{"type":"button","label":"Weiter"}]',
        "actions": [{"action": "click", "x": 10, "y": 20}],
    }

    text = _stringify_model_payload(payload)

    assert "Weiter" in text
    assert "click" not in text


def test_normalize_ocr_text_lines_accepts_dict_entries():
    texts = [
        {"text": "Google Calendar", "x": 10, "y": 20},
        {"label": "Heute"},
        "Termine",
    ]

    normalized = _normalize_ocr_text_lines(texts)

    assert normalized == ["Google Calendar", "Heute", "Termine"]


def test_normalize_ocr_text_lines_handles_scalar_and_empty_values():
    assert _normalize_ocr_text_lines(None) == []
    assert _normalize_ocr_text_lines("Eintrag") == ["Eintrag"]


def test_normalize_target_elements_accepts_dict_specs():
    target_elements = [
        {"type": "panel", "label": "CHAT"},
        {"type": "text", "text": "Schritte in der Google Cloud Console"},
        "button",
    ]

    normalized = _normalize_target_elements(target_elements)

    assert normalized == [
        "panel CHAT",
        "text Schritte in der Google Cloud Console",
        "button",
    ]
