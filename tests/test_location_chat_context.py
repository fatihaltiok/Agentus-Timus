from __future__ import annotations

from utils.location_chat_context import (
    build_location_chat_context_block,
    evaluate_location_chat_context,
    is_location_context_query,
)


def test_is_location_context_query_detects_nearby_and_route_queries() -> None:
    assert is_location_context_query("Wo bin ich gerade?")
    assert is_location_context_query("Finde mir Apotheken in meiner Nähe")
    assert is_location_context_query("Navigier mich zur nächsten Tankstelle")
    assert is_location_context_query("Wo bekomme ich gerade Kaffee?")


def test_evaluate_location_chat_context_requires_fresh_usable_snapshot() -> None:
    decision = evaluate_location_chat_context(
        query="Wo bin ich gerade?",
        snapshot={
            "presence_status": "live",
            "usable_for_context": True,
            "has_coordinates": True,
        },
        enabled=True,
    )
    assert decision.should_inject is True
    assert decision.reason == "fresh_location_context"

    stale = evaluate_location_chat_context(
        query="Wo bin ich gerade?",
        snapshot={
            "presence_status": "stale",
            "usable_for_context": False,
            "has_coordinates": True,
        },
        enabled=True,
    )
    assert stale.should_inject is False
    assert stale.reason == "presence_stale"


def test_build_location_chat_context_block_contains_key_fields() -> None:
    block = build_location_chat_context_block(
        {
            "presence_status": "live",
            "display_name": "Alexanderplatz, Berlin, Deutschland",
            "locality": "Berlin",
            "accuracy_meters": 12.4,
            "captured_at": "2026-03-16T12:00:00Z",
            "maps_url": "https://www.google.com/maps/search/?api=1&query=52.52,13.40",
        }
    )

    assert "# LIVE LOCATION CONTEXT" in block
    assert "presence_status: live" in block
    assert "display_name: Alexanderplatz, Berlin, Deutschland" in block
    assert "maps_url:" in block
