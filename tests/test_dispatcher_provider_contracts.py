"""CrossHair + Hypothesis Contracts fuer Dispatcher-Provider-Auswahl."""

from __future__ import annotations

import deal
from hypothesis import given, settings
from hypothesis import strategies as st

import main_dispatcher
from agent.providers import ModelProvider

_VALID_PROVIDER_VALUES = {provider.value for provider in ModelProvider}


@deal.post(lambda r: r in _VALID_PROVIDER_VALUES)
def normalize_dispatcher_provider_contract(raw: str) -> str:
    """Normalisierung liefert immer einen gueltigen Provider-Key."""
    return main_dispatcher._normalize_dispatcher_provider(raw).value


@deal.pre(lambda provider: provider in _VALID_PROVIDER_VALUES)
@deal.post(lambda r: isinstance(r, bool))
def dispatcher_provider_supports_native_contract(provider: str) -> bool:
    """Dispatcher-Support-Antwort ist fuer gueltige Provider immer boolesch."""
    return main_dispatcher._dispatcher_provider_supports_native_call(ModelProvider(provider))


def test_contract_invalid_provider_falls_back_to_openai():
    assert normalize_dispatcher_provider_contract("not-real") == ModelProvider.OPENAI.value


def test_contract_openrouter_roundtrips():
    assert normalize_dispatcher_provider_contract("openrouter") == ModelProvider.OPENROUTER.value


def test_contract_google_is_supported_natively():
    assert dispatcher_provider_supports_native_contract(ModelProvider.GOOGLE.value) is True


def test_contract_dashscope_is_supported_natively():
    assert dispatcher_provider_supports_native_contract(ModelProvider.DASHSCOPE.value) is True


def test_contract_dashscope_native_is_supported_natively():
    assert dispatcher_provider_supports_native_contract(ModelProvider.DASHSCOPE_NATIVE.value) is True


@given(st.text(min_size=0, max_size=30))
@settings(max_examples=200)
def test_hypothesis_normalized_dispatcher_provider_always_valid(raw: str):
    assert normalize_dispatcher_provider_contract(raw) in _VALID_PROVIDER_VALUES


@given(st.sampled_from(sorted(_VALID_PROVIDER_VALUES)))
@settings(max_examples=50)
def test_hypothesis_valid_provider_names_are_idempotent(raw: str):
    assert normalize_dispatcher_provider_contract(raw) == raw


@given(st.sampled_from(sorted(_VALID_PROVIDER_VALUES)))
@settings(max_examples=50)
def test_hypothesis_support_contract_returns_bool(provider: str):
    result = dispatcher_provider_supports_native_contract(provider)
    assert isinstance(result, bool)


@given(st.sampled_from([
    ModelProvider.OPENAI.value,
    ModelProvider.OPENROUTER.value,
    ModelProvider.DEEPSEEK.value,
    ModelProvider.INCEPTION.value,
    ModelProvider.NVIDIA.value,
    ModelProvider.DASHSCOPE.value,
    ModelProvider.DASHSCOPE_NATIVE.value,
    ModelProvider.ANTHROPIC.value,
    ModelProvider.GOOGLE.value,
]))
@settings(max_examples=20)
def test_hypothesis_supported_dispatcher_providers_stay_supported(provider: str):
    assert dispatcher_provider_supports_native_contract(provider) is True
