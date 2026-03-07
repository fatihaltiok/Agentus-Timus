"""CrossHair + Hypothesis contracts for PDF builder layout helpers."""

import deal
from hypothesis import given, strategies as st


@deal.pre(lambda web, yt, trend, image, words: min(web, yt, trend, image, words) >= 0)
@deal.post(lambda r: len(r) == 5)
def build_key_metrics_contract(web: int, yt: int, trend: int, image: int, words: int) -> list[dict]:
    return [
        {"label": "Webquellen", "value": str(web)},
        {"label": "YouTube", "value": str(yt)},
        {"label": "Trendquellen", "value": str(trend)},
        {"label": "Abbildungen", "value": str(image)},
        {"label": "Woerter", "value": str(words)},
    ]


@deal.pre(lambda captions: all(isinstance(c, str) for c in captions))
@deal.post(lambda r: r >= 0)
def figure_count_contract(captions: list[str]) -> int:
    return len([caption for caption in captions if caption.strip()])


def test_metrics_contract_has_fixed_length():
    assert len(build_key_metrics_contract(1, 2, 3, 4, 5)) == 5


def test_figure_count_contract_counts_non_empty():
    assert figure_count_contract(["A", "", "B"]) == 2


@given(
    web=st.integers(min_value=0, max_value=1000),
    yt=st.integers(min_value=0, max_value=1000),
    trend=st.integers(min_value=0, max_value=1000),
    image=st.integers(min_value=0, max_value=1000),
    words=st.integers(min_value=0, max_value=100000),
)
def test_hypothesis_metrics_contract_length(web, yt, trend, image, words):
    assert len(build_key_metrics_contract(web, yt, trend, image, words)) == 5


@given(captions=st.lists(st.text(min_size=0, max_size=20), max_size=20))
def test_hypothesis_figure_count_non_negative(captions):
    assert figure_count_contract(captions) >= 0
