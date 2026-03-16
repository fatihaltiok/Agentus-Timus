from __future__ import annotations

import deal

from utils.location_chat_context import (
    build_location_chat_context_block,
    evaluate_location_chat_context,
    is_location_context_query,
)


@deal.post(lambda r: isinstance(r, bool))
def _contract_is_location_context_query(query: str) -> bool:
    return is_location_context_query(query)


@deal.post(lambda r: isinstance(r.should_inject, bool))
@deal.post(lambda r: r.presence_status in {"live", "recent", "stale", "unknown"})
@deal.ensure(lambda query, snapshot, enabled, result: (enabled is False) or (result.should_inject is False) or (_contract_is_location_context_query(query) is True))
def _contract_evaluate_location_chat_context(
    query: str,
    snapshot: dict | None,
    enabled: bool,
):
    return evaluate_location_chat_context(query=query, snapshot=snapshot, enabled=enabled)


@deal.post(lambda r: "# LIVE LOCATION CONTEXT" in r)
@deal.post(lambda r: "presence_status:" in r)
def _contract_build_location_chat_context_block(snapshot: dict) -> str:
    return build_location_chat_context_block(snapshot)


def test_contract_evaluate_location_chat_context_blocks_irrelevant_queries() -> None:
    result = _contract_evaluate_location_chat_context(
        "Erzähl mir einen Witz",
        {"presence_status": "live", "usable_for_context": True, "has_coordinates": True},
        True,
    )
    assert result.should_inject is False


def test_contract_build_location_chat_context_block_minimal_snapshot() -> None:
    block = _contract_build_location_chat_context_block({"presence_status": "recent"})
    assert "presence_status: recent" in block
