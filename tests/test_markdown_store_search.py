from pathlib import Path

from memory.markdown_store.query_utils import build_safe_fts_query
from memory.markdown_store.store import HybridSearchIndex


def test_build_fts_query_strips_unsafe_punctuation(tmp_path: Path):
    query = build_safe_fts_query("foo/bar baz://qux")

    assert query == '"foo"* OR "bar"* OR "baz"* OR "qux"*'


def test_search_with_slashes_does_not_raise_and_can_match(tmp_path: Path):
    index = HybridSearchIndex(tmp_path / "fts.db")
    index.index_document("memory", "Test", "foo bar baz")

    results = index.search("foo/bar")

    assert results
    assert results[0].source == "memory"
