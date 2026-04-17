from orchestration.typed_task_packet import (
    build_request_preflight,
    build_typed_task_packet,
    parse_typed_task_packet,
    shorten_for_preflight,
)


def test_build_typed_task_packet_normalizes_required_fields() -> None:
    packet = build_typed_task_packet(
        packet_type="meta_orchestration",
        objective="Fuehre eine aktuelle Live-Recherche zu LLM-Preisen durch und liefere eine Tabelle.",
        scope={
            "task_type": "simple_live_lookup_document",
            "recommended_agent_chain": ["meta", "executor", "document"],
        },
        acceptance_criteria=[
            "liefere aktuelle Preise",
            "liefere aktuelle Preise",
            "nenne Quellen",
        ],
        allowed_tools=["search_web", "fetch_url", "search_web"],
        reporting_contract={"must_include": ["table", "sources"]},
        escalation_policy={"on_missing_live_data": "state_verified_failure_without_guessing"},
        state_context={"active_topic": "LLM Preise", "recent_corrections": ["nur aktuelle Quellen"]},
    )

    assert packet["packet_type"] == "meta_orchestration"
    assert packet["objective"].startswith("Fuehre eine aktuelle Live-Recherche")
    assert packet["scope"]["task_type"] == "simple_live_lookup_document"
    assert packet["acceptance_criteria"] == ["liefere aktuelle Preise", "nenne Quellen"]
    assert packet["allowed_tools"] == ["search_web", "fetch_url"]
    assert packet["reporting_contract"]["must_include"] == ["table", "sources"]


def test_build_request_preflight_warns_for_large_request() -> None:
    packet = build_typed_task_packet(
        packet_type="meta_orchestration",
        objective="Recherchiere das Thema.",
        allowed_tools=["start_deep_research"],
    )

    report = build_request_preflight(
        packet=packet,
        original_request="A" * 2600,
        rendered_handoff="# META ORCHESTRATION HANDOFF\n" + ("X" * 1200),
        task_type="knowledge_research",
        recipe_id="knowledge_research",
    )

    assert report["state"] in {"warn", "blocked"}
    assert report["issues"]
    assert report["caps"]["max_request_chars"] >= 400


def test_parse_typed_task_packet_roundtrips_json_shape() -> None:
    packet = build_typed_task_packet(
        packet_type="recipe_stage_delegation",
        objective="Oeffne YouTube und fasse den Inhalt zusammen.",
        scope={"stage_id": "visual_access", "agent": "visual"},
        allowed_tools=["open_url", "fetch_url"],
    )

    parsed = parse_typed_task_packet(packet)

    assert parsed == packet


def test_shorten_for_preflight_respects_limit_env(monkeypatch) -> None:
    monkeypatch.setenv("TIMUS_REQUEST_PREFLIGHT_MAX_REQUEST_CHARS", "40")

    shortened = shorten_for_preflight(
        "Dies ist ein absichtlich sehr langer Request fuer den Preflight-Test in Phase F2.",
        task_type="simple_live_lookup",
    )

    assert len(shortened) <= 43
    assert shortened.endswith("...")
