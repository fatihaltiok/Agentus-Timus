from __future__ import annotations

from utils.location_local_intent import (
    analyze_location_local_intent,
    analyze_location_route_intent,
    is_location_local_query,
    is_location_route_query,
)


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


def test_location_route_intent_extracts_destination_and_mode() -> None:
    intent = analyze_location_route_intent("Erstelle mir eine Route zur Zeil in Frankfurt mit dem Auto")

    assert intent.is_route_request is True
    assert intent.destination_query == "zeil in frankfurt"
    assert intent.travel_mode == "driving"


def test_location_local_intent_rejects_route_request() -> None:
    intent = analyze_location_local_intent("Navigier mich bitte nach Berlin")

    assert intent.is_location_relevant is False
    assert intent.reason == "route_request"
    assert is_location_route_query("Navigier mich bitte nach Berlin") is True


def test_location_route_intent_strips_show_me_wrapper() -> None:
    intent = analyze_location_route_intent("Zeig mir den Weg nach Eschborn in Frankfurt")

    assert intent.is_route_request is True
    assert intent.destination_query == "eschborn in frankfurt"
