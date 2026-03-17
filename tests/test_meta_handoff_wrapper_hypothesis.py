from __future__ import annotations

from hypothesis import given, strategies as st

from tests.test_meta_handoff_wrapper_contracts import _contract_strip_meta_canvas_wrappers


@given(st.text(min_size=0, max_size=200))
def test_hypothesis_strip_meta_canvas_wrappers_returns_string(query: str) -> None:
    result = _contract_strip_meta_canvas_wrappers(query)
    assert isinstance(result, str)


@given(st.text(min_size=1, max_size=80))
def test_hypothesis_strip_meta_canvas_wrappers_preserves_plain_query(query: str) -> None:
    result = _contract_strip_meta_canvas_wrappers(query)
    if "# LIVE LOCATION CONTEXT" not in query and "Nutzeranfrage:" not in query:
        assert result == query.strip()
