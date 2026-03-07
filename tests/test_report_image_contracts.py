"""CrossHair + Hypothesis contracts for creative image integration into research reports."""

import deal
from hypothesis import given, strategies as st


@deal.pre(lambda base_count, incoming_paths: base_count >= 0)
@deal.post(lambda r: r >= 0)
def merged_image_count(base_count: int, incoming_paths: list[str]) -> int:
    valid_incoming = len([p for p in incoming_paths if str(p).strip()])
    return base_count + valid_incoming


def test_merged_image_count_adds_only_non_empty_paths():
    assert merged_image_count(1, ["", "/tmp/a.png", "  "]) == 2


@given(
    base_count=st.integers(min_value=0, max_value=50),
    incoming_paths=st.lists(st.text(min_size=0, max_size=20), max_size=20),
)
def test_hypothesis_merged_image_count_nonnegative(base_count, incoming_paths):
    assert merged_image_count(base_count, incoming_paths) >= base_count
