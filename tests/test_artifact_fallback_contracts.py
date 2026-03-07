"""CrossHair + Hypothesis contracts for artifact fallback order."""

import deal
from hypothesis import given, strategies as st


@deal.pre(lambda artifacts_count, *_: artifacts_count >= 0)
@deal.post(lambda r: r in {"artifacts", "metadata", "regex", "none"})
def choose_artifact_source(
    artifacts_count: int,
    has_metadata_artifact: bool,
    has_regex_artifact: bool,
) -> str:
    """Models the enforced fallback policy in the delegation path."""
    if artifacts_count > 0:
        return "artifacts"
    if has_metadata_artifact:
        return "metadata"
    if has_regex_artifact:
        return "regex"
    return "none"


def test_artifacts_have_priority():
    assert choose_artifact_source(1, True, True) == "artifacts"


def test_metadata_beats_regex_when_no_artifacts():
    assert choose_artifact_source(0, True, True) == "metadata"


def test_regex_used_only_when_others_missing():
    assert choose_artifact_source(0, False, True) == "regex"


def test_none_when_nothing_available():
    assert choose_artifact_source(0, False, False) == "none"


@given(
    artifacts_count=st.integers(min_value=0, max_value=10),
    has_metadata_artifact=st.booleans(),
    has_regex_artifact=st.booleans(),
)
def test_hypothesis_fallback_order(
    artifacts_count: int,
    has_metadata_artifact: bool,
    has_regex_artifact: bool,
):
    choice = choose_artifact_source(
        artifacts_count,
        has_metadata_artifact,
        has_regex_artifact,
    )
    if artifacts_count > 0:
        assert choice == "artifacts"
    elif has_metadata_artifact:
        assert choice == "metadata"
    elif has_regex_artifact:
        assert choice == "regex"
    else:
        assert choice == "none"
