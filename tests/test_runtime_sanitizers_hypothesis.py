from hypothesis import given, strategies as st

from memory.markdown_store.query_utils import build_safe_fts_query
from utils.resend_email import _sanitize_subject


@given(st.text())
def test_hypothesis_sanitize_subject_removes_newlines(subject: str):
    sanitized = _sanitize_subject(subject)
    assert "\n" not in sanitized
    assert "\r" not in sanitized
    assert sanitized


@given(st.text())
def test_hypothesis_build_fts_query_stays_single_line(query: str):
    normalized = build_safe_fts_query(query)
    assert "\n" not in normalized
    assert "\r" not in normalized
