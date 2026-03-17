from __future__ import annotations

import deal

from utils.meta_handoff_wrappers import strip_meta_canvas_wrappers


@deal.post(lambda r: isinstance(r, str))
@deal.post(lambda r: "# LIVE LOCATION CONTEXT" not in r)
@deal.post(lambda r: "Nutzeranfrage:" not in r)
def _contract_strip_meta_canvas_wrappers(query: str) -> str:
    return strip_meta_canvas_wrappers(query)


def test_contract_strip_meta_canvas_wrappers_route_example() -> None:
    result = _contract_strip_meta_canvas_wrappers(
        "Antworte ausschließlich auf Deutsch.\n\n"
        "Nutzeranfrage:\n"
        "# LIVE LOCATION CONTEXT\n"
        "presence_status: recent\n"
        "Use this location only for nearby, routing, navigation, or explicit place-context tasks.\n\n"
        "zeig mir den weg nach münster mit dem auto"
    )
    assert result == "zeig mir den weg nach münster mit dem auto"
