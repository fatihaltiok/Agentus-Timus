from __future__ import annotations

import deal
from hypothesis import given, settings
from hypothesis import strategies as st

from agent.base_agent import BaseAgent


@deal.post(lambda r: isinstance(r, bool))
def retryable_provider_error_contract(text: str) -> bool:
    return BaseAgent._is_retryable_provider_error_text(text)


def test_known_retryable_provider_errors_are_true():
    assert retryable_provider_error_contract("connection error to deepseek") is True
    assert retryable_provider_error_contract("504 gateway timeout from provider") is True
    assert retryable_provider_error_contract("temporary failure in name resolution") is True


def test_non_retryable_provider_error_text_can_be_false():
    assert retryable_provider_error_contract("invalid api key") is False


@given(st.text(min_size=0, max_size=80))
@settings(max_examples=200)
def test_hypothesis_retryable_provider_error_contract_returns_bool(text: str):
    result = retryable_provider_error_contract(text)
    assert isinstance(result, bool)
