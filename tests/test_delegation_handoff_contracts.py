from __future__ import annotations

import deal

from agent.shared.delegation_handoff import parse_delegation_handoff


@deal.post(lambda r: r is None or isinstance(r.handoff_data, dict))
@deal.post(lambda r: r is None or isinstance(r.constraints, list))
def _contract_parse_delegation_handoff(task: str):
    return parse_delegation_handoff(task)


def test_parse_delegation_handoff_returns_none_for_plain_text():
    assert _contract_parse_delegation_handoff("Analysiere diese Quelle") is None


def test_parse_delegation_handoff_keeps_structured_lists():
    result = _contract_parse_delegation_handoff(
        "# DELEGATION HANDOFF\n"
        "target_agent: research\n"
        "goal: Analysiere die Quelle\n"
        "constraints:\n"
        "- high_confidence=true\n"
        "handoff_data:\n"
        "- source_urls: https://example.com\n"
    )

    assert result is not None
    assert result.constraints == ["high_confidence=true"]
    assert result.handoff_data["source_urls"] == "https://example.com"
