"""CrossHair + Hypothesis contracts for strict HTTP health checks."""

import deal
from hypothesis import given, settings
from hypothesis import strategies as st


@deal.pre(lambda url: url.startswith(("http://", "https://")))
@deal.post(lambda r: r["scheme"] in {"http", "https"} and r["path"].startswith("/"))
def _contract_normalize_http_target(url: str) -> dict:
    from urllib.parse import urlparse

    parsed = urlparse(url)
    return {"scheme": parsed.scheme, "path": parsed.path or "/"}


@given(
    st.sampled_from(["http", "https"]),
    st.text(
        alphabet=st.characters(whitelist_categories=("Ll", "Lu", "Nd")).filter(lambda c: c.isalnum() or c in "-."),
        min_size=1,
        max_size=20,
    ).filter(lambda host: bool(host.strip(".-"))),
    st.text(
        alphabet=st.characters(blacklist_characters="?# "),
        min_size=0,
        max_size=20,
    ),
)
@settings(max_examples=80)
def test_hypothesis_http_targets_keep_allowed_schemes(scheme: str, host: str, path_tail: str) -> None:
    url = f"{scheme}://{host}/{path_tail}"
    result = _contract_normalize_http_target(url)
    assert result["scheme"] in {"http", "https"}
    assert result["path"].startswith("/")
