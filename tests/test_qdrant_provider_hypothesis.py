from hypothesis import given, strategies as st

from memory.qdrant_provider import (
    normalize_qdrant_mode,
    resolve_qdrant_ready_url,
    resolve_qdrant_url,
)


@given(st.one_of(st.none(), st.text()))
def test_hypothesis_normalize_qdrant_mode_returns_known_value(raw_mode):
    assert normalize_qdrant_mode(raw_mode) in {"embedded", "server"}


@given(st.one_of(st.none(), st.text()))
def test_hypothesis_resolve_qdrant_url_is_httpish(raw_url):
    resolved = resolve_qdrant_url(raw_url)
    assert resolved.startswith(("http://", "https://"))


@given(st.one_of(st.none(), st.text()))
def test_hypothesis_resolve_qdrant_ready_url_has_suffix(raw_url):
    resolved = resolve_qdrant_ready_url(raw_url)
    assert resolved.startswith(("http://", "https://"))
    assert resolved.endswith("/readyz")
