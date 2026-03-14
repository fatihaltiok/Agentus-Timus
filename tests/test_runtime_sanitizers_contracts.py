import deal

from utils.resend_email import _sanitize_subject
from memory.markdown_store.query_utils import build_safe_fts_query


@deal.post(lambda result: result is True)
def _contract_sanitize_subject(subject: str) -> bool:
    sanitized = _sanitize_subject(subject)
    return ("\n" not in sanitized) and ("\r" not in sanitized) and bool(sanitized)


@deal.post(lambda result: result is True)
def _contract_build_fts_query(query: str) -> bool:
    normalized = build_safe_fts_query(query)
    return ("\n" not in normalized) and ("\r" not in normalized)


def test_contract_sanitize_subject_examples():
    assert _contract_sanitize_subject("foo\nbar")
    assert _contract_sanitize_subject("")


def test_contract_build_fts_query_examples():
    assert _contract_build_fts_query("foo/bar")
    assert _contract_build_fts_query("")
