"""CrossHair + Hypothesis contracts for research orchestration fixes."""

import deal
from hypothesis import given, strategies as st


@deal.post(lambda r: isinstance(r, dict))
def effective_report_params(params: dict, current_session_id: str) -> dict:
    result = dict(params or {})
    if current_session_id:
        result.setdefault("session_id", current_session_id)
    return result


@deal.post(lambda r: r > 0)
def youtube_location_code(language_code: str) -> int:
    mapping = {
        "de": 2276,
        "en": 2840,
        "fr": 2250,
        "es": 2724,
        "it": 2380,
    }
    return mapping.get((language_code or "").strip().lower(), 2276)


@deal.pre(lambda keys: isinstance(keys, list) and any(str(key).strip() for key in keys))
@deal.post(lambda r: isinstance(r, list) and len(r) > 0)
def normalize_hotkey_keys(keys: list[str]) -> list[str]:
    normalized = [str(key).strip().lower() for key in keys if str(key).strip()]
    if not normalized:
        raise ValueError("keys enthaelt keine gueltigen Tasten.")
    return normalized


def test_report_params_use_current_session_when_missing():
    result = effective_report_params({"format": "pdf"}, "sess-1")
    assert result["session_id"] == "sess-1"


def test_report_params_preserve_explicit_session():
    result = effective_report_params({"format": "pdf", "session_id": "sess-explicit"}, "sess-1")
    assert result["session_id"] == "sess-explicit"


def test_youtube_location_code_defaults_to_germany():
    assert youtube_location_code("") == 2276


def test_hotkey_normalization_lowercases_and_filters():
    assert normalize_hotkey_keys([" CTRL ", "", "L"]) == ["ctrl", "l"]


@given(
    params=st.dictionaries(
        keys=st.sampled_from(["format", "session_id"]),
        values=st.text(min_size=1, max_size=20),
        max_size=2,
    ),
    current_session_id=st.text(min_size=0, max_size=20),
)
def test_hypothesis_report_params_priority(params: dict, current_session_id: str):
    result = effective_report_params(params, current_session_id)
    if "session_id" in params:
        assert result["session_id"] == params["session_id"]
    elif current_session_id:
        assert result["session_id"] == current_session_id
    else:
        assert "session_id" not in result


@given(language_code=st.text(min_size=0, max_size=5))
def test_hypothesis_location_code_positive(language_code: str):
    assert youtube_location_code(language_code) > 0


@given(keys=st.lists(st.text(min_size=0, max_size=5), min_size=1, max_size=5))
def test_hypothesis_hotkey_normalization_nonempty_or_raises(keys: list[str]):
    if any(str(key).strip() for key in keys):
        assert len(normalize_hotkey_keys(keys)) > 0
