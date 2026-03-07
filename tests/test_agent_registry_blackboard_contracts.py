"""CrossHair-compatible contracts for delegation blackboard TTL mapping."""

import deal
import pytest
from hypothesis import given, strategies as st

from agent.agent_registry import AgentRegistry


@deal.post(lambda r: r >= 1, message="TTL must stay positive")
def ttl_for_status(status: str) -> int:
    return AgentRegistry._delegation_blackboard_ttl(status)


class TestDelegationBlackboardTTLContracts:

    def test_known_statuses_match_expected_values(self):
        assert ttl_for_status("success") == 120
        assert ttl_for_status("partial") == 60
        assert ttl_for_status("error") == 30

    def test_unknown_status_uses_default(self):
        assert ttl_for_status("anything-else") == 60

    @given(st.text(min_size=1, max_size=40))
    def test_hypothesis_ttl_always_positive(self, status):
        assert ttl_for_status(status) >= 1

    def test_contract_never_returns_non_positive(self):
        with pytest.raises(AssertionError):
            assert ttl_for_status("success") <= 0
