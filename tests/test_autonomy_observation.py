from __future__ import annotations

from pathlib import Path

from orchestration.autonomy_observation import AutonomyObservationStore, render_autonomy_observation_markdown


def test_autonomy_observation_store_records_and_summarizes_week_window(tmp_path: Path) -> None:
    store = AutonomyObservationStore(
        log_path=tmp_path / "autonomy_observation.jsonl",
        state_path=tmp_path / "autonomy_observation_state.json",
    )
    state = store.start_session(label="week-1", duration_days=7, started_at="2026-03-27T21:15:00+01:00")

    assert state["label"] == "week-1"
    assert state["active"] is True

    assert store.record_event(
        "meta_recipe_outcome",
        {
            "goal_signature": "pricing|live|light|table|none|loc=0|deliver=0",
            "task_type": "simple_live_lookup_document",
            "recipe_id": "simple_live_lookup_document",
            "success": True,
            "duration_ms": 1800,
            "planner_resolution_state": "adopted",
            "runtime_gap_insertions": ["runtime_goal_gap_document"],
        },
        observed_at="2026-03-27T21:20:00+01:00",
    )
    assert store.record_event(
        "runtime_goal_gap_inserted",
        {
            "goal_signature": "pricing|live|light|table|none|loc=0|deliver=0",
            "adaptive_reason": "runtime_goal_gap_document",
            "agent": "document",
            "stage_id": "document_output",
        },
        observed_at="2026-03-27T21:20:01+01:00",
    )
    assert store.record_event(
        "self_hardening_runtime_event",
        {
            "stage": "self_modify_finished",
            "status": "success",
            "pattern_name": "lookup_followup_context_loss",
            "route_target": "self_modify",
            "verification_status": "verified",
        },
        observed_at="2026-03-27T22:00:00+01:00",
    )
    assert store.record_event(
        "dispatcher_meta_fallback",
        {
            "reason": "uncertain_decision",
            "query_preview": "welches land passt zu meinen faehigkeiten",
        },
        observed_at="2026-03-27T22:05:00+01:00",
    )
    assert store.record_event(
        "meta_direct_tool_call",
        {
            "method": "search_web",
            "status": "error",
            "has_error": True,
            "error": "Timeout",
        },
        observed_at="2026-03-27T22:05:10+01:00",
    )
    assert store.record_event(
        "lead_diagnosis_selected",
        {
            "source_agent": "system",
            "evidence_level": "verified",
            "verified_paths_count": 1,
            "verified_functions_count": 1,
        },
        observed_at="2026-03-27T22:05:20+01:00",
    )
    assert store.record_event(
        "diagnosis_conflict_detected",
        {
            "supporting_count": 1,
            "lead_source_agent": "system",
        },
        observed_at="2026-03-27T22:05:21+01:00",
    )
    assert store.record_event(
        "developer_task_compiled",
        {
            "verified_paths_count": 1,
            "verified_functions_count": 1,
            "suppressed_claims_count": 1,
        },
        observed_at="2026-03-27T22:05:22+01:00",
    )
    assert store.record_event(
        "unverified_claim_suppressed",
        {
            "suppressed_claims_count": 2,
        },
        observed_at="2026-03-27T22:05:23+01:00",
    )
    assert store.record_event(
        "primary_fix_task_emitted",
        {
            "change_type": "type_normalization",
            "verified_paths_count": 1,
        },
        observed_at="2026-03-27T22:05:24+01:00",
    )
    assert store.record_event(
        "followup_task_deferred",
        {
            "followup_tasks_count": 2,
        },
        observed_at="2026-03-27T22:05:25+01:00",
    )
    assert store.record_event(
        "root_cause_gate_blocked",
        {
            "gate_reason": "missing_verified_paths",
        },
        observed_at="2026-03-27T22:05:26+01:00",
    )
    assert store.record_event(
        "task_mix_suppressed",
        {
            "task_mix_suppressed_count": 1,
        },
        observed_at="2026-03-27T22:05:27+01:00",
    )

    summary = store.build_summary()

    assert summary["total_events"] == 14
    assert summary["event_counts"]["observation_started"] == 1
    assert summary["event_counts"]["meta_recipe_outcome"] == 1
    assert summary["recipe_outcomes"]["success_total"] == 1
    assert summary["recipe_outcomes"]["planner_adopted_total"] == 1
    assert summary["runtime_gaps"]["by_reason"]["runtime_goal_gap_document"] == 1
    assert summary["self_hardening"]["self_modify_success_total"] == 1
    assert summary["meta_diagnostics"]["dispatcher_meta_fallback_total"] == 1
    assert summary["meta_diagnostics"]["direct_tool_calls_total"] == 1
    assert summary["meta_diagnostics"]["direct_tool_errors_total"] == 1
    assert summary["meta_diagnostics"]["lead_diagnosis_selected_total"] == 1
    assert summary["meta_diagnostics"]["diagnosis_conflicts_total"] == 1
    assert summary["meta_diagnostics"]["developer_tasks_compiled_total"] == 1
    assert summary["meta_diagnostics"]["unverified_claims_suppressed_total"] == 2
    assert summary["meta_diagnostics"]["primary_fix_tasks_total"] == 1
    assert summary["meta_diagnostics"]["followup_tasks_deferred_total"] == 2
    assert summary["meta_diagnostics"]["root_cause_gate_blocked_total"] == 1
    assert summary["meta_diagnostics"]["task_mix_suppressed_total"] == 1
    assert summary["top_goal_signatures"][0]["goal_signature"] == "pricing|live|light|table|none|loc=0|deliver=0"

    markdown = render_autonomy_observation_markdown(summary)
    assert "# Timus Autonomy Observation" in markdown
    assert "runtime_goal_gap_document" in markdown
    assert "Dispatcher -> Meta Fallbacks" in markdown
    assert "Lead-Diagnosen gewaehlt" in markdown
    assert "Primary-Fix-Tasks emittiert" in markdown
