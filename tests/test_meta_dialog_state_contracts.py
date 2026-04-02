from __future__ import annotations

import deal
from hypothesis import given, settings
from hypothesis import strategies as st

from orchestration.meta_orchestration import extract_meta_dialog_state


@deal.post(lambda r: isinstance(r, dict))
@deal.post(lambda r: isinstance(r.get("active_topic"), (str, type(None))))
@deal.post(lambda r: isinstance(r.get("open_goal"), (str, type(None))))
@deal.post(lambda r: isinstance(r.get("constraints"), list))
@deal.post(lambda r: all(isinstance(item, str) for item in r.get("constraints", [])))
@deal.post(lambda r: isinstance(r.get("next_step"), (str, type(None))))
@deal.post(lambda r: isinstance(r.get("compressed_followup_parsed"), bool))
@deal.post(lambda r: isinstance(r.get("active_topic_reused"), bool))
def _contract_meta_dialog_state(query: str) -> dict:
    return extract_meta_dialog_state(query)


@given(st.text(max_size=260))
@settings(max_examples=80)
def test_hypothesis_meta_dialog_state_shape(query: str):
    result = _contract_meta_dialog_state(query)
    if result["active_topic_reused"]:
        assert result["active_topic"]
