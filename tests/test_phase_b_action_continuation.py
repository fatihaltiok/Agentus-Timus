from __future__ import annotations

from server.mcp_server import (
    _augment_query_with_followup_capsule,
    _extract_proposal_metadata,
    _is_affirmation,
    _resolve_resolved_proposal_agent,
)


def test_ok_fang_an_is_treated_as_affirmation():
    assert _is_affirmation("ok fang an") is True


def test_agent_delegation_proposal_is_extracted_and_routed_to_meta():
    reply = (
        "Soll ich den `developer`-Agenten beauftragen, "
        "eine Google Calendar-Integration zu planen?"
    )

    proposal = _extract_proposal_metadata(reply)

    assert proposal is not None
    assert proposal["kind"] == "agent_delegation"
    assert proposal["target_agent"] == "developer"
    assert "google calendar-integration" in proposal["suggested_query"].lower()

    dispatcher_query = _augment_query_with_followup_capsule(
        "ok fang an",
        {"last_proposed_action": proposal},
    )

    assert "# RESOLVED_PROPOSAL" in dispatcher_query
    assert "target_agent: developer" in dispatcher_query
    assert _resolve_resolved_proposal_agent(dispatcher_query) == "meta"


def test_guided_followup_proposal_keeps_full_action_instead_of_single_verb():
    reply = "Hast du schon ein Google Cloud Projekt oder soll ich dich durch die Erstellung führen?"

    proposal = _extract_proposal_metadata(reply)

    assert proposal is not None
    assert proposal["kind"] == "generic_action"
    assert proposal["target"] == "meta"
    assert proposal["suggested_query"].lower() == "durch die erstellung führen"


def test_ok_fang_an_prefers_pending_followup_prompt_over_weak_generic_proposal():
    dispatcher_query = _augment_query_with_followup_capsule(
        "ok fang an",
        {
            "last_agent": "meta",
            "last_user": "hey timus kannst du meinen googlekalender einsehen",
            "pending_followup_prompt": "Hast du schon ein Google Cloud Projekt oder soll ich dich durch die Erstellung führen?",
            "last_proposed_action": {
                "kind": "generic_action",
                "target": "executor",
                "suggested_query": "führen",
                "raw_sentence": "Hast du schon ein Google Cloud Projekt oder soll ich dich durch die Erstellung führen?",
            },
        },
    )

    assert "# RESOLVED_PROPOSAL" not in dispatcher_query
    assert "# FOLLOW-UP CONTEXT" in dispatcher_query
    assert "pending_followup_prompt: Hast du schon ein Google Cloud Projekt oder soll ich dich durch die Erstellung führen?" in dispatcher_query
