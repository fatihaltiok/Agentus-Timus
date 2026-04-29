from orchestration.meta_orchestration import classify_meta_task


def _mode(result: dict) -> str:
    return str((result.get("meta_interaction_mode") or {}).get("mode") or "")


def _frame_domain(result: dict) -> str:
    return str((result.get("meta_request_frame") or {}).get("task_domain") or "")


def test_direct_german_image_request_routes_to_creative_without_mode_block() -> None:
    result = classify_meta_task(
        "erstelle mir ein ausdrucksstarkes bild einer frau in einem jeanshemd "
        "sie ist ca 40 jahre alt und sehr selbstbewusst und gleichzeitg aber sehr feminin"
    )

    assert result["task_type"] == "image_generation"
    assert result["response_mode"] == "execute"
    assert result["recommended_agent_chain"] == ["meta", "creative"]
    assert result["recommended_recipe_id"] == "image_generation"
    assert _frame_domain(result) == "creative_generation"
    assert _mode(result) == "assist"


def test_image_request_preserves_owner_action_even_after_advisory_context() -> None:
    result = classify_meta_task(
        "mach ein bild von einer futuristischen werkstatt",
        conversation_state={
            "active_topic": "Geschaeftsidee mit KI",
            "active_goal": "Ideen bewerten",
            "active_domain": "topic_advisory",
            "open_loop": "Nutzer denkt ueber Gruendungsideen nach",
            "turn_type_hint": "followup",
        },
    )

    assert result["task_type"] == "image_generation"
    assert result["recommended_agent_chain"] == ["meta", "creative"]
    assert _frame_domain(result) == "creative_generation"
    assert _mode(result) != "think_partner"


def test_compound_image_word_routes_and_clarity_allows_creative() -> None:
    result = classify_meta_task(
        "erstelle ein einfaches testbild eines roten quadrats auf hellem hintergrund"
    )
    clarity = result["meta_clarity_contract"]

    assert result["task_type"] == "image_generation"
    assert result["recommended_agent_chain"] == ["meta", "creative"]
    assert _frame_domain(result) == "creative_generation"
    assert clarity["delegation_mode"] == "single_creative_handoff"
    assert clarity["allowed_delegate_agents"] == ["creative"]
    assert clarity["max_delegate_calls"] == 1


def test_image_analysis_wording_does_not_trigger_generation() -> None:
    result = classify_meta_task("beschreibe dieses bild")

    assert result["task_type"] != "image_generation"
    assert "creative" not in result["recommended_agent_chain"]
