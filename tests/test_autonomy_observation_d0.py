from __future__ import annotations

from orchestration.autonomy_observation import render_autonomy_observation_markdown, summarize_autonomy_events


def test_summarize_autonomy_events_tracks_meta_context_state_metrics():
    events = [
        {
            "event_type": "meta_turn_type_selected",
            "observed_at": "2026-04-08T10:00:00+02:00",
            "payload": {"dominant_turn_type": "behavior_instruction", "request_id": "req-1"},
        },
        {
            "event_type": "meta_response_mode_selected",
            "observed_at": "2026-04-08T10:00:01+02:00",
            "payload": {"response_mode": "acknowledge_and_store", "request_id": "req-1"},
        },
        {
            "event_type": "meta_policy_mode_selected",
            "observed_at": "2026-04-08T10:00:02+02:00",
            "payload": {
                "response_mode": "acknowledge_and_store",
                "policy_reason": "state_summary_request",
                "request_id": "req-1",
            },
        },
        {
            "event_type": "meta_policy_override_applied",
            "observed_at": "2026-04-08T10:00:02.500000+02:00",
            "payload": {
                "policy_reason": "state_summary_request",
                "request_id": "req-1",
            },
        },
        {
            "event_type": "context_rehydration_bundle_built",
            "observed_at": "2026-04-08T10:00:03+02:00",
            "payload": {"request_id": "req-1"},
        },
        {
            "event_type": "context_slot_selected",
            "observed_at": "2026-04-08T10:00:04+02:00",
            "payload": {"slot": "conversation_state", "request_id": "req-1"},
        },
        {
            "event_type": "context_slot_suppressed",
            "observed_at": "2026-04-08T10:00:05+02:00",
            "payload": {"reason": "topic_mismatch_with_current_query", "request_id": "req-1"},
        },
        {
            "event_type": "preference_captured",
            "observed_at": "2026-04-08T10:00:06+02:00",
            "payload": {"scope": "topic", "request_id": "req-1"},
        },
        {
            "event_type": "preference_scope_selected",
            "observed_at": "2026-04-08T10:00:07+02:00",
            "payload": {"scope": "topic", "family": "source_policy", "request_id": "req-1"},
        },
        {
            "event_type": "preference_applied",
            "observed_at": "2026-04-08T10:00:08+02:00",
            "payload": {"request_id": "req-1"},
        },
        {
            "event_type": "context_misread_suspected",
            "observed_at": "2026-04-08T10:00:09+02:00",
            "payload": {
                "request_id": "req-1",
                "dominant_turn_type": "followup",
                "response_mode": "resume_open_loop",
                "risk_reasons": ["thin_context_for_risky_turn"],
            },
        },
        {
            "event_type": "conversation_state_updated",
            "observed_at": "2026-04-08T10:00:10+02:00",
            "payload": {"request_id": "req-1"},
        },
        {
            "event_type": "topic_shift_detected",
            "observed_at": "2026-04-08T10:00:11+02:00",
            "payload": {"request_id": "req-1"},
        },
    ]

    summary = summarize_autonomy_events(events)
    block = summary["meta_context_state"]

    assert block["turn_type_selected_total"] == 1
    assert block["response_mode_selected_total"] == 1
    assert block["policy_mode_selected_total"] == 1
    assert block["policy_override_total"] == 1
    assert block["context_bundle_built_total"] == 1
    assert block["context_slot_selected_total"] == 1
    assert block["context_slot_suppressed_total"] == 1
    assert block["preference_captured_total"] == 1
    assert block["preference_scope_selected_total"] == 1
    assert block["preference_applied_total"] == 1
    assert block["context_misread_suspected_total"] == 1
    assert block["conversation_state_updated_total"] == 1
    assert block["topic_shift_total"] == 1
    assert block["by_turn_type"]["behavior_instruction"] == 1
    assert block["by_response_mode"]["acknowledge_and_store"] == 2
    assert block["by_policy_reason"]["state_summary_request"] == 2
    assert block["by_slot"]["conversation_state"] == 1
    assert block["by_suppression_reason"]["topic_mismatch_with_current_query"] == 1
    assert block["by_preference_scope"]["topic"] == 2
    assert block["by_preference_family"]["source_policy"] == 1
    assert block["by_misread_reason"]["thin_context_for_risky_turn"] == 1
    assert block["healthy_bundle_rate"] == 0.0
    assert block["misread_rate"] == 1.0
    assert block["state_update_coverage"] == 1.0
    assert block["preference_roundtrip_rate"] == 1.0
    assert block["policy_override_rate"] == 1.0
    assert len(block["recent_misreads"]) == 1


def test_render_autonomy_observation_markdown_includes_d0_context_state_section():
    summary = summarize_autonomy_events(
        [
            {
                "event_type": "context_rehydration_bundle_built",
                "observed_at": "2026-04-08T10:00:00+02:00",
                "payload": {"request_id": "req-1"},
            },
            {
                "event_type": "preference_captured",
                "observed_at": "2026-04-08T10:00:01+02:00",
                "payload": {"scope": "topic", "request_id": "req-1"},
            },
        ]
    )

    markdown = render_autonomy_observation_markdown(summary)

    assert "## D0 Meta Context State" in markdown
    assert "Context-Bundles gebaut" in markdown
    assert "Preference-Captures" in markdown
    assert "Misread-Rate" in markdown
