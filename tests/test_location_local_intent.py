from __future__ import annotations

from utils.location_local_intent import analyze_location_local_intent, is_location_local_query


def test_location_local_intent_detects_location_only_query() -> None:
    intent = analyze_location_local_intent("Wo bin ich gerade?")

    assert intent.is_location_relevant is True
    assert intent.is_location_only is True
    assert intent.maps_query == ""
    assert intent.reason == "location_only"


def test_location_local_intent_extracts_category_from_local_request() -> None:
    intent = analyze_location_local_intent("Welche Apotheke hat hier noch offen?")

    assert intent.is_location_relevant is True
    assert intent.is_location_only is False
    assert intent.maps_query == "Apotheke"
    assert intent.wants_open_now is True


def test_location_local_intent_preserves_qualified_restaurant_query() -> None:
    intent = analyze_location_local_intent("Finde mir ein italienisches Restaurant in meiner Nähe")

    assert intent.is_location_relevant is True
    assert intent.maps_query == "italienisches Restaurant"


def test_is_location_local_query_rejects_non_local_request() -> None:
    assert is_location_local_query("Erzaehl mir etwas ueber italienische Restaurants") is False
