from __future__ import annotations

from orchestration.autonomy_observation import render_autonomy_observation_markdown, summarize_autonomy_events


def test_summarize_autonomy_events_tracks_d09_specialist_context_metrics():
    events = [
        {
            "event_type": "specialist_strategy_selected",
            "observed_at": "2026-04-08T15:00:00+02:00",
            "payload": {"agent": "research", "strategy_mode": "source_first_compact", "response_mode": "execute"},
        },
        {
            "event_type": "specialist_strategy_selected",
            "observed_at": "2026-04-08T15:00:01+02:00",
            "payload": {"agent": "visual", "strategy_mode": "vision_first", "response_mode": "execute"},
        },
        {
            "event_type": "specialist_signal_emitted",
            "observed_at": "2026-04-08T15:00:02+02:00",
            "payload": {"agent": "executor", "signal": "needs_meta_reframe", "signal_source": "agent"},
        },
        {
            "event_type": "specialist_signal_emitted",
            "observed_at": "2026-04-08T15:00:03+02:00",
            "payload": {"agent": "research", "signal": "context_mismatch", "signal_source": "heuristic"},
        },
    ]

    summary = summarize_autonomy_events(events)
    block = summary["specialist_context"]

    assert block["strategy_selected_total"] == 2
    assert block["specialist_signal_total"] == 2
    assert block["needs_meta_reframe_total"] == 1
    assert block["context_mismatch_total"] == 1
    assert block["agent_signal_rate"] == 0.5
    assert block["signal_reframe_rate"] == 0.5
    assert block["by_agent"]["research"] == 2
    assert block["by_agent"]["visual"] == 1
    assert block["by_agent"]["executor"] == 1
    assert block["by_strategy_mode"]["source_first_compact"] == 1
    assert block["by_strategy_mode"]["vision_first"] == 1
    assert block["by_signal"]["needs_meta_reframe"] == 1
    assert block["by_signal"]["context_mismatch"] == 1
    assert block["by_signal_source"]["agent"] == 1
    assert block["by_signal_source"]["heuristic"] == 1


def test_render_autonomy_observation_markdown_includes_d09_specialist_context_section():
    summary = summarize_autonomy_events(
        [
            {
                "event_type": "specialist_strategy_selected",
                "observed_at": "2026-04-08T15:00:00+02:00",
                "payload": {"agent": "research", "strategy_mode": "source_first_compact", "response_mode": "execute"},
            },
            {
                "event_type": "specialist_signal_emitted",
                "observed_at": "2026-04-08T15:00:01+02:00",
                "payload": {"agent": "executor", "signal": "needs_meta_reframe", "signal_source": "agent"},
            },
        ]
    )

    markdown = render_autonomy_observation_markdown(summary)

    assert "## D0.9 Specialist Context" in markdown
    assert "Strategien gewaehlt" in markdown
    assert "Specialist-Signale" in markdown
    assert "Agent-Signal-Rate" in markdown
    assert "Reframe-Rate" in markdown
    assert "Specialist-Strategie `source_first_compact`" in markdown
    assert "Specialist-Signal `needs_meta_reframe`" in markdown
