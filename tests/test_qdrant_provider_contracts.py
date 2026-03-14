import deal

from memory.qdrant_provider import (
    normalize_qdrant_mode,
    resolve_qdrant_ready_url,
    resolve_qdrant_url,
)


@deal.post(lambda r: r in {"embedded", "server"})
def _contract_normalize_qdrant_mode(raw_mode: str | None) -> str:
    return normalize_qdrant_mode(raw_mode)


@deal.post(lambda r: r.startswith(("http://", "https://")))
def _contract_resolve_qdrant_url(raw_url: str | None) -> str:
    return resolve_qdrant_url(raw_url)


@deal.post(lambda r: r.endswith("/readyz"))
@deal.post(lambda r: r.startswith(("http://", "https://")))
def _contract_resolve_qdrant_ready_url(raw_url: str | None) -> str:
    return resolve_qdrant_ready_url(raw_url)


def test_contract_normalize_qdrant_mode_examples():
    assert _contract_normalize_qdrant_mode("")
    assert _contract_normalize_qdrant_mode("server")


def test_contract_resolve_qdrant_url_examples():
    assert _contract_resolve_qdrant_url("")
    assert _contract_resolve_qdrant_url("https://qdrant.internal")


def test_contract_resolve_qdrant_ready_url_examples():
    assert _contract_resolve_qdrant_ready_url("")
    assert _contract_resolve_qdrant_ready_url("https://qdrant.internal")
