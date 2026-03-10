from __future__ import annotations

import deal
from hypothesis import given, settings
from hypothesis import strategies as st

from utils.headless_service_guard import is_protected_runtime_artifact


@deal.post(lambda r: isinstance(r, bool))
def _contract_is_protected_runtime_artifact(path: str) -> bool:
    return is_protected_runtime_artifact(path)


@given(st.text(min_size=0, max_size=120))
@settings(max_examples=80)
def test_hypothesis_protected_runtime_artifact_returns_bool(path: str) -> None:
    result = _contract_is_protected_runtime_artifact(path)
    assert isinstance(result, bool)
