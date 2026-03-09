"""CrossHair + Hypothesis contracts for stable non-security fingerprints."""

import deal
from hypothesis import given, settings
from hypothesis import strategies as st

from utils.stable_hash import stable_hex_digest, stable_text_digest


@deal.pre(lambda payload, hex_chars: hex_chars >= 1)
@deal.post(lambda r: isinstance(r, str) and len(r) >= 1)
def _contract_stable_hex_digest(payload: bytes, hex_chars: int) -> str:
    return stable_hex_digest(payload, hex_chars=hex_chars)


@deal.pre(lambda text, hex_chars: hex_chars >= 1)
@deal.post(lambda r: isinstance(r, str) and len(r) >= 1)
def _contract_stable_text_digest(text: str, hex_chars: int) -> str:
    return stable_text_digest(text, hex_chars=hex_chars)


@given(st.binary(max_size=128), st.integers(min_value=1, max_value=32))
@settings(max_examples=80)
def test_hypothesis_stable_hex_digest_has_requested_length(payload: bytes, hex_chars: int):
    digest = _contract_stable_hex_digest(payload, hex_chars)
    assert len(digest) == hex_chars


@given(st.text(max_size=128), st.integers(min_value=1, max_value=32))
@settings(max_examples=80)
def test_hypothesis_stable_text_digest_has_requested_length(text: str, hex_chars: int):
    digest = _contract_stable_text_digest(text, hex_chars)
    assert len(digest) == hex_chars
